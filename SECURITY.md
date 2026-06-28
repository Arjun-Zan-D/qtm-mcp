# Security Policy

## Supported Versions

Only the latest major version is currently receiving security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability within qtm-mcp, please report it via the GitHub Security Advisory feature or email the maintainer directly at arjunsinghshishodia03@gmail.com. Do NOT open public issues for security exploits, especially those related to Protected Health Information (PHI) access.

### Severity Classification & Timelines
- **Critical (e.g., PHI exposure, remote code execution):** We aim to respond within 48 hours and release a patch immediately.
- **High (e.g., Denial of Service, path traversal in specific setups):** We aim to respond within 5 business days.
- **Medium/Low:** We aim to respond within 5-10 business days and include fixes in the next minor release.

## Clinical Fail-Closed Policy

This server is designed for clinical environments. In the event of an error, invalid input, missing dependencies (such as OpenCV or `qtm-rt`), or unreachable subsystems, the server **MUST fail closed**.

- The server will **not** generate synthetic, mocked, or placeholder data.
- Exceptions will be explicitly raised to the MCP client (such as Claude) indicating the failure.
- This policy ensures that downstream AI agents do not invent clinical reports or hallucinate medical analyses.
