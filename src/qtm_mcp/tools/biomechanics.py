import asyncio
import logging
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List

from qtm_mcp.config import get_settings
from qtm_mcp.utils import validate_patient_id, validate_patient_inputs, safe_patient_path, get_project_patient_dir, confined_file

logger = logging.getLogger("Universal_QTM_Server.biomechanics")

async def get_patient_anthropometrics(patient_id: str) -> dict:
    """Fetches leg length, mass, and joint widths.
    
    Use this tool to retrieve the static physical measurements required
    to scale biomechanical models (like OpenSim) or compute joint centers.
    """
    settings = get_settings()
    
    try:
        validate_patient_id(patient_id)
    except Exception as e:
        hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
        logger.error(f"Validation failed for patient {hashed_id}: {e}")
        raise
    
    base_dir = await get_project_patient_dir()
    patient_dir = Path(base_dir) / patient_id
    candidate_file = patient_dir / "anthropometrics.json"
    
    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})
        with open(safe_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load anthropometrics for {patient_id}: {e}")
        raise RuntimeError(f"Could not load anthropometrics: {e}")

async def compute_joint_angles(patient_id: str, session_date: str, joint: str) -> dict:
    """Returns time-series Euler angles (flexion/extension, abduction/adduction) for a specified joint.
    
    Use this tool to get the calculated 3D kinematic curves for clinical review.
    Joints can be 'knee', 'hip', 'ankle', 'pelvis', etc.
    """
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    # Resolve the project's Patient_Data root dynamically (Scripting API ->
    # REST -> local config) and confine the session path to it, matching
    # every other tool's jail. Previously this used settings.projects_root
    # directly, which is the *top-level* QTM projects directory, not the
    # active project's Patient_Data dir -- so paths under the real session
    # directory would have been rejected (or, worse, a sibling-project's
    # data would have been considered in-jail).
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)
    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    candidate_file = patient_path / f"joint_angles_{joint}.json"
    if not candidate_file.exists():
        candidate_file = patient_path / "joint_angles.json"

    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

        def _read(path):
            import os
            if os.path.getsize(path) > 10 * 1024 * 1024:
                raise ValueError("File too large (>10 MB)")
            with open(path, "r") as f:
                return json.load(f)

        return await asyncio.to_thread(_read, safe_path)
    except Exception as e:
        logger.error(f"Failed to load joint angles for {hashed_id}/{session_date}/{joint}: {e}")
        raise RuntimeError(f"Could not load joint angles: {e}")

async def compute_cop_trajectory(patient_id: str, session_date: str) -> dict:
    """Returns the unified Centre of Pressure path across all force plates.
    
    Use this tool to evaluate balance, weight transfer symmetry, and foot strike
    patterns during the gait cycle.
    """
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    # Use the dynamically-resolved Patient_Data root as the jail (see
    # compute_joint_angles for the same reasoning).
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)
    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    candidate_file = patient_path / "cop_trajectory.json"

    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

        def _read(path):
            import os
            if os.path.getsize(path) > 10 * 1024 * 1024:
                raise ValueError("File too large (>10 MB)")
            with open(path, "r") as f:
                return json.load(f)

        return await asyncio.to_thread(_read, safe_path)
    except Exception as e:
        logger.error(f"Failed to load CoP trajectory for {hashed_id}/{session_date}: {e}")
        raise RuntimeError(f"Could not load CoP trajectory: {e}")
