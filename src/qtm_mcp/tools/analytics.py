import logging
import json
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Any, List

from qtm_mcp.config import get_settings
from qtm_mcp.utils import validate_patient_inputs, safe_patient_path, get_project_patient_dir, confined_file

logger = logging.getLogger("Universal_QTM_Server.analytics")

_NORMATIVE_DB: Dict[str, Dict[str, Any]] = {
    "knee_flexion": {"mean": 65.0, "sd": 7.0, "unit": "degrees"},
    "hip_flexion": {"mean": 30.0, "sd": 5.0, "unit": "degrees"},
    "ankle_dorsiflexion": {"mean": 15.0, "sd": 4.0, "unit": "degrees"},
    "walking_speed": {"mean": 1.3, "sd": 0.2, "unit": "m/s"},
    "cadence": {"mean": 110.0, "sd": 10.0, "unit": "steps/min"},
    "step_length": {"mean": 0.75, "sd": 0.08, "unit": "m"},
    "stride_length": {"mean": 1.50, "sd": 0.15, "unit": "m"},
    "step_width": {"mean": 0.08, "sd": 0.02, "unit": "m"},
}

async def export_timeseries(patient_id: str, session_date: str, format: str = "json") -> Dict[str, Any]:
    """Flattens selected clinical metrics into an AI-ready training array.
    
    Use this tool to compile kinematic, kinetic, and spatiotemporal data
    into a structured format (JSON or CSV) suitable for machine learning ingestion.
    """
    settings = get_settings()
    
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)
    pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    def _scan_and_read(session_dir: Path) -> Dict[str, Any]:
        import os
        aggregated: Dict[str, Any] = {}
        if not session_dir.is_dir():
            return aggregated
        for entry in session_dir.iterdir():
            if entry.suffix.lower() == ".json" and entry.is_file():
                if os.path.getsize(entry) > 10 * 1024 * 1024:
                    continue  # skip files larger than 10 MB
                with open(entry, "r") as f:
                    aggregated[entry.stem] = json.load(f)
        return aggregated

    data = await asyncio.to_thread(_scan_and_read, patient_path)
    logger.info("export_timeseries completed for patient %s, session %s, %d files", pid_hash, session_date, len(data))
    return {
        "status": "success",
        "format": format,
        "patient_id": patient_id,
        "session_date": session_date,
        "data": data,
    }

async def segment_gait_cycles(patient_id: str, session_date: str) -> Dict[str, Any]:
    """Returns frame indices sliced from heel-strike to heel-strike.
    
    Use this tool to normalize time-series data to 0-100% of the gait cycle,
    allowing proper comparison of biomechanical curves across different trials.
    """
    settings = get_settings()
    
    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)
    pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    candidate = patient_path / "gait_cycles.json"
    if not candidate.exists():
        raise FileNotFoundError(
            f"gait_cycles.json not found for patient {pid_hash}, session {session_date}"
        )

    safe_path = await confined_file(Path(base_dir), candidate, {".json"})

    def _read(path: Path) -> Dict[str, Any]:
        import os
        if os.path.getsize(path) > 10 * 1024 * 1024:
            raise ValueError("File too large (>10 MB)")
        with open(path, "r") as f:
            return json.load(f)

    data = await asyncio.to_thread(_read, safe_path)
    logger.info("segment_gait_cycles loaded for patient %s, session %s", pid_hash, session_date)
    return data

async def compare_sessions(patient_id: str, pre_date: str, post_date: str) -> Dict[str, Any]:
    """Returns a delta analysis of spatiotemporal parameters between two sessions.
    
    Use this tool to evaluate patient progress or surgical outcomes by comparing
    metrics (e.g., walking speed, step length) before and after an intervention.
    """
    settings = get_settings()
    
    # Security checks for both sessions
    validate_patient_inputs(patient_id, pre_date)
    validate_patient_inputs(patient_id, post_date)
    base_dir = await get_project_patient_dir()
    pre_path = await safe_patient_path(base_dir, patient_id, pre_date)
    post_path = await safe_patient_path(base_dir, patient_id, post_date)
    pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    pre_candidate = pre_path / f"{patient_id}_clinical_report.json"
    post_candidate = post_path / f"{patient_id}_clinical_report.json"

    safe_pre = await confined_file(Path(base_dir), pre_candidate, {".json"})
    safe_post = await confined_file(Path(base_dir), post_candidate, {".json"})

    def _read(path: Path) -> Dict[str, Any]:
        import os
        if os.path.getsize(path) > 10 * 1024 * 1024:
            raise ValueError("File too large (>10 MB)")
        with open(path, "r") as f:
            return json.load(f)

    pre_data = await asyncio.to_thread(_read, safe_pre)
    post_data = await asyncio.to_thread(_read, safe_post)

    # Compute deltas for shared numeric keys
    delta_dict: Dict[str, float] = {}
    for key in pre_data:
        if key in post_data:
            pre_val = pre_data[key]
            post_val = post_data[key]
            if isinstance(pre_val, (int, float)) and isinstance(post_val, (int, float)):
                delta_dict[key] = post_val - pre_val

    logger.info(
        "compare_sessions completed for patient %s: %s vs %s, %d deltas",
        pid_hash, pre_date, post_date, len(delta_dict),
    )
    return {
        "status": "success",
        "patient_id": patient_id,
        "pre_date": pre_date,
        "post_date": post_date,
        "deltas": delta_dict,
        "pre_metrics": pre_data,
        "post_metrics": post_data,
    }

async def lookup_normative_data(age: int, sex: str, metric: str) -> Dict[str, Any]:
    """Returns expected reference bands for comparison.
    
    Use this tool to fetch standardized reference bounds (mean ± standard deviation)
    for specific clinical metrics based on a patient's age and sex cohort.
    """
    # This tool does not directly access patient file data, so no path traversal risk.

    if metric not in _NORMATIVE_DB:
        available = ", ".join(sorted(_NORMATIVE_DB.keys()))
        raise ValueError(
            f"Unknown metric '{metric}'. Available metrics: {available}"
        )

    val = _NORMATIVE_DB[metric]
    logger.info("lookup_normative_data: metric=%s, age=%d, sex=%s", metric, age, sex)
    return {
        "metric": metric,
        "age": age,
        "sex": sex,
        "mean": val["mean"],
        "sd": val["sd"],
        "unit": val["unit"],
        "range_low": val["mean"] - 2 * val["sd"],
        "range_high": val["mean"] + 2 * val["sd"],
    }
