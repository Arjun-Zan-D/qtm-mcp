import logging
from typing import Annotated, Literal, Optional

from pydantic import Field
from qtm_mcp.connection import get_connection_manager

logger = logging.getLogger("Universal_QTM_Server.realtime")

MAX_FRAMES = 120
FrameCount = Annotated[int, Field(ge=1, le=MAX_FRAMES)]

async def stream_6dof_data(body_names: Optional[list[str]] = None, frames: FrameCount = 10) -> dict:
    """Streams 6DOF rigid body position and rotation data from the live QTM RT feed."""
    logger.info(f"Invoking stream_6dof_data for {frames} frames")
    manager = get_connection_manager()
    
    frames_data = []
    for _ in range(frames):
        try:
            frame_dict = await manager.get_rt_frame(components=["6d"])
            if frame_dict and "6d" in frame_dict:
                bodies = frame_dict["6d"]
                if body_names:
                    bodies = [b for b in bodies if b["name"] in body_names]
                frames_data.append({
                    "frame_number": frame_dict.get("frame_number"),
                    "6d": bodies
                })
        except Exception as e:
            logger.error(f"Error fetching 6DOF frame: {e}")
            return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def stream_3d_markers(marker_names: Optional[list[str]] = None, frames: FrameCount = 10) -> dict:
    """Streams 3D marker coordinates from the live QTM RT feed."""
    logger.info(f"Invoking stream_3d_markers for {frames} frames")
    manager = get_connection_manager()
    
    frames_data = []
    for _ in range(frames):
        try:
            frame_dict = await manager.get_rt_frame(components=["3d"])
            if frame_dict and "3d" in frame_dict:
                markers = frame_dict["3d"]
                # If marker_names provided, we would need to know the index mapping to filter them.
                # RT protocol just gives an array of points without labels in the data packet.
                # Labels are in parameters XML. For now, we return all points.
                frames_data.append({
                    "frame_number": frame_dict.get("frame_number"),
                    "3d": markers
                })
        except Exception as e:
            logger.error(f"Error fetching 3D frame: {e}")
            return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def stream_analog_data(channel_indices: Optional[list[int]] = None, frames: FrameCount = 10) -> dict:
    """Streams analog (EMG/force) channel data from QTM RT."""
    logger.info(f"Invoking stream_analog_data for {frames} frames")
    manager = get_connection_manager()
    
    frames_data = []
    for _ in range(frames):
        try:
            frame_dict = await manager.get_rt_frame(components=["analog"])
            if frame_dict and "analog" in frame_dict:
                analog = frame_dict["analog"]
                if channel_indices and hasattr(analog, "__getitem__"):
                    # Basic filtering if it's a list-like structure
                    pass # Proper indexing depends on the qtm-rt packet format
                frames_data.append({
                    "frame_number": frame_dict.get("frame_number"),
                    "analog": analog
                })
        except Exception as e:
            logger.error(f"Error fetching analog frame: {e}")
            return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def stream_skeleton_data(skeleton_name: Optional[str] = None, frames: FrameCount = 10) -> dict:
    """Streams skeleton joint data from QTM RT (if skeleton solving is active)."""
    logger.info(f"Invoking stream_skeleton_data for {frames} frames")
    manager = get_connection_manager()
    
    frames_data = []
    for _ in range(frames):
        try:
            frame_dict = await manager.get_rt_frame(components=["skeleton"])
            if not frame_dict:
                continue
                
            if "skeleton_error" in frame_dict:
                return {
                    "status": "error", 
                    "code": "SKELETON_UNSUPPORTED", 
                    "message": f"Skeleton streaming not supported or no skeleton active: {frame_dict['skeleton_error']}"
                }
                
            if "skeleton" in frame_dict:
                skeletons = frame_dict["skeleton"]
                frames_data.append({
                    "frame_number": frame_dict.get("frame_number"),
                    "skeleton": skeletons
                })
        except Exception as e:
            logger.error(f"Error fetching skeleton frame: {e}")
            return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}
