# QTM MCP v0.1.0 – Foundation Release

**Release Date:** 2026-06-28  
**License:** Apache 2.0  
**Python:** >= 3.10

---

## Overview

QTM MCP is an open-source Model Context Protocol (MCP) server that enables AI assistants to communicate directly with Qualisys Track Manager (QTM) — the industry-standard software for motion capture data acquisition and analysis.

This is the **first public release** of the project. It provides a stable foundation for researchers, biomechanics professionals, and AI developers to begin integrating large language models into motion capture workflows.

The project was developed and tested at **St. Xavier's Gait Lab** as the first building block of a larger vision to make motion capture software accessible through natural language.

---

## Highlights

- **30 MCP Tools** spanning session management, real-time streaming, signal processing, pipeline execution, and clinical reporting.
- **10 MCP Resources** providing read-only access to system health, calibration status, session listings, anthropometrics, telemetry, and normative reference data via `qtm://` URIs.
- **3 MCP Prompts** offering guided workflows for clinical gait analysis, biomechanics pipeline automation, and video-based postural inspection.
- **Clinical-grade security posture** — path traversal prevention, PHI hashing in logs, FHIR endpoint allowlisting, symlink rejection, and a strict fail-closed policy (no synthetic data generation on error).
- **Modular architecture** following the FastMCP specification with clean separation of Resources, Tools, and Prompts.

---

## Current Capabilities

### Stable Features
These features have been tested against real QTM installations and are considered stable for research use:

| Category | Tools | Description |
|---|---|---|
| **Session Management** | `load_patient_session` | Load `.qtm`/`.c3d` captures via QTM REST API |
| **Real-Time Streaming** | `stream_6dof_data`, `stream_3d_markers`, `stream_analog_data`, `stream_skeleton_data`, `fetch_qtm_data` | Live data streaming via `qtm-rt` SDK |
| **Scripting API** | `get_active_project_path`, `list_capture_files`, `load_capture_file`, `find_trajectory`, `get_trajectory_samples`, `trigger_paf_analysis`, `get_qtm_setting`, `set_qtm_setting` | Interact with QTM's Scripting API |
| **Health & Calibration** | `health_check`, `get_calibration_status`, `list_sessions`, `start_stop_capture`, `set_qtm_event` | System monitoring and capture control |
| **Telemetry** | `get_emg_signals`, `get_force_plate_data`, `fill_trajectory_gaps`, `filter_signals` | Analog signal retrieval and processing |
| **Biomechanics** | `get_patient_anthropometrics`, `compute_joint_angles`, `compute_cop_trajectory` | Kinematic and kinetic data access |
| **Analytics** | `export_timeseries`, `segment_gait_cycles`, `compare_sessions`, `lookup_normative_data` | Data analysis and normative comparison |
| **Clinical Output** | `generate_pdf_report`, `export_c3d`, `push_to_ehr`, `update_clinical_notes` | Reporting and EHR integration |

### Experimental Features
These features are functional but have limited real-world testing:

| Category | Tools | Notes |
|---|---|---|
| **Pipeline Execution** | `trigger_processing_pipeline` | Requires MATLAB or `opensim-cmd` in system PATH. Subprocess execution with security hardening. |
| **Video Analysis** | `extract_video_keyframes` | Requires `opencv-python`. Keyframe extraction from capture videos. |
| **FHIR/EHR Push** | `push_to_ehr` | Limited to DiagnosticReport resources. Requires pre-configured FHIR endpoint allowlist. |

---

## Known Limitations

- **Normative database is not stratified.** The `lookup_normative_data` tool accepts `age` and `sex` parameters but currently returns the same population-average values regardless. Age/sex stratification is planned for v0.5.x.
- **`filter_signals` uses a moving-average filter**, not a Butterworth filter. A more advanced digital filtering pipeline is planned.
- **Sequential HTTP requests in `get_trajectory_samples`.** Frame-by-frame fetching from the Scripting API is O(N) and may be slow for large frame ranges.
- **No PyPI distribution yet.** Installation is currently via editable mode (`pip install -e .[all]`). PyPI publishing is planned.
- **Single-platform CI.** GitHub Actions currently tests on `ubuntu-latest` only. Windows/macOS matrix testing is planned.

---

## What's Included

### New Files
- `ROADMAP.md` — Development roadmap through v1.0.0
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- `.github/RELEASE_TEMPLATE.md` — Standardized release notes template

### Documentation
- Professional README with badges, quick start guide, architecture overview, and complete configuration reference
- Clinical liability disclaimer (`DISCLAIMER.md`)
- Security policy with severity classifications and response timelines (`SECURITY.md`)
- Contributor guidelines (`CONTRIBUTING.md`)
- Keep-a-Changelog format changelog (`CHANGELOG.md`)

### Architecture
- **10 tool modules** under `src/qtm_mcp/tools/`
- **Pydantic-settings** configuration with environment variable overrides
- **Circuit breaker** HTTP client for resilient API communication
- **Connection manager** with async reconnection and thread-safe disconnect handling
- **81 automated tests** covering security, functionality, and protocol compliance

---

## Future Roadmap

See [ROADMAP.md](ROADMAP.md) for the full development plan. Key upcoming milestones:

- **v0.5.x** — Advanced filtering (Butterworth), stratified normative database, deeper force plate integration
- **v0.8.x** — Computer vision pipelines, AI-driven gait cycle segmentation, interactive visualizations
- **v1.0.0** — Extended FHIR support, plug-and-play tool extensibility, regulatory documentation

---

## Acknowledgments

This project is not affiliated with, endorsed by, or sponsored by Qualisys AB. Qualisys® and Qualisys Track Manager (QTM) are trademarks of their respective owners.

**Full Changelog**: https://github.com/Arjun-Zan-D/qtm-mcp/commits/v0.1.0
