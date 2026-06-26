# Qualisys MCP (FastMCP) Specification

## 1. Overview
The `qtm-mcp` project provides a Universal Model Context Protocol (MCP) server for Qualisys Track Manager (QTM). The goal is to fully leverage the FastMCP (`mcp.server.fastmcp`) standard to expose QTM capabilities safely and efficiently to LLMs.

## 2. Current State Assessment
Based on a review of `pyproject.toml` and `src/qtm_mcp/server.py`:
*   **Dependencies:** The project appropriately uses `mcp` (`>=1.27,<2`), `httpx`, and `pydantic-settings`. It has domain-specific optional dependency groups (`vision`, `realtime`, `clinical`, `biomechanics`, `analytics`). The `qtm-rt` dependency is critical for real-time 6DOF and 3D data.
*   **Implementation:** `server.py` currently registers *all* functionality as MCP **Tools** using `server.tool()`. This is an anti-pattern in MCP, as many of these operations are better suited as **Resources** (for retrieving static or streaming data) or **Prompts** (for guided workflows).
*   **Logging:** The current setup successfully guards against `sys.stdout` pollution by explicitly routing all logs to `sys.stderr`. 

## 3. FastMCP Capability Mapping
To become a compliant and well-architected FastMCP server, the existing endpoints must be refactored into Tools, Resources, and Prompts.

### 3.1. Tools (Actions & Executions)
Tools should be reserved for side-effects, triggering processing, or complex parametric queries.
*   `health.start_stop_capture(action="start"|"stop")`
*   `pipeline.trigger_processing_pipeline(session_id)`
*   `telemetry.fill_trajectory_gaps(session_id, method="spline")`
*   `telemetry.filter_signals(session_id, type="butterworth")`
*   `biomechanics.compute_joint_angles(session_id, model="plug-in-gait")`
*   `clinical_output.push_to_ehr(patient_id, report_uri)`
*   `clinical_output.update_clinical_notes(patient_id, notes)`
*   `clinical_output.generate_pdf_report(session_id)`
*   `video.extract_video_keyframes(session_id)`

### 3.2. Resources (Data & State Access)
Resources expose static data, system state, or streams. The following current tools must be refactored into `@server.resource()` endpoints.
*   **System State:** 
    *   `qtm://status/health` (Refactored from `health.health_check`)
    *   `qtm://status/calibration` (Refactored from `health.get_calibration_status`)
*   **Session Data:**
    *   `qtm://sessions/list` (Refactored from `health.list_sessions`)
    *   `qtm://sessions/{session_id}/anthropometrics`
    *   `qtm://sessions/{session_id}/emg`
    *   `qtm://sessions/{session_id}/force_plates`
*   **Reference Data:**
    *   `qtm://reference/normative_data/{dataset_id}` (Refactored from `analytics.lookup_normative_data`)
*   *(Optional)* **Real-time Streams:** If FastMCP allows subscription, real-time 6DOF rigid body data and 3D coordinates can be mapped to a streaming resource (e.g., `qtm://realtime/stream`).

### 3.3. Prompts (Guided LLM Workflows)
Prompts give the LLM structured templates for interacting with QTM data. These need to be newly implemented using `@server.prompt()`.
*   **`analyze_gait_cycle`**: A prompt that asks the LLM to review joint angles and force plate data for a specific `session_id` and identify asymmetries.
*   **`summarize_clinical_session`**: A prompt that loads a session's clinical metrics and generates a draft note for the EHR.
*   **`troubleshoot_calibration`**: A prompt that retrieves the current calibration status and guides the LLM in diagnosing marker visibility or camera issues.

## 4. Refactoring Plan & Next Steps

### What is Missing
1.  **Resource Declarations:** No `@server.resource()` definitions exist.
2.  **Prompt Declarations:** No `@server.prompt()` definitions exist.
3.  **Real-Time Asynchronous Streams:** Proper usage of `qtm-rt` with `asyncio` to fetch streaming data needs to be verified.

### What Needs Refactoring
1.  **Tool Pruning:** Move read-only state endpoints out of the tool registry and into the resource registry.
2.  **Type Hinting & Pydantic:** Ensure all parameters for Tools and Resources are strongly typed with Pydantic models to generate valid JSON Schemas for the LLM.

### Priorities for the Dev Agent
1.  **Resource Migration:** Refactor `health_check`, `get_calibration_status`, and `list_sessions` into FastMCP resources.
2.  **Prompt Implementation:** Implement the `analyze_gait_cycle` and `summarize_clinical_session` prompts.
3.  **Async/QTM-RT Validation:** Ensure that `realtime.fetch_qtm_data` successfully leverages asynchronous HTTPX / QTM-RT connections without blocking the main event loop.
4.  **No Stdout Rule:** Constantly maintain the `stderr` logging boundary. The audit will fail immediately if `print()` statements are introduced.
