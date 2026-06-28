# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- No unreleased changes yet.

## [0.1.0] - 2026-06-28

### Added
- Initial public release of the `qtm-mcp` server.
- Session loading capabilities for `.qtm` and `.c3d` captures dynamically via QTM's REST API.
- Multimodal raw data streaming tools (3D marker coordinates, 6D rigid body Euler matrices, analog EMG signals, force plate telemetry).
- Pipeline execution functionality (Inverse Kinematics solvers, OpenSim/MATLAB gait models).
- Clinical reporting integration for fetching spatio-temporal parameters and kinematic maximums.
- Video analysis tools for dynamic keyframe extraction and 2D sagittal joint skeletons using OpenCV.
- Dynamic project switching and file resolution.
- Configurable environment options (`QTM_REST_HOST`, `QTM_PROJECT_DIR`, etc.) managed via `pydantic-settings`.

[Unreleased]: https://github.com/Arjun-Zan-D/qtm-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Arjun-Zan-D/qtm-mcp/releases/tag/v0.1.0
