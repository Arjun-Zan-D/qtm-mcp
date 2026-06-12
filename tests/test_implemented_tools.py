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

"""Tests for the 11 newly implemented tool functions + push_to_ehr.

Covers every tool that was previously a NotImplementedError stub, plus
the graceful-offline fixes for realtime.fetch_qtm_data and
health.start_stop_capture.

Run with:
    uv run pytest tests/test_implemented_tools.py -v --asyncio-mode=auto
"""

import json
import os
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

# ── Tool imports ─────────────────────────────────────────────────────────────
from qtm_mcp.tools.biomechanics import compute_joint_angles, compute_cop_trajectory
from qtm_mcp.tools.analytics import (
    export_timeseries,
    segment_gait_cycles,
    compare_sessions,
    lookup_normative_data,
)
from qtm_mcp.tools.telemetry import fill_trajectory_gaps, filter_signals
from qtm_mcp.tools.clinical_output import (
    generate_pdf_report,
    export_c3d,
    push_to_ehr,
    update_clinical_notes,
)
from qtm_mcp.tools.health import start_stop_capture
from qtm_mcp.tools.realtime import fetch_qtm_data

# ── Constants ────────────────────────────────────────────────────────────────
VALID_PATIENT = "PAT-TEST"
VALID_DATE = "2026-06-10"


# ════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def session_dir(tmp_path):
    """Create a mock patient session directory with sample data files."""
    sdir = tmp_path / VALID_PATIENT / VALID_DATE
    sdir.mkdir(parents=True)

    # Joint angles
    with open(sdir / "joint_angles_knee.json", "w") as f:
        json.dump({"joint": "knee", "flexion": [10.5, 20.3, 30.1], "extension": [5.2, 10.1, 15.0]}, f)
    with open(sdir / "joint_angles.json", "w") as f:
        json.dump({"joint": "all", "data": {"knee": [10, 20], "hip": [5, 10]}}, f)

    # CoP trajectory
    with open(sdir / "cop_trajectory.json", "w") as f:
        json.dump({"cop_x": [0.1, 0.2, 0.3], "cop_y": [0.4, 0.5, 0.6]}, f)

    # Gait cycles
    with open(sdir / "gait_cycles.json", "w") as f:
        json.dump({"cycles": [{"start": 0, "end": 100}, {"start": 100, "end": 200}]}, f)

    # Marker trajectories (with gaps)
    with open(sdir / "marker_trajectories.json", "w") as f:
        json.dump({
            "markers": {
                "LASI": [1.0, None, None, 4.0, 5.0],
                "RASI": [2.0, 3.0, None, 5.0, 6.0],
            }
        }, f)

    # Signal data
    with open(sdir / "emg_data.json", "w") as f:
        json.dump({"channels": {"biceps": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]}}, f)

    # Clinical report
    with open(sdir / f"{VALID_PATIENT}_clinical_report.json", "w") as f:
        json.dump({
            "walking_speed": 1.2,
            "cadence": 105,
            "step_length": 0.70,
            "knee_flexion_peak": 58.3,
        }, f)

    return sdir


@pytest.fixture
def session_dir_pair(tmp_path):
    """Create pre and post session directories for compare_sessions."""
    pre_dir = tmp_path / VALID_PATIENT / "2026-01-10"
    post_dir = tmp_path / VALID_PATIENT / "2026-06-10"
    pre_dir.mkdir(parents=True)
    post_dir.mkdir(parents=True)

    with open(pre_dir / f"{VALID_PATIENT}_clinical_report.json", "w") as f:
        json.dump({"walking_speed": 1.0, "cadence": 100, "step_length": 0.65}, f)

    with open(post_dir / f"{VALID_PATIENT}_clinical_report.json", "w") as f:
        json.dump({"walking_speed": 1.3, "cadence": 112, "step_length": 0.75}, f)

    return tmp_path


def _patch_paths(mocker, tmp_path, session_dir):
    """Helper to mock path resolution to point at tmp_path fixtures."""
    mocker.patch("qtm_mcp.tools.biomechanics.get_project_patient_dir", return_value=str(tmp_path))
    mocker.patch("qtm_mcp.tools.analytics.get_project_patient_dir", return_value=str(tmp_path))
    mocker.patch("qtm_mcp.tools.telemetry.get_project_patient_dir", return_value=str(tmp_path))
    mocker.patch("qtm_mcp.tools.clinical_output.get_project_patient_dir", return_value=str(tmp_path))

    mocker.patch("qtm_mcp.tools.biomechanics.safe_patient_path", return_value=session_dir)
    mocker.patch("qtm_mcp.tools.analytics.safe_patient_path", return_value=session_dir)
    mocker.patch("qtm_mcp.tools.telemetry.safe_patient_path", return_value=session_dir)
    mocker.patch("qtm_mcp.tools.clinical_output.safe_patient_path", return_value=session_dir)


# ════════════════════════════════════════════════════════════════════════════
#  Biomechanics Tests
# ════════════════════════════════════════════════════════════════════════════

class TestComputeJointAngles:
    @pytest.mark.asyncio
    async def test_reads_joint_specific_file(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await compute_joint_angles(VALID_PATIENT, VALID_DATE, "knee")
        assert result["joint"] == "knee"
        assert "flexion" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_generic_file(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        # Remove the specific file, force fallback
        (session_dir / "joint_angles_hip.json").unlink(missing_ok=True)
        result = await compute_joint_angles(VALID_PATIENT, VALID_DATE, "hip")
        assert result["joint"] == "all"

    @pytest.mark.asyncio
    async def test_invalid_patient_raises(self):
        with pytest.raises(ValueError):
            await compute_joint_angles("../../evil", VALID_DATE, "knee")


class TestComputeCopTrajectory:
    @pytest.mark.asyncio
    async def test_reads_cop_file(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await compute_cop_trajectory(VALID_PATIENT, VALID_DATE)
        assert "cop_x" in result
        assert "cop_y" in result

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, mocker, tmp_path):
        empty_dir = tmp_path / VALID_PATIENT / VALID_DATE
        empty_dir.mkdir(parents=True)
        _patch_paths(mocker, tmp_path, empty_dir)
        with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
            await compute_cop_trajectory(VALID_PATIENT, VALID_DATE)


# ════════════════════════════════════════════════════════════════════════════
#  Analytics Tests
# ════════════════════════════════════════════════════════════════════════════

class TestExportTimeseries:
    @pytest.mark.asyncio
    async def test_aggregates_json_files(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await export_timeseries(VALID_PATIENT, VALID_DATE, "json")
        assert result["status"] == "success"
        assert result["format"] == "json"
        assert "data" in result


class TestSegmentGaitCycles:
    @pytest.mark.asyncio
    async def test_reads_gait_cycles(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await segment_gait_cycles(VALID_PATIENT, VALID_DATE)
        assert "cycles" in result

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, mocker, tmp_path):
        empty_dir = tmp_path / VALID_PATIENT / VALID_DATE
        empty_dir.mkdir(parents=True)
        _patch_paths(mocker, tmp_path, empty_dir)
        with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
            await segment_gait_cycles(VALID_PATIENT, VALID_DATE)


class TestCompareSessions:
    @pytest.mark.asyncio
    async def test_computes_deltas(self, mocker, session_dir_pair):
        tmp_path = session_dir_pair
        pre_dir = tmp_path / VALID_PATIENT / "2026-01-10"
        post_dir = tmp_path / VALID_PATIENT / "2026-06-10"

        mocker.patch("qtm_mcp.tools.analytics.get_project_patient_dir", return_value=str(tmp_path))
        # safe_patient_path needs to return different dirs based on the date
        async def mock_safe_path(base, pid, date):
            return Path(base) / pid / date
        mocker.patch("qtm_mcp.tools.analytics.safe_patient_path", side_effect=mock_safe_path)

        result = await compare_sessions(VALID_PATIENT, "2026-01-10", "2026-06-10")
        assert result["status"] == "success"
        assert "deltas" in result
        # walking_speed delta should be 1.3 - 1.0 = 0.3
        assert abs(result["deltas"]["walking_speed"] - 0.3) < 0.01


class TestLookupNormativeData:
    @pytest.mark.asyncio
    async def test_returns_known_metric(self):
        result = await lookup_normative_data(35, "M", "knee_flexion")
        assert result["metric"] == "knee_flexion"
        assert result["mean"] == 65.0
        assert result["sd"] == 7.0
        assert result["range_low"] == 65.0 - 14.0
        assert result["range_high"] == 65.0 + 14.0

    @pytest.mark.asyncio
    async def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="(?i)available"):
            await lookup_normative_data(25, "F", "nonexistent_metric")


# ════════════════════════════════════════════════════════════════════════════
#  Telemetry Tests
# ════════════════════════════════════════════════════════════════════════════

class TestFillTrajectoryGaps:
    @pytest.mark.asyncio
    async def test_fills_gaps(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await fill_trajectory_gaps(VALID_PATIENT, VALID_DATE, 5)
        assert result["status"] == "success"
        assert "gaps_filled" in result

    @pytest.mark.asyncio
    async def test_invalid_patient_raises(self):
        with pytest.raises(ValueError):
            await fill_trajectory_gaps("../../evil", VALID_DATE, 5)


class TestFilterSignals:
    @pytest.mark.asyncio
    async def test_filters_signal_data(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await filter_signals(VALID_PATIENT, VALID_DATE, "emg", 6.0)
        assert result["status"] == "success"
        assert result["filter_applied"] == "moving_average"
        assert "data" in result


# ════════════════════════════════════════════════════════════════════════════
#  Clinical Output Tests
# ════════════════════════════════════════════════════════════════════════════

class TestGeneratePdfReport:
    @pytest.mark.asyncio
    async def test_generates_report(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await generate_pdf_report(VALID_PATIENT, VALID_DATE)
        assert result["status"] == "success"
        assert "report_path" in result


class TestExportC3d:
    @pytest.mark.asyncio
    async def test_exports_data(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await export_c3d(VALID_PATIENT, VALID_DATE)
        assert result["status"] == "success"
        assert "export_path" in result


class TestPushToEhr:
    @pytest.mark.asyncio
    async def test_allowlist_blocks_unknown_endpoint(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        mock_settings = mocker.Mock()
        mock_settings.projects_root = str(session_dir.parent.parent)
        mock_settings.allowed_fhir_endpoints = ["https://approved.hospital.org/fhir"]
        mocker.patch("qtm_mcp.tools.clinical_output.get_settings", return_value=mock_settings)

        with pytest.raises(PermissionError, match="allowlist"):
            await push_to_ehr(VALID_PATIENT, VALID_DATE, "https://evil.example.com/fhir")

    @pytest.mark.asyncio
    async def test_posts_to_approved_endpoint(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)

        mock_settings = mocker.Mock()
        mock_settings.projects_root = str(session_dir.parent.parent)
        mock_settings.allowed_fhir_endpoints = ["https://approved.hospital.org/fhir"]
        mocker.patch("qtm_mcp.tools.clinical_output.get_settings", return_value=mock_settings)

        from qtm_mcp.utils import set_shared_client
        mock_client = mocker.AsyncMock()
        mock_response = mocker.Mock()
        mock_response.status_code = 201
        mock_response.raise_for_status = mocker.Mock()
        mock_client.post.return_value = mock_response
        set_shared_client(mock_client)

        result = await push_to_ehr(VALID_PATIENT, VALID_DATE, "https://approved.hospital.org/fhir")
        assert result["status"] == "success"


class TestUpdateClinicalNotes:
    @pytest.mark.asyncio
    async def test_appends_notes(self, mocker, session_dir):
        _patch_paths(mocker, session_dir.parent.parent, session_dir)
        result = await update_clinical_notes(
            VALID_PATIENT, VALID_DATE,
            "[AI-GENERATED CLINICAL NOTE]\nPatient shows improved gait symmetry."
        )
        assert result["status"] == "success"
        assert result["notes_count"] >= 1

        # Verify the file was written
        notes_file = session_dir / "clinical_notes.json"
        assert notes_file.exists()

    @pytest.mark.asyncio
    async def test_notes_length_limit(self):
        with pytest.raises(ValueError):
            await update_clinical_notes(VALID_PATIENT, VALID_DATE, "x" * 10001)


# ════════════════════════════════════════════════════════════════════════════
#  Category C: Graceful Offline Fallback Tests
# ════════════════════════════════════════════════════════════════════════════

class TestStartStopCaptureCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_breaker_returns_structured_error(self, mocker):
        from qtm_mcp.utils import set_shared_client

        mock_client = mocker.AsyncMock()
        mock_client.post.side_effect = RuntimeError(
            "Circuit Breaker OPEN: QTM REST API is temporarily unavailable."
        )
        set_shared_client(mock_client)

        result = await start_stop_capture("gait_trial_1", "start")
        assert result["status"] == "error"
        assert result["code"] == "CIRCUIT_BREAKER_OPEN"
        assert "Circuit Breaker" in result["message"]


class TestFetchQtmDataOffline:
    @pytest.mark.asyncio
    async def test_connection_failure_returns_structured_error(self, mocker):
        mocker.patch("qtm_mcp.tools.realtime.QTM_RT_AVAILABLE", True)

        async def mock_connect(*args, **kwargs):
            raise OSError("Connection refused")

        mocker.patch("qtm_rt.connect", side_effect=mock_connect)

        result = await fetch_qtm_data(["3d"], 2)
        assert result["status"] == "error"
        assert result["code"] == "CONNECTION_FAILED"
        assert result["frames_collected"] == 0

    @pytest.mark.asyncio
    async def test_no_qtm_rt_raises_runtime_error(self, mocker):
        mocker.patch("qtm_mcp.tools.realtime.QTM_RT_AVAILABLE", False)
        with pytest.raises(RuntimeError, match="qtm-rt"):
            await fetch_qtm_data(["3d"], 2)


# ════════════════════════════════════════════════════════════════════════════
#  Stdout Pollution Audit
# ════════════════════════════════════════════════════════════════════════════

class TestStdoutPollution:
    """Verify that NO tool module contains print() statements."""

    def test_no_print_in_tools(self):
        tools_dir = Path(__file__).parent.parent / "src" / "qtm_mcp" / "tools"
        violations = []
        for py_file in tools_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                # Skip comments and strings
                if stripped.startswith("#"):
                    continue
                if "print(" in stripped and not stripped.startswith("#"):
                    violations.append(f"{py_file.name}:{i}: {stripped}")

        assert not violations, (
            "Stdout pollution detected! The following lines use print():\n"
            + "\n".join(violations)
        )

    def test_no_print_in_server(self):
        """Ensure server.py has no executable print() calls (docstrings are OK)."""
        import ast
        server_file = Path(__file__).parent.parent / "src" / "qtm_mcp" / "server.py"
        content = server_file.read_text(encoding="utf-8")
        tree = ast.parse(content)
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    violations.append(f"server.py:{node.lineno}")
        assert not violations, (
            "Stdout pollution in server.py: print() calls at " + ", ".join(violations)
        )
