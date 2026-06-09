# Universal QTM MCP Server

A professional, modular Model Context Protocol (MCP) server that acts as a bridge between AI assistants (such as Claude 3.5 Sonnet) and **Qualisys Track Manager (QTM)** software. This integration enables AI agents to serve as clinical decision support tools in motion analysis labs by loading trials, streaming 3D/6D kinematic and analog/EMG data, automating data pipelines (MATLAB, OpenSim), and extracting video keyframes for postural inspection.

## Features

- **Session Loading**: Open `.qtm` or `.c3d` captures dynamically via QTM's REST API.
- **Dynamic Project Switching**: Auto-resolves file structures based on active QTM projects or offline fallbacks.
- **Multimodal Raw Data Streams**: Access 3D marker coordinates, 6D rigid body Euler matrices, analog EMG signals, and force plate telemetry.
- **Pipeline Execution**: Launch Inverse Kinematics (IK) solvers and Gait Models in OpenSim or MATLAB directly from the agent conversation.
- **Clinical Reporting**: Fetch spatio-temporal parameters and kinematic maximums, allowing pre-operative vs. post-operative comparison.
- **Gait Video Analysis**: Extract keyframe images dynamically from capture videos or programmatically generate 2D sagittal joint skeletons using OpenCV.

---

## Directory Architecture

```
qtm-mcp/
├── pyproject.toml             # Modern pyproject configuration (Hatchling)
├── README.md                  # Project documentation
├── CONTRIBUTING.md            # Contributor guidelines
├── src/
│   └── qtm_mcp/
│       ├── __init__.py        # Package exports
│       ├── server.py          # Main CLI runner and tool registry
│       ├── config.py          # Pydantic-settings config schema
│       ├── utils.py           # Directory resolution utilities
│       └── tools/             # Split tool logic
│           ├── __init__.py
│           ├── file_ops.py    # Session loading tools
│           ├── realtime.py    # qtm-rt real-time streams
│           ├── video.py       # OpenCV keyframe extraction & stick-figure drawing
│           └── pipeline.py    # Subprocess execution & clinical reports
```

---

## Installation

### Prerequisites

- Python `>= 3.10`
- To run real-time streams on host machinery: [qtm-rt SDK](https://github.com/qualisys/qualisys_python_sdk) and QTM must be active.
- To execute processing pipelines: OpenSim command line (`opensim-cmd`) or MATLAB in system PATH.

### Local Installation (Developer / Editable Mode)

1. Clone or download this project to your directory.
2. Install the package in editable mode with development dependencies:

```bash
pip install -e .
```

---

## Configuration

The package uses `pydantic-settings` to manage environment variables. You can override defaults without editing the source code by creating a `.env` file or exporting environment variables:

| Variable | Default | Description |
|---|---|---|
| `QTM_REST_PORT` | `7979` | QTM REST API control port |
| `QTM_REST_HOST` | `localhost` | Host machine running QTM REST API |
| `QTM_RT_PORT` | `22223` | QTM Real-Time Protocol port |
| `QTM_RT_HOST` | `127.0.0.1` | Host machine running QTM RT Server |
| `PROJECTS_ROOT` | `C:/QTM_Projects` | Directory where clinical projects reside |
| `DEFAULT_PROJECT` | `Xavier_Gait_Lab` | Fallback clinical project name |

---

## Client Integration

### 1. Claude Desktop Integration

Add the server to your `claude_desktop_config.json` (located at `%APPDATA%/Claude/claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "universal-qtm-server": {
      "command": "qtm-mcp"
    }
  }
}
```

If you are using a virtual environment, target the environment-specific Python runner:

```json
{
  "mcpServers": {
    "universal-qtm-server": {
      "command": "C:/Users/<Username>/.virtualenvs/qtm-mcp/Scripts/qtm-mcp.exe"
    }
  }
}
```

### 2. LangGraph / Python Integration

You can integrate this server into custom langchain or langgraph agents using the standard `mcp` client:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="qtm-mcp"
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        
        # Retrieve list of available clinical tools
        tools = await session.list_tools()
        print(tools)
```

---

## Contributor Architecture

If you want to add new tools to the biomechanical workflow:
1. Create a Python module inside the `src/qtm_mcp/tools/` folder.
2. Define your async tool functions and provide type hints.
3. Import your new module inside `src/qtm_mcp/server.py`.
4. Register the tool explicitly in `create_server()` using `server.tool()(with_timeout(X)(my_tool_function))`.

---

## Legal & Liability

> [!WARNING]
> **CLINICAL AND MEDICAL LIABILITY WARNING:**
> This software is **NOT** an FDA-approved (or other regulatory body) medical device and is **NOT** intended for clinical diagnostic, prognostic, or therapeutic decisions. It is provided strictly for **research and educational purposes**.
>
> Any biomechanical reports, real-time data streams, joint angle calculations, or AI-generated summaries must be **independently verified by a qualified, licensed healthcare professional**. The developers and contributors accept no responsibility or liability for clinical decisions made based on outputs from this software.
>
> For full terms and details, please refer to the [DISCLAIMER.md](file:///d:/QTM%20MCP/DISCLAIMER.md) and [LICENSE](file:///d:/QTM%20MCP/LICENSE) files.
