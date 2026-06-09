# Security Policy

## Supported Versions

Only the latest major version is currently receiving security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability within the Universal QTM MCP Server, please report it via the GitHub Security Advisory feature or email the lab maintainers directly. Do NOT open public issues for security exploits, especially those related to Protected Health Information (PHI) access.

## Clinical Fail-Closed Policy

This server is designed for clinical environments. In the event of an error, invalid input, missing dependencies (such as OpenCV or `qtm-rt`), or unreachable subsystems, the server **MUST fail closed**.

- The server will **not** generate synthetic, mocked, or placeholder data.
- Exceptions will be explicitly raised to the MCP client (such as Claude) indicating the failure.
- This policy ensures that downstream AI agents do not invent clinical reports or hallucinate medical analyses.
