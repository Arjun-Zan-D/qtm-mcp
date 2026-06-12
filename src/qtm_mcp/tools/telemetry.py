import logging
import json
from pathlib import Path
from typing import Dict, Any, List

from qtm_mcp.config import get_settings
from qtm_mcp.utils import validate_patient_inputs, safe_patient_path, get_project_patient_dir, confined_file

logger = logging.getLogger("Universal_QTM_Server.telemetry")

async def get_emg_signals(patient_id: str, session_date: str, trial: str) -> Dict[str, Any]:
    """Returns structured Delsys analog data for muscle activation.
    
    Use this tool to extract raw or processed electromyography (EMG) time-series
    data for a specific trial, which is essential for determining muscle activation
    timing and amplitude during gait cycles.
    """
    settings = get_settings()
    
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)
    
    candidate_file = patient_path / f"emg_{trial}.json"
    if not candidate_file.exists():
        candidate_file = patient_path / "emg_data.json"
        
    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})
        with open(safe_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load EMG data for {patient_id}/{session_date}/{trial}: {e}")
        raise RuntimeError(f"Could not load EMG data: {e}")

async def get_force_plate_data(patient_id: str, session_date: str, trial: str) -> Dict[str, Any]:
    """Returns Fx, Fy, Fz, and CoP arrays from force plates.
    
    Use this tool to obtain ground reaction forces and center of pressure
    data necessary for inverse dynamics calculations.
    """
    settings = get_settings()
    
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)
    
    candidate_file = patient_path / f"force_plates_{trial}.json"
    if not candidate_file.exists():
        candidate_file = patient_path / "force_plate_data.json"
        
    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})
        with open(safe_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load force plate data for {patient_id}/{session_date}/{trial}: {e}")
        raise RuntimeError(f"Could not load force plate data: {e}")

async def fill_trajectory_gaps(patient_id: str, session_date: str, max_gap_frames: int) -> Dict[str, Any]:
    """Triggers a QTM gap-fill script to interpolate missing marker trajectories.
    
    Use this tool to clean up raw optical tracking data before running biomechanical
    modeling. Specify max_gap_frames to avoid interpolating over unrecoverable gaps.
    """
    settings = get_settings()
    
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    patient_path = await safe_patient_path(settings.projects_root, patient_id, session_date)
    
    raise NotImplementedError("Tool not yet implemented — requires actual data source")

async def filter_signals(patient_id: str, session_date: str, signal_type: str, cutoff_freq: float) -> Dict[str, Any]:
    """Applies low-pass filtering to marker trajectories or analog signals.
    
    Use this tool to smooth noisy kinematic or kinetic data (e.g., using a zero-lag
    Butterworth filter). Typical cutoff_freq is 6Hz for kinematics and 15-50Hz for kinetics.
    """
    settings = get_settings()
    
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    patient_path = await safe_patient_path(settings.projects_root, patient_id, session_date)
    
    raise NotImplementedError("Tool not yet implemented — requires actual data source")
