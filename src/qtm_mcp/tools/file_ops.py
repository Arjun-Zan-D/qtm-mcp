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


import logging
import asyncio
import hashlib

import httpx

from qtm_mcp.config import get_settings
from qtm_mcp.utils import get_project_patient_dir, validate_patient_inputs, safe_patient_path, get_shared_client

logger = logging.getLogger("qtm_mcp.file_ops")


async def load_patient_session(patient_id: str, session_date: str) -> dict:
    """Constructs the patient file path and uses the QTM local REST API to load
    the corresponding .qtm session file directly into the QTM interface.
    """
    try:
        validate_patient_inputs(patient_id, session_date)
        patient_base = await get_project_patient_dir()
        patient_dir = await safe_patient_path(patient_base, patient_id, session_date)
    except ValueError as e:
        raise ValueError(f"Input Validation Error: {e}")

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
    logger.info(
        f"Invoking load_patient_session for Patient: {hashed_id}, Date: {session_date}"
    )

    patient_dir_str = str(patient_dir).replace("\\", "/")

    # ── Locate an existing capture file in the directory ─────────────────────
    capture_file = None
    
    def _find_capture(directory):
        if not directory.exists():
            return None
        matches = sorted(directory.glob("*.qtm")) + sorted(directory.glob("*.c3d"))
        if matches:
            return str(matches[0]).replace("\\", "/")
        return None

    try:
        capture_file = await asyncio.to_thread(_find_capture, patient_dir)
    except Exception as e:
        logger.error(f"Failed to scan patient directory: {e}")

    if not capture_file:
        raise FileNotFoundError(
            f"No capture file found for patient {patient_id} on {session_date}. "
            f"Expected a .qtm or .c3d file in: {patient_dir_str}/"
        )

    payload = {"filePath": capture_file}
    settings = get_settings()

    # ── POST to QTM REST API via async httpx ─────────────────────────────────
    try:
        client = get_shared_client()
        endpoint = f"{settings.qtm_rest_url}/api/capture/open"
        response = await client.post(endpoint, json=payload, timeout=5.0)
        if response.status_code == 200:
            return {"status": "Success", "loaded_file": capture_file}
        else:
            safe_body = response.text[:500] if response.text else "(empty body)"
            raise RuntimeError(
                f"QTM REST API returned HTTP {response.status_code}. Body: {safe_body}"
            )
    except httpx.ConnectError:
        logger.warning("QTM REST API connection failed.")
        raise ConnectionError(f"QTM REST API offline at {settings.qtm_rest_url}")
    except httpx.TimeoutException:
        logger.warning("QTM REST API request timed out.")
        raise TimeoutError(f"QTM REST API request timed out after 5 seconds.")
