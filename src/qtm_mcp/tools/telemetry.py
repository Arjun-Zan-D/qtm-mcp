import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from qtm_mcp.config import get_settings
from qtm_mcp.utils import validate_patient_inputs, safe_patient_path, get_project_patient_dir, confined_file

logger = logging.getLogger("Universal_QTM_Server.telemetry")

async def get_emg_signals(patient_id: str, session_date: str, trial: str) -> dict:
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

async def get_force_plate_data(patient_id: str, session_date: str, trial: str) -> dict:
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

async def fill_trajectory_gaps(patient_id: str, session_date: str, max_gap_frames: int) -> dict:
    """Triggers a QTM gap-fill script to interpolate missing marker trajectories.
    
    Use this tool to clean up raw optical tracking data before running biomechanical
    modeling. Specify max_gap_frames to avoid interpolating over unrecoverable gaps.
    """
    settings = get_settings()
    pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)

    candidate_file = patient_path / "marker_trajectories.json"
    safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

    def _read(path: Path) -> Any:
        import os
        if os.path.getsize(path) > 10 * 1024 * 1024:
            raise ValueError("File too large")
        with open(path, "r") as f:
            return json.load(f)

    logger.info("Reading marker trajectories for patient %s / %s", pid_hash, session_date)
    data = await asyncio.to_thread(_read, safe_path)

    # --- Linear interpolation gap-fill ---
    gaps_filled = 0

    def _interpolate(values: List[Any]) -> List[Any]:
        nonlocal gaps_filled
        result = list(values)
        n = len(result)
        i = 0
        while i < n:
            if result[i] is None:
                start = i
                while i < n and result[i] is None:
                    i += 1
                gap_len = i - start
                if gap_len <= max_gap_frames and start > 0 and i < n:
                    left = result[start - 1]
                    right = result[i]
                    for j in range(gap_len):
                        t = (j + 1) / (gap_len + 1)
                        result[start + j] = left + (right - left) * t
                    gaps_filled += gap_len
            else:
                i += 1
        return result

    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], list) and any(v is None for v in data[key]):
                data[key] = _interpolate(data[key])
    elif isinstance(data, list):
        for idx, traj in enumerate(data):
            if isinstance(traj, list) and any(v is None for v in traj):
                data[idx] = _interpolate(traj)

    def _write(path: Path, content: Any) -> None:
        with open(path, "w") as f:
            json.dump(content, f)

    await asyncio.to_thread(_write, safe_path, data)
    logger.info("Gap-filled %d frames for patient %s / %s", gaps_filled, pid_hash, session_date)

    return {
        "status": "success",
        "patient_id": patient_id,
        "session_date": session_date,
        "gaps_filled": gaps_filled,
        "max_gap_frames": max_gap_frames,
    }

async def filter_signals(patient_id: str, session_date: str, signal_type: str, cutoff_freq: float) -> dict:
    """Applies low-pass filtering to marker trajectories or analog signals.
    
    Use this tool to smooth noisy kinematic or kinetic data (e.g., using a zero-lag
    Butterworth filter). Typical cutoff_freq is 6Hz for kinematics and 15-50Hz for kinetics.
    """
    settings = get_settings()
    pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)

    # Try primary filename, then fallback
    candidate_file = patient_path / f"{signal_type}_data.json"
    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})
    except (ValueError, FileNotFoundError):
        candidate_file = patient_path / f"signals_{signal_type}.json"
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

    def _read(path: Path) -> Any:
        import os
        if os.path.getsize(path) > 10 * 1024 * 1024:
            raise ValueError("File too large")
        with open(path, "r") as f:
            return json.load(f)

    logger.info("Reading %s signals for patient %s / %s", signal_type, pid_hash, session_date)
    data = await asyncio.to_thread(_read, safe_path)

    # --- Moving-average filter ---
    window = max(3, int(1.0 / cutoff_freq * 100))
    window = min(window, 21)

    def _moving_average(values: List[float]) -> List[float]:
        n = len(values)
        if n == 0:
            return values
        half_w = window // 2
        smoothed: List[float] = []
        for i in range(n):
            lo = max(0, i - half_w)
            hi = min(n, i + half_w + 1)
            smoothed.append(sum(values[lo:hi]) / (hi - lo))
        return smoothed

    filtered_data = data
    if isinstance(data, dict):
        filtered_data = {}
        for key, val in data.items():
            if isinstance(val, list) and val and isinstance(val[0], (int, float)):
                filtered_data[key] = _moving_average(val)
            else:
                filtered_data[key] = val
    elif isinstance(data, list) and data and isinstance(data[0], (int, float)):
        filtered_data = _moving_average(data)

    logger.info(
        "Applied moving_average (window=%d) to %s signals for patient %s / %s",
        window, signal_type, pid_hash, session_date,
    )

    return {
        "status": "success",
        "patient_id": patient_id,
        "session_date": session_date,
        "signal_type": signal_type,
        "cutoff_freq": cutoff_freq,
        "filter_applied": "moving_average",
        "window_size": window,
        "data": filtered_data,
    }
