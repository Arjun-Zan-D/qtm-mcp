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
import tempfile
import asyncio
import os
import hashlib
from pathlib import Path

from qtm_mcp.config import get_settings
from qtm_mcp.utils import (
    get_project_patient_dir,
    safe_patient_path,
    validate_patient_inputs,
)

logger = logging.getLogger("Universal_QTM_Server.pipeline")

def _generate_default_ik_setup(xml_path: Path, patient_id: str):
    xml_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<OpenSimDocument Version="40000">
    <InverseKinematicsTool>
        <!-- Default auto-generated template for {patient_id} -->
        <model_file>placeholder_model.osim</model_file>
        <marker_file>placeholder_markers.trc</marker_file>
        <coordinate_file>placeholder_coordinates.mot</coordinate_file>
        <time_range>0 1</time_range>
    </InverseKinematicsTool>
</OpenSimDocument>"""
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(xml_path, "w") as f:
        f.write(xml_content)


async def trigger_processing_pipeline(
    patient_id: str, session_date: str, pipeline_type: str
) -> dict:
    """Triggers an external biomechanical processing script (such as MATLAB gait analysis

    or an OpenSim Inverse Kinematics command line) using the QTM session coordinates.

    Args:
        patient_id: The unique identifier of the patient (e.g., 'PAT-203').
        session_date: The date of the session in YYYY-MM-DD format (e.g., '2026-06-09').
        pipeline_type: The pipeline runtime configuration. Choose from: 'matlab' or 'opensim'.
    """
    # ── Input validation gate ────────────────────────────────────────────────
    try:
        validate_patient_inputs(patient_id, session_date)
        patient_base = await get_project_patient_dir()
        patient_dir = await safe_patient_path(patient_base, patient_id, session_date)
    except ValueError as e:
        raise ValueError(f"Input Validation Error: {e}")

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
    logger.info(
        f"Invoking trigger_processing_pipeline for Patient: {hashed_id}, "
        f"Engine: {pipeline_type}"
    )

    settings = get_settings()
    patient_dir_str = str(patient_dir).replace("\\", "/")
    config_path = None
    warning_msg = None

    # ── Build command for the requested pipeline engine ───────────────────────
    if pipeline_type.lower() == "matlab":
        # SECURE PATTERN: Dump user-supplied parameters into a temporary JSON
        # config file instead of interpolating them into the MATLAB command
        # string.  The MATLAB wrapper reads this config at runtime, completely
        # eliminating the f-string injection / RCE vector.
        config_data = {
            "patient_base_dir": patient_dir_str,
            "patient_id": patient_id,
            "session_date": session_date,
        }
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                prefix="qtm_pipeline_",
                delete=False,
                dir=tempfile.gettempdir(),
            ) as config_file:
                json.dump(config_data, config_file)
                config_path = config_file.name.replace("\\", "/")
            os.chmod(config_path, 0o600)

            matlab_root = Path(settings.matlab_scripts_path).expanduser().resolve()
            projects_root = Path(settings.projects_root).expanduser().resolve()
            if not matlab_root.is_relative_to(projects_root):
                raise PermissionError(f"MATLAB scripts path '{matlab_root}' escapes projects root '{projects_root}'")

            command = [
                "matlab",
                "-nosplash",
                "-nodesktop",
                "-r",
                f"addpath('{matlab_root.as_posix()}'); "
                f"run_clinical_analysis_from_config('{config_path}'); exit;",
            ]
        except OSError as e:
            logger.error(f"Failed to write pipeline config tempfile: {e}")
            raise RuntimeError(f"Could not create temporary configuration file: {e}")

    elif pipeline_type.lower() == "opensim":
        # SECURE PATTERN: Resolve the OpenSim XML path dynamically from project root.
        # Fall back to settings.opensim_config_root if dynamic resolution fails.
        base_dir = await get_project_patient_dir()
        if base_dir and "Patient_Data" in base_dir:
            project_root = Path(base_dir.replace("Patient_Data", "").rstrip("/\\"))
            opensim_dir = project_root / "OpenSim"
        else:
            opensim_dir = Path(settings.opensim_config_root).expanduser()

        opensim_root = opensim_dir.resolve()
        setup_xml = (opensim_root / f"Setup_IK_{patient_id}.xml").resolve()
        
        if not setup_xml.is_relative_to(opensim_root):
            raise PermissionError("OpenSim config path escapes the configured root directory.")

        log_dir = opensim_root.parent / "Logs"
        os.makedirs(log_dir, exist_ok=True)

        if not setup_xml.exists():
            _generate_default_ik_setup(setup_xml, patient_id)
            warning_msg = "default_template_used"

        command = [
            "opensim-cmd",
            "run-tool",
            str(setup_xml).replace("\\", "/"),
        ]
    else:
        raise ValueError(f"Unknown pipeline type '{pipeline_type}'. Must be 'matlab' or 'opensim'.")

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120.0)
            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                out_msg = stdout.decode().strip()
                details = err_msg if err_msg else out_msg
                if not details:
                    details = "No output provided (silent failure)"
                raise RuntimeError(f"Error: Pipeline {pipeline_type} exited with code {process.returncode}. Details: {details}")
            
            result = {
                "status": "Success",
                "pipeline_engine": pipeline_type,
                "processed_directory": patient_dir_str,
                "stdout": stdout.decode()
            }
            if warning_msg:
                result["warning"] = warning_msg
            return result
        except (TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise
    finally:
        if config_path and os.path.exists(config_path):
            try:
                os.remove(config_path)
                logger.debug(f"Securely deleted temporary pipeline config: {config_path}")
            except OSError as cleanup_error:
                logger.warning(f"Failed to delete temp file {config_path}: {cleanup_error}")


async def fetch_clinical_metrics(patient_id: str, session_date: str) -> dict:
    """Reads clinical reports (such as exported .tsv or .json files) containing computed
    spatio-temporal metrics and peak joint angles.
    """
    try:
        validate_patient_inputs(patient_id, session_date)
        patient_base = await get_project_patient_dir()
        patient_dir = await safe_patient_path(patient_base, patient_id, session_date)
    except ValueError as e:
        raise ValueError(f"Input Validation Error: {e}")

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
    logger.info(
        f"Invoking fetch_clinical_metrics for Patient: {hashed_id}, "
        f"Session: {session_date}"
    )

    from qtm_mcp.utils import confined_file
    settings = get_settings()

    try:
        metrics_file = await confined_file(
            Path(settings.projects_root),
            patient_dir / f"{patient_id}_clinical_report.json",
            {".json"},
        )
    except PermissionError:
        logger.critical(f"SECURITY: Path traversal attempt blocked for patient {hashed_id}")
        raise
    except FileNotFoundError as e:
        if str(Path(settings.projects_root).expanduser()) in str(e):
            raise RuntimeError(f"Configuration error: QTM_PROJECTS_ROOT '{settings.projects_root}' does not exist on this machine.")
        raise FileNotFoundError(f"Clinical report not found for {patient_id}. Expected {patient_id}_clinical_report.json in {patient_dir.as_posix()}.")
    except ValueError as e:
        raise FileNotFoundError(f"Clinical report not found: {e}")

    def _read_json(path):
        import os
        # size limit check
        if os.path.getsize(path) > 10 * 1024 * 1024:
            raise ValueError("File too large")
        with open(path, "r") as f:
            return json.load(f)
            
    try:
        logger.info(f"Loading local clinical metrics from: {metrics_file}")
        data = await asyncio.to_thread(_read_json, metrics_file)
        return data
    except Exception as e:
        logger.error(f"Failed to read clinical report file: {e}")
        raise
