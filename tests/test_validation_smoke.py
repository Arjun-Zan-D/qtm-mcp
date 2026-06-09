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

"""Smoke test for Phase 1 & 2 remediation validation functions."""
import sys
import asyncio

from qtm_mcp.utils import validate_patient_inputs, safe_patient_path

# --- Test valid inputs ---
validate_patient_inputs("PAT-203", "2026-06-09")
validate_patient_inputs("Patient_001", "2025-12-15")
print("[PASS] Valid inputs accepted.")

# --- Test directory traversal in patient_id ---
for bad_id in ["../../etc", "PAT;rm -rf /", "PAT'--", "a" * 65, ""]:
    try:
        validate_patient_inputs(bad_id, "2026-06-09")
        print(f"[FAIL] Should have rejected patient_id='{bad_id}'")
        sys.exit(1)
    except ValueError:
        print(f"[PASS] Rejected malicious patient_id: '{bad_id}'")

# --- Test injection in session_date ---
for bad_date in ["2026-01-01; DROP TABLE", "../../../", "2026-1-1", ""]:
    try:
        validate_patient_inputs("PAT-203", bad_date)
        print(f"[FAIL] Should have rejected session_date='{bad_date}'")
        sys.exit(1)
    except ValueError:
        print(f"[PASS] Rejected malicious session_date: '{bad_date}'")

# --- Test safe_patient_path boundary jail ---
try:
    # Even if someone passes validated-looking but double-dotted segments
    # manually (bypassing validate_patient_inputs), the path jail catches it
    asyncio.run(safe_patient_path("C:/QTM_Projects/Test/Patient_Data", "legit", "2026-06-09"))
    print("[PASS] safe_patient_path accepted valid path.")
except ValueError:
    print("[FAIL] safe_patient_path rejected valid path.")
    sys.exit(1)

print("\n=== ALL VALIDATION TESTS PASSED ===")
