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
from typing import Annotated, Literal, Optional

from pydantic import Field
from qtm_mcp.connection import get_connection_manager

logger = logging.getLogger("qtm_mcp.realtime")

MAX_FRAMES = 120
FrameCount = Annotated[int, Field(ge=1, le=MAX_FRAMES)]


async def _collect_frames(components: list[str], frames: int) -> list[dict]:
    """Open a single RT stream subscription and collect *frames* packets.

    Previously, each stream_* tool looped range(frames) calling
    manager.get_rt_frame() once per iteration, which opened a fresh stream,
    waited for one packet, then stopped the stream -- per frame. That meant
    O(N) stream setup/teardown round-trips against the QTM RT TCP socket.

    By delegating to manager.stream_n_frames(...) we open the stream once,
    drain N packets, then stop the stream. The per-frame translation is
    handled inside connection.py.
    """
    manager = get_connection_manager()
    return await manager.stream_n_frames(components=components, n_frames=frames)


async def stream_6dof_data(body_names: Optional[list[str]] = None, frames: FrameCount = 10) -> dict:
    """Streams 6DOF rigid body position and rotation data from the live QTM RT feed."""
    logger.info(f"Invoking stream_6dof_data for {frames} frames")
    try:
        packets = await _collect_frames(components=["6d"], frames=frames)
    except Exception as e:
        logger.error(f"Error fetching 6DOF stream: {e}")
        return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    frames_data = []
    for frame_dict in packets:
        if "6d" in frame_dict:
            bodies = frame_dict["6d"]
            if body_names:
                bodies = [b for b in bodies if b["name"] in body_names]
            frames_data.append({
                "frame_number": frame_dict.get("frame_number"),
                "6d": bodies,
            })

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def stream_3d_markers(marker_names: Optional[list[str]] = None, frames: FrameCount = 10) -> dict:
    """Streams 3D marker coordinates from the live QTM RT feed."""
    logger.info(f"Invoking stream_3d_markers for {frames} frames")
    try:
        packets = await _collect_frames(components=["3d"], frames=frames)
    except Exception as e:
        logger.error(f"Error fetching 3D stream: {e}")
        return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    # Note: marker_names filtering is not applied because the RT 3D packet
    # contains points without labels; labels live in the parameters XML.
    frames_data = [
        {"frame_number": fd.get("frame_number"), "3d": fd.get("3d", [])}
        for fd in packets if "3d" in fd
    ]

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def stream_analog_data(channel_indices: Optional[list[int]] = None, frames: FrameCount = 10) -> dict:
    """Streams analog (EMG/force) channel data from QTM RT."""
    logger.info(f"Invoking stream_analog_data for {frames} frames")
    try:
        packets = await _collect_frames(components=["analog"], frames=frames)
    except Exception as e:
        logger.error(f"Error fetching analog stream: {e}")
        return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    # channel_indices filtering would require knowledge of the qtm_rt analog
    # packet layout (which varies by configuration), so we expose the raw
    # analog payload and let downstream tools slice it.
    frames_data = [
        {"frame_number": fd.get("frame_number"), "analog": fd.get("analog", [])}
        for fd in packets if "analog" in fd
    ]

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def stream_skeleton_data(skeleton_name: Optional[str] = None, frames: FrameCount = 10) -> dict:
    """Streams skeleton joint data from QTM RT (if skeleton solving is active)."""
    logger.info(f"Invoking stream_skeleton_data for {frames} frames")
    try:
        packets = await _collect_frames(components=["skeleton"], frames=frames)
    except Exception as e:
        logger.error(f"Error fetching skeleton stream: {e}")
        return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}

    frames_data = []
    for frame_dict in packets:
        if "skeleton_error" in frame_dict:
            return {
                "status": "error",
                "code": "SKELETON_UNSUPPORTED",
                "message": (
                    "Skeleton streaming not supported or no skeleton active: "
                    f"{frame_dict['skeleton_error']}"
                ),
            }
        if "skeleton" in frame_dict:
            frames_data.append({
                "frame_number": frame_dict.get("frame_number"),
                "skeleton": frame_dict["skeleton"],
            })

    return {"status": "success", "frames_collected": len(frames_data), "data": frames_data}


async def fetch_qtm_data() -> dict:
    """One-shot snapshot of ALL QTM RT data streams.
    
    Connects to the QTM RT server and grabs exactly one frame containing
    3D markers, 6DOF rigid bodies, analog channels, force plates, and
    skeleton data. Use this as a quick diagnostic to verify what data
    QTM is currently streaming.
    """
    logger.info("Invoking fetch_qtm_data snapshot")
    manager = get_connection_manager()
    
    try:
        frame_dict = await manager.get_rt_frame(
            components=["3d", "6d", "analog", "force", "skeleton"], 
            timeout=3.0
        )
        if not frame_dict:
            return {
                "status": "error", 
                "code": "RT_TIMEOUT", 
                "message": "Timed out waiting for RT frame.",
            }
        
        # Build combined response
        data = {
            "frame_number": frame_dict.get("frame_number"),
            "3d_markers": frame_dict.get("3d", []),
            "6dof_bodies": frame_dict.get("6d", []),
            "analog_channels": frame_dict.get("analog", []),
            "force_plates": frame_dict.get("force", []),
            "skeleton": frame_dict.get("skeleton", []),
        }
        if "skeleton_error" in frame_dict:
            data["skeleton_error"] = frame_dict["skeleton_error"]
            
        return {
            "status": "success",
            "data": data,
        }
    except Exception as e:
        logger.error(f"Error in fetch_qtm_data: {e}")
        return {"status": "error", "code": "RT_CONNECTION_FAILED", "message": str(e)}
