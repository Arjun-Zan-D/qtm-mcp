# Gait Video & Pose Extraction

**Use Case:** A physical therapist wants to visually inspect a patient's posture at specific critical moments during the gait cycle (e.g., initial contact / heel strike).

**Copy and paste the following prompt into your AI assistant:**

```text
Connect to the active QTM session. The patient is currently performing walking trials on the treadmill.

Please perform the following workflow:
1. Identify the timestamps for the last three 'Heel Strike' events on the right foot using the force plate telemetry or kinematic data.
2. Use the video extraction tool to grab keyframe images from the reference video camera at those exact three timestamps.
3. For each extracted keyframe, apply the 2D sagittal joint skeleton generator (OpenCV) so I can easily see the alignment of the trunk, hip, knee, and ankle.
4. Save these overlaid images to a 'Postural_Review' folder in the current project directory and show me the resulting file paths so I can review them with the patient.
```
