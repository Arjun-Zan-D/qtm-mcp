# Copyright (c) 2026 Arjun Singh Shishodia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import time
import logging
import asyncio
from pathlib import Path

import httpx

from qtm_mcp.config import get_settings

logger = logging.getLogger("qtm_mcp.utils")

# ── Precompiled validation patterns ──────────────────────────────────────────
_PATIENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_SESSION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CircuitBreakerClient:
    def __init__(self, client: httpx.AsyncClient, max_failures: int = 3, reset_timeout: float = 60.0):
        self._client = client
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"

    def _allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit Breaker HALF_OPEN. Testing connection.")
                return True
            return False
        return True

    def _record_success(self):
        if self.state != "CLOSED":
            logger.info("Circuit Breaker CLOSED. Service recovered.")
        self.failures = 0
        self.state = "CLOSED"

    def _record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.max_failures:
            if self.state != "OPEN":
                logger.warning(f"Circuit Breaker OPEN. Too many failures ({self.failures}).")
            self.state = "OPEN"

    async def get(self, *args, **kwargs):
        if not self._allow_request():
            raise RuntimeError("Circuit Breaker OPEN: QTM REST API is temporarily unavailable.")
        try:
            response = await self._client.get(*args, **kwargs)
            self._record_success()
            return response
        except httpx.RequestError as e:
            self._record_failure()
            raise e

    async def post(self, *args, **kwargs):
        if not self._allow_request():
            raise RuntimeError("Circuit Breaker OPEN: QTM REST API is temporarily unavailable.")
        try:
            response = await self._client.post(*args, **kwargs)
            self._record_success()
            return response
        except httpx.RequestError as e:
            self._record_failure()
            raise e

def get_shared_client() -> CircuitBreakerClient:
    """Returns the General REST client."""
    from qtm_mcp.connection import get_connection_manager
    return get_connection_manager().get_rest_client()

def get_scripting_client() -> CircuitBreakerClient:
    """Returns the Scripting API REST client."""
    from qtm_mcp.connection import get_connection_manager
    return get_connection_manager().get_scripting_client()

async def confined_file(root: Path, candidate: Path, suffixes: set[str]) -> Path:
    """Safely resolves a file path and ensures it remains within the trusted root."""
    def _resolve():
        return root.expanduser().resolve(strict=True), candidate.expanduser().resolve(strict=True)
        
    trusted_root, resolved = await asyncio.to_thread(_resolve)
    
    if not resolved.is_relative_to(trusted_root):
        raise PermissionError("File escapes configured projects root")
        
    # Additional check: reject if any component of the path is a symlink
    for parent in candidate.expanduser().parents:
        if parent.is_symlink():
            raise PermissionError("Symlinks are not permitted in patient data paths")
    if candidate.expanduser().is_symlink():
        raise PermissionError("Symlinks are not permitted in patient data paths")
        
    if not resolved.is_file() or resolved.suffix.lower() not in suffixes:
        raise ValueError("Unsupported or missing file")
    return resolved


def validate_patient_id(patient_id: str) -> None:
    """Validates patient_id against strict format constraints."""
    if not _PATIENT_ID_RE.match(patient_id):
        raise ValueError(
            f"Invalid patient_id '{patient_id}': "
            "must be 1-64 characters matching [A-Za-z0-9_-]"
        )

def validate_patient_inputs(patient_id: str, session_date: str) -> None:
    """Validates patient_id and session_date against strict format constraints.

    Raises:
        ValueError: If either input contains characters outside the allowed
            character set, preventing shell metacharacter injection and
            directory traversal attempts.
    """
    validate_patient_id(patient_id)
    if not _SESSION_DATE_RE.match(session_date):
        raise ValueError(
            f"Invalid session_date '{session_date}': must match YYYY-MM-DD format"
        )


async def safe_patient_path(base_dir: str, patient_id: str, session_date: str) -> Path:
    """Constructs and validates a patient data path with directory-traversal jail check.

    Resolves the final path using ``Path.resolve()`` and verifies it remains
    within the *base_dir* boundary via ``Path.is_relative_to()``.

    Args:
        base_dir: The trusted root directory for patient data.
        patient_id: Validated patient identifier segment.
        session_date: Validated session date segment (YYYY-MM-DD).

    Returns:
        A fully resolved ``Path`` object guaranteed to reside under *base_dir*.

    Raises:
        ValueError: If the resolved path escapes the base directory boundary.
    """
    def _resolve():
        base = Path(base_dir).expanduser().resolve()
        target = (base / patient_id / session_date).resolve()
        return base, target
        
    base, target = await asyncio.to_thread(_resolve)
    
    if not target.is_relative_to(base):
        raise ValueError(
            "Path traversal blocked: resolved path escapes the patient data boundary"
        )
    return target


async def get_active_project_directory() -> str | None:
    """Queries the Scripting API for the live project directory."""
    try:
        client = get_scripting_client()
        resp = await client.post(
            "/api/scripting/qtm/settings/directory/get_project_directory",
            json=[],
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Scripting API get_project_directory failed: {e}")
    return None

async def get_project_patient_dir() -> str:
    """Dynamically resolves the patient directory using a 3-tier strategy:
    
    Tier 1: Scripting API (Port 7979)
    Tier 2: General REST API (Port 22222)
    Tier 3: Local environment configuration fallback
    """
    settings = get_settings()
    current_project = settings.default_project

    # Tier 1: Scripting API
    scripting_path = await get_active_project_directory()
    if scripting_path:
        return os.path.join(scripting_path, "Patient_Data").replace("\\", "/")

    # Tier 2: General REST API
    try:
        client = get_shared_client()
        endpoint = f"{settings.qtm_rest_url}/api/project"
        response = await client.get(endpoint, timeout=2.0)
        if response.status_code == 200:
            project_info = response.json()
            project_path = project_info.get("projectPath") or project_info.get("path")
            if project_path:
                return os.path.join(project_path, "Patient_Data").replace("\\", "/")
            project_name = project_info.get("name")
            if project_name:
                current_project = project_name
    except httpx.RequestError as e:
        logger.debug(f"QTM REST API request failed ({type(e).__name__}). Falling back to local config.")
    except Exception as e:
        logger.error(f"Error querying active project: {e}")

    # Tier 3: Local Configuration Fallback
    logger.warning("Dynamic project resolution failed. Using local configuration fallback.")
    if settings.qtm_project_dir:
        fallback_path = Path(settings.qtm_project_dir).expanduser() / "Patient_Data"
    else:
        fallback_path = Path(settings.projects_root).expanduser() / current_project / "Patient_Data"
    return str(fallback_path).replace("\\", "/")
