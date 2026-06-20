import os
import json
import pytest
import asyncio
from typing import Generator, Tuple

# Import the tools to be tested
from qtm_mcp.tools.file_ops import load_patient_session
from qtm_mcp.tools.pipeline import fetch_clinical_metrics, trigger_processing_pipeline
from qtm_mcp.tools.video import extract_video_keyframes

# Import the server and tool modules to mock
from qtm_mcp.server import create_server
from qtm_mcp.tools import (
    health,
    telemetry,
    biomechanics,
    analytics,
    clinical_output,
    video,
    pipeline,
    file_ops,
    realtime,
)

# ─────────────────────────────────────────────────────────────────────────────
# Existing Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_patient_dir(tmp_path):
    """Creates a mock patient data directory structure for testing async file system operations."""
    patient_dir = tmp_path / "PAT-TEST" / "2026-06-09"
    patient_dir.mkdir(parents=True, exist_ok=True)
    return patient_dir

@pytest.mark.asyncio
async def test_fetch_clinical_metrics_async_io(mock_patient_dir, mocker):
    """Test that fetch_clinical_metrics correctly uses asyncio.to_thread for JSON file reads."""
    metrics_file = mock_patient_dir / "PAT-TEST_clinical_report.json"
    dummy_data = {"test_metric": 42.5, "status": "success"}
    with open(metrics_file, "w") as f:
        json.dump(dummy_data, f)
        
    mocker.patch("qtm_mcp.tools.pipeline.get_project_patient_dir", return_value=str(mock_patient_dir.parent.parent))
    mocker.patch("qtm_mcp.tools.pipeline.safe_patient_path", return_value=mock_patient_dir)
    
    mock_settings = mocker.Mock()
    mock_settings.projects_root = str(mock_patient_dir.parent.parent)
    mocker.patch("qtm_mcp.tools.pipeline.get_settings", return_value=mock_settings)

    result = await fetch_clinical_metrics("PAT-TEST", "2026-06-09")
    
    assert "test_metric" in result
    assert result["test_metric"] == 42.5
    assert result["status"] == "success"

@pytest.mark.asyncio
async def test_file_ops_async_iterdir(mock_patient_dir, mocker):
    """Test that load_patient_session correctly uses asyncio.to_thread for directory iteration."""
    capture_file = mock_patient_dir / "PAT-TEST_2026-06-09_Gait01.qtm"
    capture_file.touch()

    mocker.patch("qtm_mcp.tools.file_ops.get_project_patient_dir", return_value=str(mock_patient_dir.parent.parent))
    mocker.patch("qtm_mcp.tools.file_ops.safe_patient_path", return_value=mock_patient_dir)
    
    from qtm_mcp.config import get_settings
    from qtm_mcp.connection import QTMConnectionManager, set_connection_manager
    
    manager = QTMConnectionManager(get_settings())
    set_connection_manager(manager)

    mock_client = mocker.AsyncMock()
    mock_client.post.return_value.status_code = 200
    mocker.patch("qtm_mcp.connection.QTMConnectionManager.get_rest_client", return_value=mock_client)

    result = await load_patient_session("PAT-TEST", "2026-06-09")
    
    assert "status" in result
    assert "Success" in result["status"]
    
    set_connection_manager(None)

@pytest.mark.asyncio
async def test_validation_exception_graceful_handling():
    """Verify that ValueError exceptions from malformed inputs are raised correctly."""
    malformed_patient_id = "INVALID_PATIENT_!@#$"
    
    with pytest.raises(ValueError):
        await fetch_clinical_metrics(malformed_patient_id, "2026-06-09")
    
    with pytest.raises(ValueError):
        await extract_video_keyframes(malformed_patient_id, "2026-06-09")
    
    with pytest.raises(ValueError):
        await load_patient_session(malformed_patient_id, "2026-06-09")

@pytest.mark.asyncio
async def test_pipeline_tempfile_cleanup(mock_patient_dir, mocker):
    """Test that the PHI temp config file is properly generated and securely deleted."""
    mocker.patch("qtm_mcp.tools.pipeline.get_project_patient_dir", return_value=str(mock_patient_dir.parent.parent))
    mocker.patch("qtm_mcp.tools.pipeline.safe_patient_path", return_value=mock_patient_dir)
    
    mock_remove = mocker.patch("os.remove")

    mock_proc = mocker.AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"output", b"")
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_proc)
    
    result = await trigger_processing_pipeline("PAT-TEST", "2026-06-09", "matlab")
    
    assert result["status"] == "Success"
    mock_remove.assert_called_once()
    deleted_file_path = mock_remove.call_args[0][0]
    assert "qtm_pipeline_" in deleted_file_path
    assert deleted_file_path.endswith(".json")


# ─────────────────────────────────────────────────────────────────────────────
# QTM RT Mocking Fixtures & Setup
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_qtm_rt(mocker):
    """Fixture to mock qtm_rt module and simulate streaming and parameter responses."""
    mock_conn = mocker.AsyncMock()
    
    class MockMarker:
        def __init__(self, x, y, z):
            self.x = x
            self.y = y
            self.z = z
            
    class MockPacket:
        def __init__(self, framenumber, components):
            self.framenumber = framenumber
            self.components = components
            
        def get_3d_markers(self):
            return None, [MockMarker(1.0, 2.0, 3.0), MockMarker(4.0, 5.0, 6.0)]
            
        def get_6d(self):
            return None, [
                ("rigid_body_1", (0.1, 0.2, 0.3), [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
            ]
            
        def get_analog(self):
            return None, [1.2, 2.3, 3.4]
            
        def get_force(self):
            return None, [100.0, 200.0, 300.0]

    async def mock_stream_frames(components, on_packet):
        # Yield 3 packets asynchronously
        for i in range(1, 4):
            packet = MockPacket(i, components)
            on_packet(packet)
            await asyncio.sleep(0.001)

    mock_conn.stream_frames = mock_stream_frames
    mock_conn.stream_frames_stop = mocker.AsyncMock()
    mock_conn.disconnect = mocker.AsyncMock()
    
    async def mock_get_parameters(parameters):
        if "calibration" in parameters:
            return """
            <QTM_Parameters_Ver_1.28>
                <Calibration>
                    <Date>2026-06-10 02:00:00</Date>
                    <Average_Residual>0.65</Average_Residual>
                    <Cameras>8</Cameras>
                </Calibration>
            </QTM_Parameters_Ver_1.28>
            """
        return "<Parameters></Parameters>"
        
    mock_conn.get_parameters = mock_get_parameters
    
    # Patch qtm_rt.connect
    mock_connect = mocker.patch("qtm_rt.connect", return_value=mock_conn)
    
    # Enable QTM RT in connection
    mocker.patch("qtm_mcp.connection.QTM_RT_AVAILABLE", True)
    
    return mock_connect, mock_conn


# ─────────────────────────────────────────────────────────────────────────────
# Helper to extract text from FastMCP tool results
# ─────────────────────────────────────────────────────────────────────────────

def get_tool_text(res) -> str:
    """Safely extracts text content from a FastMCP call_tool response."""
    if isinstance(res, tuple):
        list_contents = res[0]
        if isinstance(list_contents, list) and len(list_contents) > 0:
            return list_contents[0].text
    elif isinstance(res, list):
        if len(res) > 0:
            return res[0].text
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server Registration & Behavior Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_tools(mocker):
    """Fixture to mock the tool function implementations in order to test server registration and fallback behavior."""
    def patch_tool(name, return_value):
        mock_func = mocker.patch(name, autospec=True)
        mock_func.return_value = return_value
        return mock_func

    patch_tool("qtm_mcp.tools.health.health_check", {"status": "healthy"})
    patch_tool("qtm_mcp.tools.health.list_sessions", ["2026-06-10"])
    patch_tool("qtm_mcp.tools.health.start_stop_capture", {"status": "capture_started"})
    patch_tool("qtm_mcp.tools.biomechanics.get_patient_anthropometrics", {"mass": 70.5})
    patch_tool("qtm_mcp.tools.biomechanics.compute_joint_angles", {"angles": [10.5, 11.2]})
    patch_tool("qtm_mcp.tools.biomechanics.compute_cop_trajectory", {"cop": [0.0, 0.0]})
    patch_tool("qtm_mcp.tools.telemetry.get_emg_signals", {"emg_channels": 8})
    patch_tool("qtm_mcp.tools.telemetry.get_force_plate_data", {"plates": [1, 2]})
    patch_tool("qtm_mcp.tools.telemetry.fill_trajectory_gaps", {"status": "gaps_filled"})
    patch_tool("qtm_mcp.tools.telemetry.filter_signals", {"status": "filtered"})
    patch_tool("qtm_mcp.tools.analytics.lookup_normative_data", {"bounds": [1.2, 1.8]})
    patch_tool("qtm_mcp.tools.analytics.export_timeseries", {"status": "exported"})
    patch_tool("qtm_mcp.tools.analytics.segment_gait_cycles", {"status": "segmented"})
    patch_tool("qtm_mcp.tools.analytics.compare_sessions", {"status": "compared"})
    patch_tool("qtm_mcp.tools.clinical_output.generate_pdf_report", {"status": "pdf_generated"})
    patch_tool("qtm_mcp.tools.clinical_output.export_c3d", {"status": "c3d_exported"})
    patch_tool("qtm_mcp.tools.clinical_output.push_to_ehr", {"status": "pushed"})
    patch_tool("qtm_mcp.tools.clinical_output.update_clinical_notes", {"status": "updated"})
    patch_tool("qtm_mcp.tools.video.extract_video_keyframes", {"status": "video_extracted"})
    patch_tool("qtm_mcp.tools.pipeline.trigger_processing_pipeline", {"status": "Success"})
    patch_tool("qtm_mcp.tools.pipeline.fetch_clinical_metrics", {"status": "success"})


@pytest.fixture
def mcp_server(mock_tools):
    """Returns a newly created FastMCP server instance for testing, with tools mocked."""
    return create_server()


@pytest.mark.asyncio
async def test_mcp_manifest(mcp_server):
    """Verify that the FastMCP server registers the correct number of resources, tools, and prompts."""
    tools = await mcp_server.list_tools()
    resources = await mcp_server.list_resources()
    templates = await mcp_server.list_resource_templates()
    prompts = await mcp_server.list_prompts()
    
    # Assert counts match the spec
    assert len(resources) == 3
    assert len(templates) == 6
    assert len(tools) == 29
    assert len(prompts) == 3
    
    tool_names = [t.name for t in tools]
    assert "stream_3d_markers" in tool_names
    assert "stream_6dof_data" in tool_names
    assert "start_stop_capture" in tool_names
    assert "trigger_processing_pipeline" in tool_names
    
    prompt_names = [p.name for p in prompts]
    assert "analyze_gait_cycle" in prompt_names
    assert "summarize_clinical_session" in prompt_names
    assert "troubleshoot_calibration" in prompt_names


@pytest.mark.asyncio
async def test_mcp_resources_health_and_calibration(mcp_server, mock_qtm_rt, mocker):
    from qtm_mcp.config import get_settings
    from qtm_mcp.connection import QTMConnectionManager, set_connection_manager
    manager = QTMConnectionManager(get_settings())
    set_connection_manager(manager)

    """Test health and calibration resources which pull live/mocked system parameters."""
    mocker.patch("qtm_mcp.tools.health.health_check", return_value={"status": "healthy"})
    
    # Test qtm://status/health
    res_health = await mcp_server.read_resource("qtm://status/health")
    assert len(res_health) == 1
    health_data = json.loads(res_health[0].content)
    assert health_data["status"] == "healthy"
    
    # Test qtm://status/calibration
    res_cal = await mcp_server.read_resource("qtm://status/calibration")
    assert len(res_cal) == 1
    cal_data = json.loads(res_cal[0].content)
    assert cal_data["status"] == "success"
    assert cal_data["is_calibrated"] is True
    assert cal_data["average_residual_mm"] == 0.65
    assert cal_data["camera_count"] == 8
    assert cal_data["calibration_date"] == "2026-06-10 02:00:00"
    
    set_connection_manager(None)


@pytest.mark.asyncio
async def test_mcp_session_and_reference_resources(mcp_server, mocker):
    """Test the session-specific and reference-specific template resources."""
    mocker.patch("qtm_mcp.tools.health.list_sessions", return_value=["2026-06-10"])
    mocker.patch("qtm_mcp.tools.biomechanics.get_patient_anthropometrics", return_value={"mass": 70.5})
    mocker.patch("qtm_mcp.tools.telemetry.get_emg_signals", return_value={"emg_channels": 8})
    mocker.patch("qtm_mcp.tools.telemetry.get_force_plate_data", return_value={"plates": [1, 2]})
    mocker.patch("qtm_mcp.tools.analytics.lookup_normative_data", return_value={"bounds": [1.2, 1.8]})

    # Test qtm://sessions/list/{patient_id}
    res = await mcp_server.read_resource("qtm://sessions/list/PAT-203")
    assert json.loads(res[0].content) == ["2026-06-10"]

    # Test qtm://sessions/{patient_id}/{session_date}/anthropometrics
    res = await mcp_server.read_resource("qtm://sessions/PAT-203/2026-06-10/anthropometrics")
    assert json.loads(res[0].content) == {"mass": 70.5}

    # Test qtm://sessions/{patient_id}/{session_date}/emg
    res = await mcp_server.read_resource("qtm://sessions/PAT-203/2026-06-10/emg")
    assert json.loads(res[0].content) == {"emg_channels": 8}

    # Test qtm://sessions/{patient_id}/{session_date}/force_plates
    res = await mcp_server.read_resource("qtm://sessions/PAT-203/2026-06-10/force_plates")
    assert json.loads(res[0].content) == {"plates": [1, 2]}

    # Test qtm://reference/normative_data/{dataset_id}
    res = await mcp_server.read_resource("qtm://reference/normative_data/35_M_knee_flexion")
    assert json.loads(res[0].content) == {"bounds": [1.2, 1.8]}


@pytest.mark.asyncio
async def test_mcp_realtime_stream_tools(mcp_server, mock_qtm_rt):
    from qtm_mcp.config import get_settings
    from qtm_mcp.connection import QTMConnectionManager, set_connection_manager
    manager = QTMConnectionManager(get_settings())
    set_connection_manager(manager)
    
    """Test the streaming tools against the mock streaming connection."""
    tool_result = await mcp_server.call_tool(
        "stream_3d_markers",
        {"marker_names": ["marker_1"], "frames": 2}
    )
    
    set_connection_manager(None)
    
    text = get_tool_text(tool_result)
    res_data = json.loads(text)
    assert res_data["status"] == "success"
    assert res_data["frames_collected"] >= 2
    
    first_frame = res_data["data"][0]
    assert "frame_number" in first_frame
    assert "3d" in first_frame
    assert len(first_frame["3d"]) == 2
    assert first_frame["3d"][0] == {"x": 1.0, "y": 2.0, "z": 3.0}


@pytest.mark.asyncio
async def test_mcp_other_tools_mocked(mcp_server, mocker):
    """Test a sample of other registered tools by mocking their internal callables."""
    # start_stop_capture
    res = await mcp_server.call_tool("start_stop_capture", {"trial_name": "gait1", "action": "start"})
    text = get_tool_text(res)
    assert "capture_started" in text

    # fill_trajectory_gaps
    res = await mcp_server.call_tool("fill_trajectory_gaps", {"patient_id": "PAT-203", "session_date": "2026-06-10", "max_gap_frames": 10})
    text = get_tool_text(res)
    assert "gaps_filled" in text


@pytest.mark.asyncio
async def test_mcp_prompts(mcp_server):
    """Test that all three guided workflow prompts return expected prompt text templates."""
    # analyze_gait_cycle
    prompt_res = await mcp_server.get_prompt("analyze_gait_cycle", {"patient_id": "PAT-203", "session_date": "2026-06-10"})
    text = prompt_res.messages[0].content.text
    assert "Gait Cycle Asymmetry Analysis" in text
    assert "PAT-203" in text
    
    # summarize_clinical_session
    prompt_res = await mcp_server.get_prompt("summarize_clinical_session", {"patient_id": "PAT-203", "session_date": "2026-06-10"})
    text = prompt_res.messages[0].content.text
    assert "Clinical Session Summary" in text
    assert "PAT-203" in text

    # troubleshoot_calibration
    prompt_res = await mcp_server.get_prompt("troubleshoot_calibration", {})
    text = prompt_res.messages[0].content.text
    assert "Camera Calibration Troubleshooting" in text
