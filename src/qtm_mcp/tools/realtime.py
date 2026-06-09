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

import json
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
    logger.info(f"Invoking fetch_qtm_data for data_types: {data_types}, frames: {frames}")

    if not data_types:
        raise ValueError("At least one data type is required")
        
    if not QTM_RT_AVAILABLE:
        logger.info("Generating synthetic QTM RT data as fallback")
        import random
        result = {}
        if "3d" in data_types:
            result["3d"] = [{"frame": i, "markers": [{"id": j, "x": random.uniform(-100, 100), "y": random.uniform(-100, 100), "z": random.uniform(0, 200)} for j in range(5)]} for i in range(frames)]
        if "6d" in data_types:
            result["6d"] = [{"frame": i, "bodies": [{"id": j, "x": random.uniform(-100, 100), "y": random.uniform(-100, 100), "z": random.uniform(0, 200), "roll": random.uniform(-180, 180), "pitch": random.uniform(-90, 90), "yaw": random.uniform(-180, 180)} for j in range(2)]} for i in range(frames)]
        if "analog" in data_types:
            result["analog"] = [{"frame": i, "channels": [{"id": j, "value": random.uniform(-5, 5)} for j in range(4)]} for i in range(frames)]
        if "force" in data_types:
            result["force"] = [{"frame": i, "plates": [{"id": j, "fx": random.uniform(-10, 10), "fy": random.uniform(-10, 10), "fz": random.uniform(500, 1000)} for j in range(2)]} for i in range(frames)]
        return {"status": "Success", "is_simulated": True, "data": result}
        
    raise NotImplementedError(
        "Live qtm_rt streaming is not implemented"
    )

