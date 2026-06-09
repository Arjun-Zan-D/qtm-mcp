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

"""Async behavioural test suite for all QTM MCP tools.

Covers:
- Input validation (invalid patient_id / session_date raise ValueError)
- Fail closed logic for pipeline, video, and file_ops tools
- Subprocess execution patching for trigger_processing_pipeline

Run with:
    pip install -e ".[dev]"
    pytest tests/test_tools_async.py -v --asyncio-mode=auto
"""
import json
import pytest
import pytest_mock
import asyncio
from pathlib import Path

from qtm_mcp.utils import validate_patient_inputs
from qtm_mcp.tools.realtime import fetch_qtm_data
from qtm_mcp.tools.pipeline import trigger_processing_pipeline, fetch_clinical_metrics
from qtm_mcp.tools.video import extract_video_keyframes, MAX_KEYFRAMES
from qtm_mcp.tools.file_ops import load_patient_session

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

VALID_PATIENT = "PAT-203"
VALID_DATE = "2025-06-09"
VALID_DATE_POST = "2026-06-09"

# ─────────────────────────────────────────────────────────────────────────────
# Input Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestInputValidation:
    @pytest.mark.parametrize("bad_id", [
        "../../etc",
        "PAT;rm -rf /",
        "PAT'--injection",
        "a" * 65,       # too long
        "",              # empty
        "PAT 203",       # space (shell-unsafe)
        "../windows",
    ])
    def test_invalid_patient_id_raises(self, bad_id):
        with pytest.raises(ValueError, match="patient_id"):
            validate_patient_inputs(bad_id, VALID_DATE)

    @pytest.mark.parametrize("bad_date", [
        "2026-01-01; DROP TABLE",
        "../../../",
        "2026-1-1",         # missing zero-padding
        "20260109",         # no dashes
        "",
        "not-a-date",
    ])
    def test_invalid_session_date_raises(self, bad_date):
        with pytest.raises(ValueError, match="session_date"):
            validate_patient_inputs(VALID_PATIENT, bad_date)

    def test_valid_inputs_accepted(self):
        validate_patient_inputs("PAT-203", "2025-06-09")
        validate_patient_inputs("Patient_001", "2025-12-15")


# ─────────────────────────────────────────────────────────────────────────────
# fetch_qtm_data
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchQtmData:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self):
        with pytest.raises(RuntimeError):
            await fetch_qtm_data(["3d"], 2)


# ─────────────────────────────────────────────────────────────────────────────
# trigger_processing_pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestTriggerProcessingPipeline:
    @pytest.mark.asyncio
    async def test_matlab_subprocess_execution(self, mocker, tmp_path):
        mocker.patch("qtm_mcp.tools.pipeline.get_project_patient_dir", return_value=str(tmp_path))
        mocker.patch("qtm_mcp.tools.pipeline.safe_patient_path", return_value=tmp_path)
        
        # Mock subprocess
        mock_proc = mocker.AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"matlab output", b"")
        mocker.patch("asyncio.create_subprocess_exec", return_value=mock_proc)

        result = await trigger_processing_pipeline(VALID_PATIENT, VALID_DATE, "matlab")
        assert result["status"] == "Success"
        assert result["pipeline_engine"] == "matlab"
        assert result["stdout"] == "matlab output"

    @pytest.mark.asyncio
    async def test_invalid_patient_id_raises(self):
        with pytest.raises(ValueError):
            await trigger_processing_pipeline("../../etc", VALID_DATE, "matlab")


# ─────────────────────────────────────────────────────────────────────────────
# fetch_clinical_metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchClinicalMetrics:
    @pytest.mark.asyncio
    async def test_missing_report_raises_file_not_found(self, mocker, tmp_path):
        mocker.patch("qtm_mcp.tools.pipeline.get_project_patient_dir", return_value=str(tmp_path))
        mocker.patch("qtm_mcp.tools.pipeline.safe_patient_path", return_value=tmp_path)
        
        mock_settings = mocker.Mock()
        mock_settings.projects_root = str(tmp_path)
        mocker.patch("qtm_mcp.tools.pipeline.get_settings", return_value=mock_settings)
        
        with pytest.raises(FileNotFoundError):
            await fetch_clinical_metrics(VALID_PATIENT, VALID_DATE)

    @pytest.mark.asyncio
    async def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            await fetch_clinical_metrics(VALID_PATIENT, "not-a-date")


# ─────────────────────────────────────────────────────────────────────────────
# extract_video_keyframes
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractVideoKeyframes:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_video(self, mocker, tmp_path):
        mocker.patch("qtm_mcp.tools.video.get_project_patient_dir", return_value=str(tmp_path))
        mocker.patch("qtm_mcp.tools.video.safe_patient_path", return_value=tmp_path)
        with pytest.raises(FileNotFoundError):
            await extract_video_keyframes(VALID_PATIENT, VALID_DATE, num_frames=3)

    @pytest.mark.asyncio
    async def test_invalid_patient_id_raises(self):
        with pytest.raises(ValueError):
            await extract_video_keyframes("../../evil", VALID_DATE)


# ─────────────────────────────────────────────────────────────────────────────
# load_patient_session — mocked httpx
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadPatientSession:
    @pytest.mark.asyncio
    async def test_connect_error_raises_connection_error(self, mocker, tmp_path):
        import httpx
        mocker.patch("qtm_mcp.tools.file_ops.get_project_patient_dir", return_value=str(tmp_path))
        patient_dir = tmp_path / VALID_PATIENT / VALID_DATE
        patient_dir.mkdir(parents=True)
        (patient_dir / "test.qtm").touch()
        mocker.patch("qtm_mcp.tools.file_ops.safe_patient_path", return_value=patient_dir)
        
        from qtm_mcp.utils import set_shared_client
        mock_client = mocker.AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        set_shared_client(mock_client)
        with pytest.raises(ConnectionError):
            await load_patient_session(VALID_PATIENT, VALID_DATE)

    @pytest.mark.asyncio
    async def test_invalid_patient_id_raises(self):
        with pytest.raises(ValueError):
            await load_patient_session("PAT;inject", VALID_DATE)
