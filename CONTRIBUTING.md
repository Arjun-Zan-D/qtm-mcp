# Contributing to qtm-mcp

Thank you for contributing! As an open-source clinical motion capture utility, maintaining high standards of code safety, documentation accuracy, and data fallback coverage is essential for reliability in clinical research settings.

---

## Code of Conduct

Please remain respectful, professional, and patient in all issues, pull requests, and discussions.

---

## Development Environment Setup

1. Clone this repository locally.
2. Initialize a virtual environment and activate it:
   ```bash
   python -m venv .venv
   .venv/Scripts/activate     # On Windows
   source .venv/bin/activate  # On Linux/macOS
   ```
3. Install development requirements and the project in editable mode:
   ```bash
   pip install -e .[dev]
   # Or install dependencies manually
   pip install -e .
   pip install pytest pytest-asyncio
   ```

---

## Testing

We use `pytest` for unit testing. Write test cases for new tools under the `tests/` directory.

### Running Tests

To run the full test suite, execute:

```bash
pytest
```

Ensure all tests pass before opening a Pull Request. If you add new tools, write corresponding test functions under `tests/` to verify registration and mock outputs.

---

## Pull Request Guidelines

1. **Keep Imports Dynamic**: Do not make proprietary SDKs (`qtm-rt`) or system binaries (`opencv-python`) mandatory blockages for basic imports. Wrap them in `try/except` and provide simulated data generators so that tools run in test mode when hardware is offline.
2. **Document Everything**: Every `@mcp.tool()` must contain a clear, clinical docstring. Large language models read these docstrings at runtime to decide when and how to invoke the tools.
3. **Branching**: Submit your pull request to the `main` branch. Use descriptive branch names (e.g. `feat/force-plate-calibration` or `fix/rest-timeout-handling`).
4. **Linting & Formatting**: Follow PEP 8 guidelines. Keep code clean and well-commented.
