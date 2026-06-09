import pytest
from qtm_mcp.server import create_server

EXPECTED_TOOLS = {
    "load_patient_session",
    "fetch_qtm_data",
    "trigger_processing_pipeline",
    "fetch_clinical_metrics",
    "extract_video_keyframes",
}

@pytest.mark.asyncio
async def test_tools_registration():
    """All five core clinical tools must be registered on the created MCP instance."""
    server = create_server()
    # In FastMCP, tools are often stored in server._tool_manager or similar,
    # or you can list them. Wait, `server.list_tools()` is standard.
    tools_response = await server.list_tools()
    registered_names = {t.name for t in tools_response}

    for expected in EXPECTED_TOOLS:
        assert expected in registered_names, (
            f"Tool '{expected}' is missing from MCP registration. "
            f"Registered tools: {sorted(registered_names)}"
        )
