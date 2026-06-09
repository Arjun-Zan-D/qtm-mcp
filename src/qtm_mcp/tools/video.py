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

import os
import json
import base64
import logging
import asyncio
import hashlib
from pathlib import Path

from qtm_mcp.utils import get_project_patient_dir, validate_patient_inputs, safe_patient_path

logger = logging.getLogger("Universal_QTM_Server.video")

# Maximum number of keyframes an agent may request in a single call.
# Prevents runaway OpenCV decoding from blocking the event loop for minutes.
MAX_KEYFRAMES = 10

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
    logger.info("Successfully imported 'cv2' and 'numpy' for video/image analytics.")
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV ('cv2') or NumPy is not installed. Video keyframe tools will use basic text/placeholder base64 fallbacks.")

def _sync_extract_keyframes(patient_dir: Path, video_path: str, num_frames: int) -> list[dict]:
    """Synchronous CPU-bound OpenCV extraction."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video at {video_path}")
        
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_video_frames <= 0:
        cap.release()
        raise ValueError("Video file reported 0 total frames.")

    extracted_images = []
    indices = [0] if num_frames == 1 else [int(i * (total_video_frames - 1) / (num_frames - 1)) for i in range(num_frames)]
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    
    output_dir = patient_dir / ".keyframes"
    output_dir.mkdir(exist_ok=True)
    FRAME_QUALITY = 60
    
    for target_frame in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        success, frame = cap.read()
        if not success:
            continue
        
        frame_path = output_dir / f"frame_{target_frame:06d}.jpg"
        cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, FRAME_QUALITY])
        
        extracted_images.append({
            "frame_index": target_frame,
            "timestamp_ms": round((target_frame / fps) * 1000, 1),
            "image_path": frame_path.as_posix()
        })
        
    cap.release()
    return extracted_images


async def extract_video_keyframes(patient_id: str, session_date: str, num_frames: int = 5) -> dict:
    """Locates the reference sagittal/frontal plane video (.avi or .mp4) associated with the QTM session
    and extracts evenly-spaced keyframes across the gait cycle.
    """
    try:
        validate_patient_inputs(patient_id, session_date)
        patient_base = await get_project_patient_dir()
        patient_dir = await safe_patient_path(patient_base, patient_id, session_date)
    except ValueError as e:
        raise ValueError(f"Input Validation Error: {e}")

    num_frames = max(1, min(num_frames, MAX_KEYFRAMES))
    
    def _find_video(directory):
        if not directory.exists():
            return None
        matches = sorted(directory.glob("*.avi")) + sorted(directory.glob("*.mp4")) + sorted(directory.glob("*.mov"))
        if matches:
            return str(matches[0]).replace("\\", "/")
        return None
        
    video_path = await asyncio.to_thread(_find_video, patient_dir)

    if not OPENCV_AVAILABLE:
        raise RuntimeError("OpenCV ('cv2') is not installed, cannot extract keyframes.")

    if not video_path or not os.path.exists(video_path):
        patient_dir_str = str(patient_dir).replace("\\", "/")
        raise FileNotFoundError(
            f"No video file found in {patient_dir_str}. "
            f"Expected a video file (.avi, .mp4, .mov) in this directory."
        )

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
    try:
        logger.info(f"Extracting keyframes for Patient {hashed_id} from video: {video_path}")
        # Offload blocking OpenCV work to a background thread
        extracted_images = await asyncio.to_thread(_sync_extract_keyframes, patient_dir, video_path, num_frames)
        
        return {
            "patient_id": patient_id,
            "session_date": session_date,
            "video_source": video_path,
            "status": f"Extracted {len(extracted_images)} actual keyframes.",
            "keyframes": extracted_images
        }
    except Exception as e:
        logger.error(f"Failed to extract video keyframes: {str(e)}")
        raise RuntimeError(f"Video Extraction Error: {e}")
