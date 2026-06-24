import sys
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from qtm_mcp.config import get_settings

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
    """Lifespan context manager for shared server resources.

    Eagerly resolves Settings on startup so any malformed `.env` or
    missing environment variable surfaces immediately at boot rather
    than on the first tool invocation. Future shared resources (e.g.
    a pooled httpx.AsyncClient or qtm-rt connection) can be bound to
    the server context here.
    """
    get_settings()  # populate lru_cache & fail-fast on bad config
    yield

def create_server() -> FastMCP:
    server = FastMCP("Universal_QTM_Server", lifespan=server_lifespan)
    
    try:
        from qtm_mcp.tools import file_ops, realtime, video, pipeline
        
        # Explicit registration instead of global decorators
        server.tool()(file_ops.load_patient_session)
        server.tool()(realtime.fetch_qtm_data)
        server.tool()(video.extract_video_keyframes)
        server.tool()(pipeline.trigger_processing_pipeline)
        server.tool()(pipeline.fetch_clinical_metrics)
        
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
