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

"""Qualisys MCP Server — FastMCP implementation.

Capability map (per docs/qualisys_mcp_spec.md):
  Resources  – read-only data / system state endpoints (no side effects)
  Tools      – actions that trigger processing, mutations, or capture control
  Prompts    – guided LLM workflows for clinical review and diagnostics

Logging contract:
  ALL log output is routed EXCLUSIVELY to sys.stderr.
  print() is FORBIDDEN — it would corrupt the MCP JSON-RPC transport on stdout.
"""

import sys
import logging
import asyncio
import functools
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

from qtm_mcp.config import get_settings
from qtm_mcp.utils import set_shared_client
from qtm_mcp.connection import QTMConnectionManager, set_connection_manager

# ── Logging guardrail ────────────────────────────────────────────────────────
# MCP uses stdin/stdout as its JSON-RPC transport.  ALL log output MUST be
# directed to stderr to avoid corrupting the protocol framing.
# Reconfigure the root logger unconditionally so any downstream import that
# calls logging.getLogger() without explicit handlers also lands on stderr.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,  # Override any previously installed root handlers
)

logger = logging.getLogger("Universal_QTM_Server")


# ── Lifespan context manager ─────────────────────────────────────────────────

@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Manage shared resources (httpx client and RT connection) across the server lifetime."""
    settings = get_settings()
    logger.info("Server starting. QTM REST target: %s", settings.qtm_rest_url)

    manager = QTMConnectionManager(settings)
    await manager.startup()
    set_connection_manager(manager)

    try:
        yield
    finally:
        logger.info("Server shutting down — draining HTTP clients and RT connection.")
        await manager.shutdown()
        set_connection_manager(None)
        logger.info("Shutdown complete.")


# ── Timeout decorator ────────────────────────────────────────────────────────

def with_timeout(seconds: float = 300.0):
    """Wrap an async callable so it raises TimeoutError after *seconds*."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Operation '{func.__name__}' exceeded the {seconds}s timeout."
                )
        return wrapper
    return decorator


# ── Server factory ───────────────────────────────────────────────────────────

def create_server() -> FastMCP:
    """Instantiate and fully register the Universal QTM FastMCP server.

    Registration order follows the spec:
      1. Resources  (qtm:// URIs for read-only data access)
      2. Tools      (side-effect actions)
      3. Prompts    (guided LLM workflows)
    """
    mcp = FastMCP("Universal_QTM_Server", lifespan=server_lifespan)

    # ── Import tool modules ──────────────────────────────────────────────────
    try:
        from qtm_mcp.tools import (
            file_ops,
            realtime,
            video,
            pipeline,
            health,
            telemetry,
            biomechanics,
            analytics,
            clinical_output,
            scripting,
        )
    except ImportError as exc:
        logger.critical("Failed to import tool modules: %s", exc)
        raise

    # ════════════════════════════════════════════════════════════════════════
    #  RESOURCES  —  qtm:// URI scheme, read-only, no side-effects
    # ════════════════════════════════════════════════════════════════════════

    # ── System state resources ───────────────────────────────────────────────

    @mcp.resource("qtm://status/health")
    async def resource_health_check() -> dict:
        """System health: QTM REST reachability, RT port status, MATLAB/OpenSim paths.

        Returns a snapshot of the system's operational status without
        modifying any state.  Refactored from the former ``health_check`` tool.
        """
        return await with_timeout(10.0)(health.health_check)()

    @mcp.resource("qtm://status/calibration")
    async def resource_calibration_status() -> dict:
        """Latest wand calibration error metrics from QTM.

        Returns camera calibration quality indicators so an LLM can determine
        whether the lab is ready for a new capture session.
        Refactored from the former ``get_calibration_status`` tool.
        """
        return await with_timeout(10.0)(health.get_calibration_status)()

    @mcp.resource("qtm://project/active")
    async def resource_active_project() -> dict:
        """The currently active QTM project path and metadata. Read-only."""
        return await with_timeout(10.0)(scripting.get_active_project_path)()

    @mcp.resource("qtm://project/files/{extension}")
    async def resource_project_files(extension: str) -> dict:
        """List of capture files in the active project, filtered by extension."""
        return await with_timeout(30.0)(scripting.list_capture_files)(f".{extension}")

    # ── Session data resources ───────────────────────────────────────────────

    @mcp.resource("qtm://sessions/list/{patient_id}")
    async def resource_list_sessions(patient_id: str):
        """Available session dates for *patient_id*.

        Returns an ordered list of YYYY-MM-DD strings so the LLM can choose
        which session to analyse.  Refactored from the former ``list_sessions``
        tool.
        """
        return await with_timeout(10.0)(health.list_sessions)(patient_id)

    @mcp.resource("qtm://sessions/{patient_id}/{session_date}/anthropometrics")
    async def resource_anthropometrics(patient_id: str, session_date: str) -> dict:
        """Static physical measurements (leg length, mass, joint widths) for the patient.

        Provides the body-segment parameters needed to scale biomechanical
        models such as OpenSim or to compute joint centres.
        Refactored from the former ``get_patient_anthropometrics`` tool.
        """
        return await with_timeout(10.0)(biomechanics.get_patient_anthropometrics)(patient_id)

    @mcp.resource("qtm://sessions/{patient_id}/{session_date}/emg")
    async def resource_emg_signals(patient_id: str, session_date: str) -> dict:
        """Delsys EMG time-series for all muscles in the session.

        Returns raw or processed electromyography data for muscle activation
        timing and amplitude analysis.
        """
        # No trial in the resource URI -- pass trial=None so telemetry reads
        # the session-level emg_data.json directly. Clients that need a
        # specific trial should invoke get_emg_signals as a tool with the
        # trial argument set explicitly.
        return await with_timeout(60.0)(telemetry.get_emg_signals)(
            patient_id, session_date, trial=None
        )

    @mcp.resource("qtm://sessions/{patient_id}/{session_date}/force_plates")
    async def resource_force_plates(patient_id: str, session_date: str) -> dict:
        """Ground reaction forces and centre-of-pressure data from all force plates.

        Returns Fx, Fy, Fz, and CoP arrays required for inverse-dynamics
        calculations.
        """
        # No trial in the resource URI -- pass trial=None so telemetry reads
        # the session-level force_plate_data.json directly.
        return await with_timeout(60.0)(telemetry.get_force_plate_data)(
            patient_id, session_date, trial=None
        )

    # ── Reference data resources ─────────────────────────────────────────────

    @mcp.resource("qtm://reference/normative_data/{dataset_id}")
    async def resource_normative_data(dataset_id: str) -> dict:
        """Age/sex-stratified normative reference bands for clinical metrics.

        The *dataset_id* encodes the cohort as ``{age}_{sex}_{metric}``,
        e.g. ``35_M_knee_flexion``.  Returns mean ± SD reference bounds.
        Refactored from the former ``lookup_normative_data`` tool.
        """
        # Parse composite dataset_id: <age>_<sex>_<metric>
        parts = dataset_id.split("_", 2)
        if len(parts) < 3:
            raise ValueError(
                "dataset_id must follow the pattern '<age>_<sex>_<metric>', "
                f"got: '{dataset_id}'"
            )
        try:
            age = int(parts[0])
        except ValueError:
            raise ValueError(f"Age component of dataset_id must be an integer, got '{parts[0]}'")
        sex = parts[1]
        metric = parts[2]
        return await with_timeout(10.0)(analytics.lookup_normative_data)(age, sex, metric)

    logger.info("Registered 7 MCP Resources under the qtm:// URI scheme.")

    # ════════════════════════════════════════════════════════════════════════
    #  TOOLS  —  actions, mutations, processing triggers, capture control
    # ════════════════════════════════════════════════════════════════════════

    # ── Scripting API (Discovery & File Ops) ─────────────────────────────────
    mcp.tool()(with_timeout(10.0)(scripting.get_active_project_path))
    mcp.tool()(with_timeout(30.0)(scripting.list_capture_files))
    mcp.tool()(with_timeout(10.0)(scripting.load_capture_file))
    
    # ── Scripting API (Trajectories & PAF) ───────────────────────────────────
    mcp.tool()(with_timeout(10.0)(scripting.find_trajectory))
    mcp.tool()(with_timeout(60.0)(scripting.get_trajectory_samples))
    mcp.tool()(with_timeout(300.0)(scripting.trigger_paf_analysis))
    
    # ── Scripting API (Settings) ─────────────────────────────────────────────
    mcp.tool()(with_timeout(10.0)(scripting.get_qtm_setting))
    mcp.tool()(with_timeout(10.0)(scripting.set_qtm_setting))

    # ── Capture control ──────────────────────────────────────────────────────
    mcp.tool()(with_timeout(10.0)(health.start_stop_capture))
    mcp.tool()(with_timeout(10.0)(health.set_qtm_event))

    # ── Session loading ──────────────────────────────────────────────────────
    mcp.tool()(with_timeout(60.0)(file_ops.load_patient_session))

    # ── Real-time data acquisition ───────────────────────────────────────────
    mcp.tool()(with_timeout(10.0)(realtime.stream_6dof_data))
    mcp.tool()(with_timeout(10.0)(realtime.stream_3d_markers))
    mcp.tool()(with_timeout(10.0)(realtime.stream_analog_data))
    mcp.tool()(with_timeout(10.0)(realtime.stream_skeleton_data))
    mcp.tool()(with_timeout(10.0)(realtime.fetch_qtm_data))

    # ── Video processing ─────────────────────────────────────────────────────
    mcp.tool()(with_timeout(120.0)(video.extract_video_keyframes))

    # ── Processing pipelines ─────────────────────────────────────────────────
    mcp.tool()(with_timeout(300.0)(pipeline.trigger_processing_pipeline))
    mcp.tool()(with_timeout(60.0)(pipeline.fetch_clinical_metrics))

    # ── Telemetry processing (mutating / triggers gap-fill / filter scripts) ─
    mcp.tool()(with_timeout(120.0)(telemetry.fill_trajectory_gaps))
    mcp.tool()(with_timeout(60.0)(telemetry.filter_signals))

    # ── Biomechanics computations ────────────────────────────────────────────
    mcp.tool()(with_timeout(120.0)(biomechanics.compute_joint_angles))
    mcp.tool()(with_timeout(120.0)(biomechanics.compute_cop_trajectory))

    # ── Analytics ────────────────────────────────────────────────────────────
    mcp.tool()(with_timeout(120.0)(analytics.export_timeseries))
    mcp.tool()(with_timeout(120.0)(analytics.segment_gait_cycles))
    mcp.tool()(with_timeout(60.0)(analytics.compare_sessions))

    # ── Clinical output ──────────────────────────────────────────────────────
    mcp.tool()(with_timeout(120.0)(clinical_output.generate_pdf_report))
    mcp.tool()(with_timeout(120.0)(clinical_output.export_c3d))
    mcp.tool()(with_timeout(60.0)(clinical_output.push_to_ehr))
    mcp.tool()(with_timeout(30.0)(clinical_output.update_clinical_notes))

    logger.info("Registered 18 MCP Tools.")

    # ════════════════════════════════════════════════════════════════════════
    #  PROMPTS  —  guided LLM workflows for clinical review and diagnostics
    # ════════════════════════════════════════════════════════════════════════

    @mcp.prompt()
    async def analyze_gait_cycle(patient_id: str, session_date: str) -> list:
        """Guided workflow: identify left/right gait asymmetries in a QTM session.

        Loads joint angles and force-plate data for *patient_id* on
        *session_date* and returns a structured prompt asking the LLM to
        identify kinematic and kinetic asymmetries, flag deviations from
        normative bands, and suggest clinical follow-up actions.

        Args:
            patient_id: The unique patient identifier (e.g. 'PAT-203').
            session_date: Session date in YYYY-MM-DD format.
        """
        logger.info(
            "Prompt 'analyze_gait_cycle' invoked for patient=%s date=%s",
            patient_id, session_date,
        )
        prompt_text = (
            f"# Gait Cycle Asymmetry Analysis\n\n"
            f"**Patient ID:** {patient_id}  \n"
            f"**Session Date:** {session_date}\n\n"
            "## Instructions\n"
            "You have access to the following MCP resources and tools for this patient:\n\n"
            "1. **Joint Angles** — call `compute_joint_angles` for joints: "
            "`knee`, `hip`, `ankle`, `pelvis` on both the left and right sides.\n"
            f"2. **Force Plates** — read resource `qtm://sessions/{patient_id}/{session_date}/force_plates` "
            "to obtain Fx, Fy, Fz, and Centre-of-Pressure arrays.\n"
            "3. **Normative Data** — query `qtm://reference/normative_data/<age>_<sex>_<metric>` "
            "to compare against age/sex-matched reference bands.\n"
            "4. **Gait Cycle Segmentation** — call `segment_gait_cycles` to normalise "
            "time-series to 0–100 % of the gait cycle.\n\n"
            "## Analysis Tasks\n"
            "- Identify any **left/right asymmetry** (threshold: > 10 % difference at peak values).\n"
            "- Flag joints where peak angles deviate more than **± 2 SD** from normative bands.\n"
            "- Evaluate the **Centre-of-Pressure trajectory** for mediolateral balance and "
            "foot-strike pattern anomalies.\n"
            "- Compare loading-response and push-off phases for symmetry.\n\n"
            "## Output Format\n"
            "Provide a structured clinical summary with:\n"
            "1. An executive summary (2–3 sentences).\n"
            "2. A table of asymmetry indices per joint.\n"
            "3. Specific clinical concerns and recommended follow-up assessments.\n"
        )
        return [TextContent(type="text", text=prompt_text)]

    @mcp.prompt()
    async def summarize_clinical_session(patient_id: str, session_date: str) -> list:
        """Guided workflow: draft a clinical EHR note from session metrics.

        Retrieves the clinical metrics file for *patient_id* on *session_date*
        and instructs the LLM to produce a compliant draft note ready for
        physician review and EHR submission.

        Args:
            patient_id: The unique patient identifier (e.g. 'PAT-203').
            session_date: Session date in YYYY-MM-DD format.
        """
        logger.info(
            "Prompt 'summarize_clinical_session' invoked for patient=%s date=%s",
            patient_id, session_date,
        )
        prompt_text = (
            f"# Clinical Session Summary — EHR Draft Note\n\n"
            f"**Patient ID:** {patient_id}  \n"
            f"**Session Date:** {session_date}\n\n"
            "## Instructions\n"
            "Retrieve the following data using the available MCP tools and resources:\n\n"
            "1. Call `fetch_clinical_metrics` to load the processed spatiotemporal "
            "parameters and peak joint angles for this session.\n"
            f"2. Read `qtm://sessions/{patient_id}/{session_date}/anthropometrics` for "
            "body-segment parameters (height, mass, leg length).\n"
            f"3. Read `qtm://sessions/{patient_id}/{session_date}/force_plates` for "
            "ground reaction force summary statistics.\n"
            f"4. Optionally read `qtm://sessions/{patient_id}/{session_date}/emg` for "
            "muscle activation timing if available.\n\n"
            "## Drafting Guidelines\n"
            "- Use formal clinical language suitable for inclusion in an HL7/FHIR "
            "DiagnosticReport resource.\n"
            "- Structure the note as: *Reason for Referral* → *Findings* → *Impression* "
            "→ *Recommendations*.\n"
            "- Quantify every finding (e.g. 'peak knee flexion 48° vs. normative 65 ± 7°').\n"
            "- Explicitly note data quality issues (missing markers, high residuals) where "
            "applicable.\n"
            "- Do **not** include the patient's name or date-of-birth — use only the "
            "anonymised patient_id.\n\n"
            "## Output Format\n"
            "Return the draft note as plain text, prefixed with the sentinel string:\n"
            "`[AI-GENERATED CLINICAL NOTE]`\n\n"
            "After generating the note, offer to call `update_clinical_notes` to persist "
            "it to the session record, or `push_to_ehr` to transmit it to the EHR endpoint."
        )
        return [TextContent(type="text", text=prompt_text)]

    @mcp.prompt()
    async def troubleshoot_calibration() -> list:
        """Guided workflow: diagnose camera calibration issues in QTM.

        Reads the current calibration status resource and provides the LLM
        with a structured decision tree for identifying the root cause of
        elevated residuals, poor marker visibility, or camera faults.
        """
        logger.info("Prompt 'troubleshoot_calibration' invoked.")
        prompt_text = (
            "# QTM Camera Calibration Troubleshooting\n\n"
            "## Step 1 — Retrieve Current Status\n"
            "Read the resource `qtm://status/calibration` to obtain the latest wand "
            "calibration error metrics (mean residual per camera, standard deviation, "
            "marker visibility counts).\n\n"
            "## Step 2 — Evaluate Residuals\n"
            "Apply the following thresholds:\n\n"
            "| Condition | Likely Cause | Action |\n"
            "|---|---|---|\n"
            "| Mean residual > 1.5 mm | Lens dirt / misalignment | Clean lenses; re-run wand calibration |\n"
            "| Single camera > 3× mean | Camera hardware fault | Check cable / sensor; swap unit |\n"
            "| Marker visibility < 50 % | Reflective interference | Dim ambient lighting; remove reflective objects |\n"
            "| Residual spikes at room edges | Volume coverage gap | Reposition cameras; increase overlap |\n\n"
            "## Step 3 — Check System Health\n"
            "Read `qtm://status/health` to verify:\n"
            "- QTM REST API is reachable (HTTP 200 on `/api/project`).\n"
            "- All cameras report `Connected` status.\n"
            "- MATLAB and OpenSim paths are correctly configured.\n\n"
            "## Step 4 — Re-calibration Decision\n"
            "If residuals exceed thresholds after cleaning:\n"
            "1. Perform a full dynamic wand calibration (minimum 1000 wand frames per camera).\n"
            "2. Perform a static L-frame calibration to establish the lab coordinate system.\n"
            "3. Re-read `qtm://status/calibration` to confirm improvement.\n\n"
            "## Output Format\n"
            "Provide:\n"
            "1. A pass/fail verdict for the current calibration.\n"
            "2. The specific camera IDs (if any) that require attention.\n"
            "3. Recommended actions in priority order.\n"
        )
        return [TextContent(type="text", text=prompt_text)]

    logger.info("Registered 3 MCP Prompts.")
    logger.info(
        "Universal_QTM_Server ready: 7 Resources | 17 Tools | 3 Prompts"
    )
    return mcp


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point — registered as `qtm-mcp` in pyproject.toml scripts."""
    logger.info("Launching Universal QTM MCP Server over stdio...")
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
