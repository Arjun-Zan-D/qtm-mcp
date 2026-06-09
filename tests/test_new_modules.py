import pytest
from unittest.mock import patch
from qtm_mcp.tools import clinical_output
from qtm_mcp.config import get_settings

class TestClinicalOutput:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.patcher = patch("qtm_mcp.tools.clinical_output.safe_patient_path")
        self.mock_safe_path = self.patcher.start()
        # Mock it to return a dummy path so it doesn't do disk I/O in the test
        self.mock_safe_path.return_value = "/dummy/path"
        yield
        self.patcher.stop()

    @pytest.mark.asyncio
    async def test_push_to_ehr_allowlist(self):
        settings = get_settings()
        # Ensure allowlist is empty initially
        settings.allowed_fhir_endpoints = []
        
        with pytest.raises(PermissionError, match="not in the approved allowlist"):
            await clinical_output.push_to_ehr("PATIENT-1", "2026-05-10", "https://unauthorized.ehr.com/fhir")
        
        # Test with allowed endpoint (it should pass validation but raise NotImplementedError since it's a stub)
        settings.allowed_fhir_endpoints = ["https://approved.ehr.com/fhir"]
        with pytest.raises(NotImplementedError):
            await clinical_output.push_to_ehr("PATIENT-1", "2026-05-10", "https://approved.ehr.com/fhir")

    @pytest.mark.asyncio
    async def test_update_clinical_notes_size_limit(self):
        long_note = "A" * 10001
        with pytest.raises(ValueError, match="Notes exceed 10000 character limit"):
            await clinical_output.update_clinical_notes("PATIENT-1", "2026-05-10", long_note)

    @pytest.mark.asyncio
    async def test_update_clinical_notes_valid(self):
        # Passes size limit and auto-prepends prefix, then raises NotImplementedError.
        with pytest.raises(NotImplementedError):
            await clinical_output.update_clinical_notes("PATIENT-1", "2026-05-10", "Patient shows improved gait speed.")
