# QTM MCP

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-1.27%2B-green.svg)](https://modelcontextprotocol.io/)
[![Python Tests](https://github.com/Arjun-Zan-D/qtm-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/Arjun-Zan-D/qtm-mcp/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

*Topics: mcp, model-context-protocol, qualisys, motion-capture, gait-analysis, biomechanics, opensim, python, ai, llm, research*

---

> ### **Making Qualisys Track Manager (QTM) accessible through AI.** 🚀
> 
> **QTM MCP** is an open-source Model Context Protocol (MCP) server that enables AI assistants to communicate directly with Qualisys Track Manager (QTM).
>
> Motion capture software is incredibly powerful, but mastering its workflows often requires significant training and technical expertise. QTM MCP reduces that barrier by allowing researchers, biomechanics laboratories, and developers to interact with QTM using natural language instead of manually navigating complex software workflows or writing custom scripts. 
>
> Rather than replacing existing motion capture software, QTM MCP acts as an intelligent communication layer between AI assistants and QTM—allowing repetitive tasks to be automated while keeping researchers in complete control of the workflow.
>
> *The project was developed and tested at St. Xavier's Gait Lab as the first building block of a larger vision.*

---

**Under the hood:** A professional, modular server that acts as a bridge between AI assistants (such as Claude, ChatGPT, Gemini, etc.) and **QTM**. This integration enables AI agents to serve as support tools in motion analysis labs by loading trials, streaming 3D/6D kinematic and analog/EMG data, automating data pipelines (MATLAB, OpenSim), and extracting video keyframes for postural inspection.

## Current Capabilities

- **Session Loading**: Open `.qtm` or `.c3d` captures dynamically via QTM's REST API.
- **Dynamic Project Switching**: Auto-resolves file structures based on active QTM projects or offline fallbacks.
- **Multimodal Raw Data Streams**: Access 3D marker coordinates, 6D rigid body Euler matrices, analog EMG signals, and force plate telemetry.
- **Pipeline Execution**: Launch Inverse Kinematics (IK) solvers and Gait Models in OpenSim or MATLAB directly from the agent conversation.
- **Clinical Reporting**: Fetch spatio-temporal parameters and kinematic maximums, allowing comparison between multiple trials.
- **Gait Video Analysis**: Extract keyframe images dynamically from capture videos or programmatically generate 2D sagittal joint skeletons using OpenCV.

---

## Quick Start

### 1. Prerequisites
- Python `>= 3.10`
- To run real-time streams on host machinery: [qtm-rt SDK](https://github.com/qualisys/qualisys_python_sdk) and QTM must be active. (Note: The server operates gracefully in offline/fallback mode without real-time streaming).
- To execute processing pipelines: OpenSim command line (`opensim-cmd`) or MATLAB in system PATH.

### 2. Installation (Developer / Editable Mode)
Clone or download this project to your directory, then install the package in editable mode:

```bash
pip install -e .[all]
```

*Optional dependency groups available:* `vision`, `clinical`, `biomechanics`, `analytics`.

### 3. Client Integration
Add the server to your `claude_desktop_config.json` (located at `%APPDATA%/Claude/claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "qtm-mcp": {
      "command": "C:/Users/<Username>/.virtualenvs/qtm-mcp/Scripts/qtm-mcp.exe"
    }
  }
}
```

Or connect programmatically via LangGraph / Python:
```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(command="qtm-mcp")

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print(tools)
```

---

## Configuration

The package uses `pydantic-settings` to manage environment variables. You can override defaults without editing the source code by creating a `.env` file or exporting environment variables.

| Variable | Default | Description |
|---|---|---|
| `QTM_REST_PORT` | `22222` | QTM REST API control port |
| `QTM_REST_HOST` | `localhost` | Host machine running QTM REST API |
| `QTM_SCRIPTING_PORT` | `7979` | QTM Scripting API control port |
| `QTM_SCRIPTING_HOST` | `localhost` | Host machine running QTM Scripting API |
| `QTM_RT_PORT` | `22223` | QTM Real-Time Protocol port |
| `QTM_RT_HOST` | `127.0.0.1` | Host machine running QTM RT Server |
| `QTM_PROJECT_DIR` | `None` | Fallback directory for patient data if dynamic resolution fails |
| `PROJECTS_ROOT` | `~/QTM_Projects` | Directory where clinical projects reside |
| `DEFAULT_PROJECT` | `My_Gait_Lab` | Fallback clinical project name |
| `FHIR_ALLOWED_ENDPOINTS` | `""` | Comma-separated list of approved EHR endpoints for clinical output |
| `MATLAB_SCRIPTS_PATH` | `~/QTM_Projects/My_Gait_Lab/Matlab_Scripts` | External pipeline engine path for MATLAB |
| `OPENSIM_CONFIG_ROOT` | `~/QTM_Projects/My_Gait_Lab/OpenSim` | External pipeline engine path for OpenSim |

**Session Data Structure:**
The server expects patient data files within the active QTM project directory under `Patient_Data/{patient_id}/{session_date}/`. Files should include:
- `{patient_id}_clinical_report.json`
- `gait_cycles.json`
- `marker_trajectories.json`
- OpenSim configurations under `OpenSim/Setup_IK_{patient_id}.xml`

---

## Architecture Overview

QTM MCP leverages the FastMCP standard to expose capabilities efficiently:

- **Resources** (`qtm://` URIs): Read-only endpoints for data and system state (e.g., system health, active project, static reference data).
- **Tools**: Executable actions that trigger processing, mutations, or capture control (e.g., streaming real-time data, pipeline execution, generating PDF reports).
- **Prompts**: Guided workflows that provide AI assistants with structured templates for complex tasks (e.g., clinical session summarization, calibration troubleshooting).

### Directory Architecture

```
qtm-mcp/
├── pyproject.toml             # Modern pyproject configuration (Hatchling)
├── README.md                  # Project documentation
├── CONTRIBUTING.md            # Contributor guidelines
├── CHANGELOG.md               # Release history
├── ROADMAP.md                 # Future vision and features
├── src/
│   └── qtm_mcp/
│       ├── __init__.py        # Package exports
│       ├── server.py          # Main CLI runner and tool registry
│       ├── config.py          # Pydantic-settings config schema
│       ├── connection.py      # QTM RT and HTTP connection manager
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
│           ├── clinical_output.py # EHR pushes, PDFs, and clinical notes
│           └── scripting.py       # QTM Scripting API interactions
```

---

## Contributing & Project Resources

If you want to add new tools to the biomechanical workflow:
1. Create a Python module inside the `src/qtm_mcp/tools/` folder.
2. Define your async tool functions and provide type hints.
3. Import your new module inside `src/qtm_mcp/server.py`.
4. Register the tool explicitly in `create_server()` using `@mcp.tool()` or `mcp.tool()(with_timeout(X)(my_tool_function))`.

For more details on contributing, please see [CONTRIBUTING.md](CONTRIBUTING.md).

- **[CHANGELOG.md](CHANGELOG.md)**: Version history and release notes.
- **[ROADMAP.md](ROADMAP.md)**: Planned features and vision.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)**: Guidelines for community interaction.
- **[SECURITY.md](SECURITY.md)**: Security and fail-closed policies.

---

## Acknowledgments

This project is not affiliated with, endorsed by, or sponsored by Qualisys AB. Qualisys® and Qualisys Track Manager (QTM) are trademarks of their respective owners.

## Legal & Liability

> [!WARNING]
> **CLINICAL AND MEDICAL LIABILITY WARNING:**
> This software is **NOT** an FDA-approved (or other regulatory body) medical device and is **NOT** intended for clinical diagnostic, prognostic, or therapeutic decisions. It is provided strictly for **research and educational purposes**.
>
> Any biomechanical reports, real-time data streams, joint angle calculations, or AI-generated summaries must be **independently verified by a qualified, licensed healthcare professional**. The developers and contributors accept no responsibility or liability for clinical decisions made based on outputs from this software.
>
> For full terms and details, please refer to the [DISCLAIMER.md](DISCLAIMER.md) and [LICENSE.txt](LICENSE.txt) files.
