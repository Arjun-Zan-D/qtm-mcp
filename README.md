# Universal QTM MCP Server

[![Python Tests](https://github.com/Arjun-Zan-D/qtm-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/Arjun-Zan-D/qtm-mcp/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A professional, modular Model Context Protocol (MCP) server that acts as a bridge between AI assistants (such as Claude 3.5 Sonnet) and **Qualisys Track Manager (QTM)** software. This integration enables AI agents to serve as clinical decision support tools in motion analysis labs by loading trials, streaming 3D/6D kinematic and analog/EMG data, automating data pipelines (MATLAB, OpenSim), and extracting video keyframes for postural inspection.

## Features

- **Session Loading**: Open `.qtm` or `.c3d` captures dynamically via QTM's REST API.
- **Dynamic Project Switching**: Auto-resolves file structures based on active QTM projects or offline fallbacks.
- **Multimodal Raw Data Streams**: Access 3D marker coordinates, 6D rigid body Euler matrices, analog EMG signals, and force plate telemetry.
- **Pipeline Execution**: Launch Inverse Kinematics (IK) solvers and Gait Models in OpenSim or MATLAB directly from the agent conversation.
- **Clinical Reporting**: Fetch spatio-temporal parameters and kinematic maximums, allowing pre-operative vs. post-operative comparison.
- **Gait Video Analysis**: Extract keyframe images dynamically from capture videos or programmatically generate 2D sagittal joint skeletons using OpenCV.

---

## Configuration

Configure the server via environment variables or a `.env` file in the project root. See `.env.example` for a full list of supported variables.

### Key Environment Variables

*   **`QTM_REST_HOST` / `QTM_REST_PORT`**: Endpoint for the QTM REST API (default: `localhost:22222`).
*   **`QTM_SCRIPTING_HOST` / `QTM_SCRIPTING_PORT`**: Endpoint for the QTM Scripting API (default: `localhost:7979`).
*   **`QTM_RT_HOST` / `QTM_RT_PORT`**: Endpoint for the QTM RT stream (default: `127.0.0.1:22223`).
*   **`QTM_PROJECT_DIR`**: Fallback directory for patient data if dynamic resolution fails.
*   **`FHIR_ALLOWED_ENDPOINTS`**: Comma-separated list of approved EHR endpoints for clinical output.

### Optional Dependencies

Install specific capability groups or all of them:

```bash
pip install qtm-mcp[vision]       # For video processing
pip install qtm-mcp[clinical]     # For PDF and FHIR exports
pip install qtm-mcp[biomechanics] # For biomechanical analytics
pip install qtm-mcp[all]          # Install all optional dependencies
```

### Session Data Structure

The server expects patient data files within the active QTM project directory under `Patient_Data/{patient_id}/{session_date}/`. Files should include:
- `{patient_id}_clinical_report.json`
- `gait_cycles.json`
- `marker_trajectories.json`
- OpenSim configurations under `OpenSim/Setup_IK_{patient_id}.xml`

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
│           ├── file_ops.py        # Session loading tools
│           ├── realtime.py        # qtm-rt real-time streams
│           ├── video.py           # OpenCV keyframe extraction
│           ├── pipeline.py        # Subprocess execution & clinical reports
│           ├── health.py          # Hardware status and calibration
│           ├── telemetry.py       # Analog and EMG signal processing
│           ├── biomechanics.py    # Kinematics and anthropometrics
│           ├── analytics.py       # ML/AI data segmentation and normative stats
│           └── clinical_output.py # EHR pushes, PDFs, and clinical notes
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
