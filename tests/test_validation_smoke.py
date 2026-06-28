# Copyright (c) 2026 Arjun Singh Shishodia
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

"""Tests for Phase 1 & 2 remediation validation functions."""
import pytest
from qtm_mcp.utils import validate_patient_inputs, safe_patient_path

def test_valid_inputs_accepted():
    """Test that valid inputs pass validation."""
    validate_patient_inputs("PAT-203", "2026-06-09")
    validate_patient_inputs("Patient_001", "2025-12-15")

@pytest.mark.parametrize("bad_id", [
    "../../etc", 
    "PAT;rm -rf /", 
    "PAT'--", 
    "a" * 65, 
    ""
])
def test_directory_traversal_in_patient_id(bad_id):
    """Test that malicious patient IDs are rejected."""
    with pytest.raises(ValueError):
        validate_patient_inputs(bad_id, "2026-06-09")

@pytest.mark.parametrize("bad_date", [
    "2026-01-01; DROP TABLE", 
    "../../../", 
    "2026-1-1", 
    ""
])
def test_injection_in_session_date(bad_date):
    """Test that malicious session dates are rejected."""
    with pytest.raises(ValueError):
        validate_patient_inputs("PAT-203", bad_date)

@pytest.mark.asyncio
async def test_safe_patient_path_boundary_jail():
    """Test that safe_patient_path accepts a valid path."""
    path = await safe_patient_path("C:/QTM_Projects/Test/Patient_Data", "legit", "2026-06-09")
    assert path.name == "2026-06-09"
    assert path.parent.name == "legit"
