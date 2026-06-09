import os
import json
import pytest
import asyncio

# Import the tools to be tested
from qtm_mcp.tools.file_ops import load_patient_session
from qtm_mcp.tools.pipeline import fetch_clinical_metrics, trigger_processing_pipeline
from qtm_mcp.tools.video import extract_video_keyframes

@pytest.fixture
def mock_patient_dir(tmp_path):
    """Creates a mock patient data directory structure for testing async file system operations."""
    patient_dir = tmp_path / "PAT-TEST" / "2026-06-09"
    patient_dir.mkdir(parents=True, exist_ok=True)
    return patient_dir

@pytest.mark.asyncio
async def test_fetch_clinical_metrics_async_io(mock_patient_dir, mocker):
    """Test that fetch_clinical_metrics correctly uses asyncio.to_thread for JSON file reads."""
    # Write a mock clinical metrics file into the temp path
    metrics_file = mock_patient_dir / "PAT-TEST_clinical_report.json"
    dummy_data = {"test_metric": 42.5, "status": "success"}
    with open(metrics_file, "w") as f:
        json.dump(dummy_data, f)
        
    # Mock the directory resolution utilities to point to our pytest tmp_path
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
    # Create a mock .qtm capture file
    capture_file = mock_patient_dir / "PAT-TEST_2026-06-09_Gait01.qtm"
    capture_file.touch()

    mocker.patch("qtm_mcp.tools.file_ops.get_project_patient_dir", return_value=str(mock_patient_dir.parent.parent))
    mocker.patch("qtm_mcp.tools.file_ops.safe_patient_path", return_value=mock_patient_dir)
    
    # Mock httpx post to bypass actual networking during unit tests
    mock_post = mocker.patch("httpx.AsyncClient.post")
    mock_post.return_value.status_code = 200

    result = await load_patient_session("PAT-TEST", "2026-06-09")
    
    assert "status" in result
    assert "Success" in result["status"]

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
    
    # Patch os.remove to spy on it and verify the config file was cleaned up
    mock_remove = mocker.patch("os.remove")

    # Mock subprocess execution
    mock_proc = mocker.AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"output", b"")
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_proc)
    
    result = await trigger_processing_pipeline("PAT-TEST", "2026-06-09", "matlab")
    
    assert result["status"] == "Success"
    # Verify that os.remove was called to securely delete the temporary PHI file
    mock_remove.assert_called_once()
    deleted_file_path = mock_remove.call_args[0][0]
    assert "qtm_pipeline_" in deleted_file_path
    assert deleted_file_path.endswith(".json")
