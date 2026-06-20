import logging
import asyncio
from typing import Any

import httpx

from qtm_mcp.utils import get_scripting_client

logger = logging.getLogger("Universal_QTM_Server.scripting")

async def get_active_project_path() -> dict:
    """Returns the filesystem path of the currently active QTM project."""
    try:
        client = get_scripting_client()
        resp = await client.post(
            "/api/scripting/qtm/settings/directory/get_project_directory",
            json=[],
            timeout=5.0,
        )
        resp.raise_for_status()
        return {"status": "success", "project_path": resp.json()}
    except Exception as e:
        logger.error(f"Failed to get active project path: {e}")
        return {"status": "error", "message": str(e)}

async def list_capture_files(extension: str = ".qtm") -> dict:
    """Lists all capture files in the active QTM project directory.
    
    This uses the OS to scan the project directory to find files since the scripting
    API endpoints for file discovery depend on specific folders.
    """
    from qtm_mcp.utils import get_active_project_directory
    import os
    from pathlib import Path
    
    try:
        project_dir = await get_active_project_directory()
        if not project_dir:
            return {"status": "error", "message": "No active project found."}
            
        p = Path(project_dir)
        # Search recursively for files with the given extension
        files = []
        for file in p.rglob(f"*{extension}"):
            files.append(str(file.relative_to(p)).replace("\\", "/"))
            
        return {"status": "success", "project_path": project_dir, "files": files}
    except Exception as e:
        logger.error(f"Failed to list capture files: {e}")
        return {"status": "error", "message": str(e)}

async def load_capture_file(file_path: str) -> dict:
    """Loads a specific .qtm or .c3d file into QTM for viewing/processing."""
    try:
        client = get_scripting_client()
        # file_path could be relative, QTM resolves it against project dir
        resp = await client.post(
            "/api/scripting/qtm/data/object/file/open",
            json=[file_path],
            timeout=10.0,
        )
        resp.raise_for_status()
        return {"status": "success", "message": f"Loaded {file_path}", "result": resp.json()}
    except Exception as e:
        logger.error(f"Failed to load capture file: {e}")
        return {"status": "error", "message": str(e)}

async def find_trajectory(trajectory_name: str) -> dict:
    """Finds a named trajectory in the currently loaded QTM capture."""
    try:
        client = get_scripting_client()
        resp = await client.post(
            "/api/scripting/qtm/data/object/trajectory/find_trajectory",
            json=[trajectory_name],
            timeout=5.0,
        )
        resp.raise_for_status()
        return {"status": "success", "trajectory_id": resp.json()}
    except Exception as e:
        logger.error(f"Failed to find trajectory {trajectory_name}: {e}")
        return {"status": "error", "message": str(e)}

async def get_trajectory_samples(trajectory_id: int, start_frame: int, end_frame: int) -> dict:
    """Retrieves 3D coordinate samples for a trajectory across a frame range."""
    try:
        client = get_scripting_client()
        samples = []
        # In a real scenario, batched requests or a different endpoint might be better,
        # but this follows the documentation structure.
        for frame in range(start_frame, end_frame + 1):
            resp = await client.post(
                "/api/scripting/qtm/data/series/_3d/get_sample",
                json=[trajectory_id, frame],
                timeout=5.0,
            )
            if resp.status_code == 200:
                samples.append({"frame": frame, "point": resp.json()})
            else:
                samples.append({"frame": frame, "point": None})
        return {"status": "success", "trajectory_id": trajectory_id, "samples": samples}
    except Exception as e:
        logger.error(f"Failed to get trajectory samples: {e}")
        return {"status": "error", "message": str(e)}

async def trigger_paf_analysis(analysis_name: str) -> dict:
    """Triggers a PAF (Project Automation Framework) analysis pipeline in QTM."""
    try:
        client = get_scripting_client()
        # QTM PAF modules are usually run via qtm.gui.terminal.write or run_processing
        # Using run_processing assuming it maps to PAF modules
        resp = await client.post(
            "/api/scripting/qtm/data/object/file/run_processing",
            json=[analysis_name],
            timeout=300.0,  # PAF can take a long time
        )
        resp.raise_for_status()
        return {"status": "success", "message": f"PAF analysis '{analysis_name}' triggered.", "result": resp.json()}
    except httpx.HTTPStatusError as e:
        # Fallback to gui.terminal.write if run_processing is not the right one
        logger.warning(f"run_processing failed, trying terminal write for PAF: {e}")
        try:
            resp2 = await client.post(
                "/api/scripting/qtm/gui/terminal/write",
                json=[f"paf {analysis_name}"], # Assuming there's a paf command
                timeout=5.0,
            )
            resp2.raise_for_status()
            return {"status": "success", "message": f"Terminal command for PAF '{analysis_name}' sent.", "result": resp2.json()}
        except Exception as e2:
            return {"status": "error", "message": f"Failed to trigger PAF analysis: {e2}"}
    except Exception as e:
        logger.error(f"Failed to trigger PAF analysis: {e}")
        return {"status": "error", "message": str(e)}

async def get_qtm_setting(setting_path: str) -> dict:
    """Reads a QTM project or measurement setting."""
    try:
        client = get_scripting_client()
        # Convert dotted path to REST path
        api_path = "/api/scripting/qtm/settings/" + setting_path.replace(".", "/")
        resp = await client.post(
            api_path,
            json=[],
            timeout=5.0,
        )
        resp.raise_for_status()
        return {"status": "success", "setting_path": setting_path, "value": resp.json()}
    except Exception as e:
        logger.error(f"Failed to get QTM setting {setting_path}: {e}")
        return {"status": "error", "message": str(e)}

async def set_qtm_setting(setting_path: str, value: Any) -> dict:
    """Modifies a QTM project or measurement setting."""
    try:
        client = get_scripting_client()
        api_path = "/api/scripting/qtm/settings/" + setting_path.replace(".", "/")
        resp = await client.post(
            api_path,
            json=[value],
            timeout=5.0,
        )
        resp.raise_for_status()
        return {"status": "success", "setting_path": setting_path, "result": resp.json()}
    except Exception as e:
        logger.error(f"Failed to set QTM setting {setting_path}: {e}")
        return {"status": "error", "message": str(e)}
