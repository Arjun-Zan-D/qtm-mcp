import json
import pytest
from pathlib import Path
from unittest.mock import patch
from qtm_mcp.tools import clinical_output
from qtm_mcp.config import get_settings

VALID_PATIENT = "PATIENT-1"
VALID_DATE = "2026-05-10"

class TestClinicalOutput:
    @pytest.fixture(autouse=True)
    def setup_mocks(self, tmp_path):
        self.tmp_path = tmp_path
        session_dir = tmp_path / VALID_PATIENT / VALID_DATE
        session_dir.mkdir(parents=True)
        self.session_dir = session_dir

        # Write a dummy clinical report for tools that need it
        with open(session_dir / f"{VALID_PATIENT}_clinical_report.json", "w") as f:
            json.dump({"walking_speed": 1.2, "cadence": 105}, f)

        self.patcher_safe = patch("qtm_mcp.tools.clinical_output.safe_patient_path")
        self.mock_safe_path = self.patcher_safe.start()
        self.mock_safe_path.return_value = session_dir  # Return a Path object

        self.patcher_proj = patch("qtm_mcp.tools.clinical_output.get_project_patient_dir")
        self.mock_proj_dir = self.patcher_proj.start()
        self.mock_proj_dir.return_value = str(tmp_path)

        yield
        self.patcher_safe.stop()
        self.patcher_proj.stop()

    @pytest.mark.asyncio
    async def test_push_to_ehr_allowlist(self):
        settings = get_settings()
        # Ensure allowlist is empty initially
        settings.allowed_fhir_endpoints = []

        with pytest.raises(PermissionError, match="not in the approved allowlist"):
            await clinical_output.push_to_ehr(VALID_PATIENT, VALID_DATE, "https://unauthorized.ehr.com/fhir")

    @pytest.mark.asyncio
    async def test_update_clinical_notes_size_limit(self):
        long_note = "A" * 10001
        with pytest.raises(ValueError, match="Notes exceed 10000 character limit"):
            await clinical_output.update_clinical_notes(VALID_PATIENT, VALID_DATE, long_note)

    @pytest.mark.asyncio
    async def test_update_clinical_notes_valid(self):
        result = await clinical_output.update_clinical_notes(
            VALID_PATIENT, VALID_DATE, "Patient shows improved gait speed."
        )
        assert result["status"] == "success"
        assert result["notes_count"] >= 1

        # Verify the notes file was written
        notes_file = self.session_dir / "clinical_notes.json"
        assert notes_file.exists()
