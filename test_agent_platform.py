"""Compatibility test loader for the agent-platform test suite.

`unittest discover` starts at the top-level `tests/` directory by default in many
local workflows. The real suite lives under `agent-platform/tests/` so the
agent-platform module can be copied as a unit. This shim keeps default discovery
useful without duplicating tests.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "agent-platform" / "tests" / "test_mvp0_agents.py"

spec = importlib.util.spec_from_file_location("agent_platform_test_mvp0_agents", TARGET)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

MVP0AgentTests = module.MVP0AgentTests
