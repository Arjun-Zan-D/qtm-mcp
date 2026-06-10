# Copyright (c) 2026 Xavier Gait Lab Contributors
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
from typing import Annotated, Literal
from pydantic import Field
logger = logging.getLogger("Universal_QTM_Server.realtime")

try:
    import qtm_rt  # noqa: F401
    QTM_RT_AVAILABLE = True
    logger.info("Successfully imported 'qtm_rt' SDK.")
except ImportError:
    QTM_RT_AVAILABLE = False
    logger.warning("The 'qtm-rt' SDK is not installed.")

MAX_FRAMES = 120
DataType = Literal["3d", "6d", "analog", "force"]
FrameCount = Annotated[int, Field(ge=1, le=MAX_FRAMES)]

async def fetch_qtm_data(data_types: list[DataType], frames: FrameCount) -> dict:
    """Fetches raw motion capture streams from the QTM RT server.

    Retrieves 3D marker coordinates, 6D rigid body Euler orientations,
    analog EMG signals, and force plate vectors for a specified number
    of frames.

    Args:
        data_types: List of desired components to pull. Choose from: ["3d", "6d", "analog", "force"].
        frames: Number of frames of data to retrieve (1-120).
    """
    import asyncio
    from qtm_mcp.config import get_settings
    settings = get_settings()

    logger.info(f"Invoking fetch_qtm_data for data_types: {data_types}, frames: {frames}")

    if not data_types:
        raise ValueError("At least one data type is required")
        
    if not (1 <= frames <= MAX_FRAMES):
        raise ValueError(f"frames must be between 1 and {MAX_FRAMES}, got {frames}")

    if not QTM_RT_AVAILABLE:
        raise RuntimeError(
            "The 'qtm-rt' SDK is not installed. Real-time data acquisition is unavailable. "
            "Install with: pip install qtm-mcp[realtime]"
        )
        
    # Map data types to qtm_rt stream components
    components = []
    for dt in data_types:
        if dt in ["3d", "6d", "analog", "force"]:
            components.append(dt)
        else:
            raise ValueError(f"Unknown data type: {dt}")

    # Establish connection with QTM RT server
    import qtm_rt
    connection = await qtm_rt.connect(settings.qtm_rt_host, port=settings.qtm_rt_port)
    if connection is None:
        raise ConnectionError(
            f"Failed to connect to QTM RT server at {settings.qtm_rt_host}:{settings.qtm_rt_port}"
        )

    frames_data = []
    done_event = asyncio.Event()

    def on_packet(packet):
        frame_dict = {"frame_number": packet.framenumber}
        
        if "3d" in components:
            try:
                # get_3d_markers returns (header, markers)
                _, markers = packet.get_3d_markers()
                if markers:
                    frame_dict["3d"] = [{"x": m.x, "y": m.y, "z": m.z} for m in markers]
                else:
                    frame_dict["3d"] = []
            except Exception as e:
                logger.error(f"Error parsing 3D markers: {e}")
                frame_dict["3d"] = []

        if "6d" in components:
            try:
                # get_6d returns (header, bodies)
                _, bodies = packet.get_6d()
                if bodies:
                    formatted_bodies = []
                    for b in bodies:
                        name, pos, rot = b
                        formatted_bodies.append({
                            "name": name,
                            "position": list(pos) if pos is not None else [],
                            "rotation": [list(row) for row in rot] if rot is not None else []
                        })
                    frame_dict["6d"] = formatted_bodies
                else:
                    frame_dict["6d"] = []
            except Exception as e:
                logger.error(f"Error parsing 6D bodies: {e}")
                frame_dict["6d"] = []

        if "analog" in components:
            try:
                # get_analog returns (header, analog_data)
                _, analog = packet.get_analog()
                frame_dict["analog"] = analog if analog is not None else []
            except Exception as e:
                logger.error(f"Error parsing analog data: {e}")
                frame_dict["analog"] = []

        if "force" in components:
            try:
                # get_force returns (header, force_data)
                _, force = packet.get_force()
                frame_dict["force"] = force if force is not None else []
            except Exception as e:
                logger.error(f"Error parsing force data: {e}")
                frame_dict["force"] = []

        frames_data.append(frame_dict)
        if len(frames_data) >= frames:
            done_event.set()

    try:
        await connection.stream_frames(components=components, on_packet=on_packet)
        try:
            # Wait for frames to accumulate with a 10s timeout
            await asyncio.wait_for(done_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout occurred while waiting for QTM frames. Returning partial data.")
    finally:
        try:
            await connection.stream_frames_stop()
        except Exception as e:
            logger.error(f"Error stopping stream: {e}")
        try:
            await connection.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    return {
        "status": "success",
        "frames_collected": len(frames_data),
        "data": frames_data
    }

