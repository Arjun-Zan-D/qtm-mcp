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
from pathlib import Path

from qtm_mcp.config import get_settings
from qtm_mcp.utils import (
    get_project_patient_dir,
    safe_patient_path,
    validate_patient_inputs,
)

logger = logging.getLogger("Universal_QTM_Server.pipeline")


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
        patient_dir = safe_patient_path(patient_base, patient_id, session_date)
    except ValueError as e:
        raise ValueError(f"Input Validation Error: {e}")

    logger.info(
        f"Invoking trigger_processing_pipeline for Patient: {patient_id}, "
        f"Engine: {pipeline_type}"
    )

    settings = get_settings()
    patient_dir_str = str(patient_dir).replace("\\", "/")
    config_path = None

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

            command = [
                "matlab",
                "-nosplash",
                "-nodesktop",
                "-batch",
                f"addpath('{settings.matlab_scripts_path}'); "
                f"run_clinical_analysis_from_config('{config_path}');",
            ]
        except OSError as e:
            logger.error(f"Failed to write pipeline config tempfile: {e}")
            return f"Error: Could not create temporary configuration file: {e}"

    elif pipeline_type.lower() == "opensim":
        # SECURE PATTERN: Resolve the OpenSim XML path and verify it remains
        # within the configured opensim_config_root boundary.
        opensim_root = Path(settings.opensim_config_root).expanduser().resolve()
        setup_xml = (opensim_root / f"Setup_IK_{patient_id}.xml").resolve()
        if not setup_xml.is_relative_to(opensim_root):
            return "Error: OpenSim config path escapes the configured root directory."

        command = [
            "opensim-cmd",
            "run-tool",
            str(setup_xml).replace("\\", "/"),
        ]
    else:
        return f"Error: Unknown pipeline type '{pipeline_type}'. Must be 'matlab' or 'opensim'."

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
            
            return {
                "status": "Success",
                "pipeline_engine": pipeline_type,
                "processed_directory": patient_dir_str,
                "stdout": stdout.decode()
            }
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
        patient_dir = safe_patient_path(patient_base, patient_id, session_date)
    except ValueError as e:
        raise ValueError(f"Input Validation Error: {e}")

    logger.info(
        f"Invoking fetch_clinical_metrics for Patient: {patient_id}, "
        f"Session: {session_date}"
    )

    from qtm_mcp.utils import confined_file
    settings = get_settings()

    # Distinguish two FileNotFoundError flavours that confined_file() can raise:
    #   1. The configured projects_root itself does not exist on this machine
    #      → operator/config problem, surface as RuntimeError.
    #   2. The expected per-patient report file is missing inside a perfectly
    #      valid projects_root → normal "not yet processed" condition, surface
    #      as FileNotFoundError so the agent can prompt for pipeline execution.
    projects_root_path = Path(settings.projects_root).expanduser()
    if not projects_root_path.exists():
        raise RuntimeError(
            f"Configuration error: QTM_PROJECTS_ROOT "
            f"'{settings.projects_root}' does not exist on this machine."
        )

    try:
        metrics_file = confined_file(
            projects_root_path,
            patient_dir / f"{patient_id}_clinical_report.json",
            {".json"},
        )
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Clinical report not found for {patient_id}. "
            f"Expected {patient_id}_clinical_report.json in {patient_dir.as_posix()}."
        )
    except PermissionError as e:
        # confined_file raises PermissionError if the file escapes the jail
        raise PermissionError(f"Clinical report path failed boundary check: {e}")
    except ValueError as e:
        raise FileNotFoundError(f"Clinical report invalid or wrong type: {e}")

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
