import sys
import logging
import asyncio
import functools
from contextlib import asynccontextmanager
import httpx

from mcp.server.fastmcp import FastMCP
from qtm_mcp.config import get_settings
from qtm_mcp.utils import set_shared_client

# ── Logging guardrail ────────────────────────────────────────────────────────
# MCP uses stdin/stdout as its JSON-RPC transport.  ALL log output MUST be
# directed to stderr to avoid corrupting the protocol framing.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(stream=sys.stderr),
    ],
)

logger = logging.getLogger("Universal_QTM_Server")

@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Lifespan context manager to handle shared resources like httpx clients."""
    settings = get_settings()
    logger.info(f"Server starting. QTM REST target: {settings.qtm_rest_url}")
    client = httpx.AsyncClient(
        base_url=settings.qtm_rest_url,
        timeout=httpx.Timeout(5.0, connect=2.0),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )
    set_shared_client(client)
    try:
        yield
    finally:
        logger.info("Server shutting down — cleaning up resources.")
        await client.aclose()
        set_shared_client(None)

def with_timeout(seconds: float = 300.0):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Tool '{func.__name__}' exceeded {seconds}s timeout")
        return wrapper
    return decorator

def create_server() -> FastMCP:
    server = FastMCP("Universal_QTM_Server", lifespan=server_lifespan)
    
    try:
        from qtm_mcp.tools import file_ops, realtime, video, pipeline
        from qtm_mcp.tools import health, telemetry, biomechanics, analytics, clinical_output
        
        # Explicit registration instead of global decorators
        server.tool()(with_timeout(60.0)(file_ops.load_patient_session))
        server.tool()(with_timeout(10.0)(realtime.fetch_qtm_data))
        server.tool()(with_timeout(120.0)(video.extract_video_keyframes))
        server.tool()(with_timeout(300.0)(pipeline.trigger_processing_pipeline))
        server.tool()(with_timeout(60.0)(pipeline.fetch_clinical_metrics))

        # Health
        server.tool()(with_timeout(10.0)(health.health_check))
        server.tool()(with_timeout(10.0)(health.list_sessions))
        server.tool()(with_timeout(10.0)(health.start_stop_capture))
        server.tool()(with_timeout(10.0)(health.get_calibration_status))

        # Telemetry
        server.tool()(with_timeout(60.0)(telemetry.get_emg_signals))
        server.tool()(with_timeout(60.0)(telemetry.get_force_plate_data))
        server.tool()(with_timeout(120.0)(telemetry.fill_trajectory_gaps))
        server.tool()(with_timeout(60.0)(telemetry.filter_signals))

        # Biomechanics
        server.tool()(with_timeout(10.0)(biomechanics.get_patient_anthropometrics))
        server.tool()(with_timeout(120.0)(biomechanics.compute_joint_angles))
        server.tool()(with_timeout(120.0)(biomechanics.compute_cop_trajectory))

        # Analytics
        server.tool()(with_timeout(120.0)(analytics.export_timeseries))
        server.tool()(with_timeout(120.0)(analytics.segment_gait_cycles))
        server.tool()(with_timeout(60.0)(analytics.compare_sessions))
        server.tool()(with_timeout(10.0)(analytics.lookup_normative_data))

        # Clinical Output
        server.tool()(with_timeout(120.0)(clinical_output.generate_pdf_report))
        server.tool()(with_timeout(120.0)(clinical_output.export_c3d))
        server.tool()(with_timeout(60.0)(clinical_output.push_to_ehr))
        server.tool()(with_timeout(30.0)(clinical_output.update_clinical_notes))
        
        logger.info("Successfully registered all modular MCP tools.")
    except ImportError as e:
        logger.critical(f"Critical error registering modular tools: {str(e)}")
        raise e
        
    return server

def main():
    """CLI entrypoint for running the modular Universal QTM MCP Server."""
    logger.info("Launching Universal QTM MCP Server over stdio...")
    server = create_server()
    server.run()

if __name__ == "__main__":
    main()
