# QTM MCP Roadmap

This document outlines the development roadmap for QTM MCP as we progress toward a stable `1.0.0` release. 

As an open-source project bridging AI and clinical biomechanics, our goal is to build a robust, safe, and easily extensible toolset for researchers and clinicians.

## 📍 Phase 1: Core Foundation & Stability (v0.1.x) - *Current*
- [x] FastMCP migration for Tools, Resources, and Prompts separation
- [x] Basic session loading and offline fallback mechanisms
- [x] Initial real-time streaming wrappers for `qtm-rt`
- [x] Core clinical tools (OpenSim integration, normative data comparison)
- [x] Path confinement and security guardrails for file operations
- [ ] Comprehensive automated test coverage and CI/CD pipelines
- [ ] Improve real-time connection resilience and circuit breaking

## 📍 Phase 2: Enhanced Biomechanics & Telemetry (v0.5.x)
- [ ] **Advanced Filtering**: Introduce configurable digital filters (Butterworth, Chebyshev) for raw analog and kinematic data directly within the server.
- [ ] **Expanded Normative Database**: Stratify the normative metrics database by age, sex, and pathology.
- [ ] **Force Plate Integration**: Deepen telemetry tools to support center-of-pressure (COP) trajectories and ground reaction force (GRF) vectors natively.
- [ ] **Python-based Modeling**: Provide lightweight Python alternatives to OpenSim/MATLAB pipelines for simpler joint angle calculations.

## 📍 Phase 3: Visual Intelligence & AI Analytics (v0.8.x)
- [ ] **Computer Vision Pipelines**: Expand the `video.py` toolset to support 3D pose estimation from 2D keyframes.
- [ ] **Gait Cycle Segmentation**: Implement AI-driven heuristic algorithms to automatically identify heel-strike and toe-off events from marker data.
- [ ] **Interactive Visualizations**: Generate static and interactive HTML/JS plots (via Plotly) that LLMs can return directly to the user.

## 📍 Phase 4: Production & Clinical Readiness (v1.0.0)
- [ ] **EHR Integrations**: Expand FHIR support beyond basic DiagnosticReports to encompass structured Observations and Conditions.
- [ ] **Extensibility API**: Provide a plug-and-play architecture for labs to inject their own custom proprietary tools without forking the repository.
- [ ] **Regulatory Documentation**: Complete technical files detailing software architecture, risk management, and clinical disclaimers.

---

*Note: This roadmap is subject to change based on community feedback, contributor availability, and shifts in the broader AI / MCP ecosystem. If you are interested in accelerating any of these features, please check our [CONTRIBUTING.md](CONTRIBUTING.md) guide.*
