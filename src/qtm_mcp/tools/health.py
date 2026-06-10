import logging
import hashlib
from typing import Dict, Any, List

from qtm_mcp.config import get_settings
from qtm_mcp.utils import validate_patient_id, validate_patient_inputs, safe_patient_path

logger = logging.getLogger("Universal_QTM_Server.health")

async def health_check() -> Dict[str, Any]:
    """Pings the QTM REST API, checks RT port status, and verifies MATLAB/OpenSim paths.
    
    Use this tool to quickly verify system health and ensure all required external
    services (QTM) and software paths (MATLAB, OpenSim) are correctly configured
    and accessible before running complex pipelines.
    """
    settings = get_settings()
    raise NotImplementedError("Tool not yet implemented — requires actual data source")

async def list_sessions(patient_id: str) -> List[str]:
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

    raise NotImplementedError("Tool not yet implemented — requires actual data source")

async def start_stop_capture(trial_name: str, action: str) -> Dict[str, str]:
    """Uses QTM REST API to trigger/stop cameras.
    
    Use this tool to control the Qualisys Track Manager hardware state remotely.
    Action must be either 'start' or 'stop'.
    """
    settings = get_settings()
    
    if action not in ["start", "stop"]:
        raise ValueError("Action must be 'start' or 'stop'.")
        
    raise NotImplementedError("Tool not yet implemented — requires actual data source")

async def get_calibration_status() -> Dict[str, Any]:
    """Queries QTM for the latest wand calibration error metrics.
    
    Use this tool to ensure that the camera system calibration is within acceptable
    limits before initiating a new capture session or trusting recorded 3D data.
    """
    settings = get_settings()
    
    try:
        import qtm_rt
    except ImportError:
        raise RuntimeError(
            "The 'qtm-rt' SDK is not installed. Calibration query is unavailable."
        )

    connection = await qtm_rt.connect(settings.qtm_rt_host, port=settings.qtm_rt_port)
    if connection is None:
        raise ConnectionError(
            f"Failed to connect to QTM RT server at {settings.qtm_rt_host}:{settings.qtm_rt_port}"
        )

    try:
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
            "message": str(e)
        }
    finally:
        try:
            await connection.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
