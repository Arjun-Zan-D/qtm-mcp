# Copyright (c) 2026 Xavier Gait Lab Contributors
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
import logging
import asyncio
from pathlib import Path

import httpx

from qtm_mcp.config import get_settings

logger = logging.getLogger("Universal_QTM_Server.utils")

# ── Precompiled validation patterns ──────────────────────────────────────────
_PATIENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_SESSION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


_shared_client: httpx.AsyncClient | None = None

def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        raise RuntimeError("Shared HTTP client is not initialized")
    return _shared_client

def set_shared_client(client: httpx.AsyncClient | None):
    global _shared_client
    _shared_client = client

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


async def get_project_patient_dir() -> str:
    """Dynamically resolves the patient directory by querying QTM's active project REST endpoint

    or falling back to local configurations if QTM is offline.

    Returns:
        The resolved patient data directory as a forward-slash-normalized string.
    """
    settings = get_settings()
    current_project = settings.default_project
    try:
        client = get_shared_client()
        endpoint = f"{settings.qtm_rest_url}/api/project"
        response = await client.get(endpoint, timeout=2.0)
        if response.status_code == 200:
            project_info = response.json()
            project_path = project_info.get("path")
            if project_path:
                return os.path.join(project_path, "Patient_Data").replace("\\", "/")
            project_name = project_info.get("name")
            if project_name:
                current_project = project_name
    except httpx.RequestError as e:
        logger.debug(f"QTM REST API request failed ({type(e).__name__}). Using local cached project config.")
    except Exception as e:
        logger.error(f"Error querying active project: {e}")

    fallback_path = Path(settings.projects_root).expanduser() / current_project / "Patient_Data"
    return str(fallback_path).replace("\\", "/")
