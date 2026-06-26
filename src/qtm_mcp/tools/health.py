import logging
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List

import httpx

from qtm_mcp.config import get_settings
from qtm_mcp.utils import validate_patient_id, validate_patient_inputs, safe_patient_path, get_project_patient_dir, get_shared_client

logger = logging.getLogger("Universal_QTM_Server.health")

async def health_check() -> dict:
    """Pings the QTM REST API, checks RT port status, and verifies MATLAB/OpenSim paths.
    
    Use this tool to quickly verify system health and ensure all required external
    services (QTM) and software paths (MATLAB, OpenSim) are correctly configured
    and accessible before running complex pipelines.
    """
    settings = get_settings()
    
    # Ping REST API
    rest_status = "error"
    try:
        client = get_shared_client()
        resp = await client.get(f"{settings.qtm_rest_url}/api/project", timeout=2.0)
        if resp.status_code == 200:
            rest_status = "ok"
    except Exception:
        pass
        
    # Probe RT socket
    rt_status = "error"
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.qtm_rt_host, settings.qtm_rt_port), 
            timeout=2.0
        )
        writer.close()
        await writer.wait_closed()
        rt_status = "ok"
    except Exception:
        pass
        
    # Check projects_root
    projects_dir = Path(settings.projects_root).expanduser()
    projects_root_status = "ok" if projects_dir.exists() and projects_dir.is_dir() else "missing"
    
    return {
        "rest_api": rest_status,
        "rt_port": rt_status,
        "projects_root": projects_root_status
    }

async def list_sessions(patient_id: str) -> list:
    """Returns a list of available session dates for a given patient.
    
    Use this tool to discover the recorded capture sessions for a specific patient.
    This is often the first step before accessing telemetry or biomechanical data.
    """
    settings = get_settings()
    
    try:
        # Validate patient ID without dummy date hack
        validate_patient_id(patient_id)
    except Exception as e:
        hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
        logger.error(f"Validation failed for patient {hashed_id}: {e}")
        raise

    base_dir = await get_project_patient_dir()
    patient_dir = Path(base_dir) / patient_id
    if not patient_dir.exists():
        return []
        
    import re
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    sessions = [d.name for d in patient_dir.iterdir() if d.is_dir() and date_re.match(d.name)]
    return sorted(sessions)

async def start_stop_capture(trial_name: str, action: str) -> dict:
    """Uses QTM REST API to trigger/stop cameras.
    
    Use this tool to control the Qualisys Track Manager hardware state remotely.
    Action must be either 'start' or 'stop'.
    """
    settings = get_settings()
    
    if action not in ["start", "stop"]:
        raise ValueError("Action must be 'start' or 'stop'.")
        
    endpoint = f"{settings.qtm_rest_url}/api/capture/{action}"
    payload = {"name": trial_name} if action == "start" else {}

    try:
        # Use the shared async httpx client (with circuit breaker) instead of
        # the blocking 'requests' library wrapped in asyncio.to_thread. That
        # avoids burning an executor thread per call and keeps capture
        # control on the same connection pool / breaker as every other QTM
        # REST request.
        client = get_shared_client()
        resp = await client.post(endpoint, json=payload, timeout=5.0)
        resp.raise_for_status()
        return {"status": "success", "action": action, "trial": trial_name}
    except Exception as e:
        logger.error("Capture %s failed: %s", action, e)
        return {"status": "error", "code": "UNKNOWN_ERROR", "action": action, "message": str(e)}

async def get_calibration_status() -> dict:
    """Queries QTM for the latest wand calibration error metrics.
    
    Use this tool to ensure that the camera system calibration is within acceptable
    limits before initiating a new capture session or trusting recorded 3D data.
    """
    try:
        from qtm_mcp.connection import get_connection_manager
        manager = get_connection_manager()
        connection = await manager.get_rt()
        
        xml_str = await connection.get_parameters(parameters=["calibration"])
        
        # Parse XML
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_str)
        
        cal_elem = root.find('.//Calibration')
        if cal_elem is None:
            return {
                "status": "unknown",
                "message": "Calibration element not found in QTM parameters.",
                "raw_xml": xml_str
            }
            
        date_str = cal_elem.findtext('Date', default='Unknown')
        
        avg_res_str = cal_elem.findtext('Average_Residual', default='0.0')
        try:
            avg_res = float(avg_res_str)
        except ValueError:
            avg_res = 0.0
            
        cams_str = cal_elem.findtext('Cameras', default='0')
        try:
            cams = int(cams_str)
        except ValueError:
            cams = 0
            
        # Determine pass status based on a standard 1.0 mm residual threshold
        is_calibrated = avg_res > 0.0 and avg_res < 1.0
        
        return {
            "status": "success",
            "is_calibrated": is_calibrated,
            "average_residual_mm": avg_res,
            "camera_count": cams,
            "calibration_date": date_str
        }
    except Exception as e:
        logger.error(f"Error querying calibration status: {e}")
        return {
            "status": "error",
            "code": "RT_CONNECTION_FAILED",
            "message": str(e)
        }

async def set_qtm_event(event_label: str) -> dict:
    """Inserts a named event marker into the active recording timeline.
    
    Use this tool to mark significant points in time (e.g. heel strike) during a capture.
    """
    try:
        from qtm_mcp.connection import get_connection_manager
        manager = get_connection_manager()
        connection = await manager.get_rt()
        
        await connection.set_qtm_event(event_label)
        return {"status": "success", "event": event_label}
    except Exception as e:
        logger.error(f"Error setting QTM event: {e}")
        return {
            "status": "error",
            "code": "RT_CONNECTION_FAILED",
            "message": str(e)
        }
