"""Tests for deterministic LSP setup helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from astrograph.lsp_setup import (
    auto_bind_missing_servers,
    load_lsp_bindings,
    resolve_lsp_command,
    save_lsp_bindings,
)


@pytest.mark.parametrize(
    ("binding", "env_command", "expected_source", "expected_command"),
    [
        (["custom-pylsp"], "env-pylsp", "binding", ["custom-pylsp"]),
        (None, "python -m pylsp", "env", ["python", "-m", "pylsp"]),
    ],
)
def test_resolve_lsp_command_precedence(
    tmp_path,
    binding,
    env_command,
    expected_source,
    expected_command,
):
    if binding is not None:
        save_lsp_bindings({"python": binding}, workspace=tmp_path)

    with patch.dict(os.environ, {"ASTROGRAPH_PY_LSP_COMMAND": env_command}, clear=False):
        command, source = resolve_lsp_command(
            language_id="python",
            default_command=("pylsp",),
            command_env_var="ASTROGRAPH_PY_LSP_COMMAND",
            workspace=tmp_path,
        )

    assert source == expected_source
    assert command == expected_command


def test_auto_bind_missing_servers_uses_agent_observations(tmp_path):
    with patch.dict(
        os.environ,
        {
            "ASTROGRAPH_PY_LSP_COMMAND": "missing-python-lsp-xyz",
            "ASTROGRAPH_JS_LSP_COMMAND": "missing-js-lsp-xyz",
        },
        clear=False,
    ):
        result = auto_bind_missing_servers(
            workspace=tmp_path,
            observations=[
                {
                    "language": "python",
                    "command": [sys.executable, "-m", "pylsp"],
                }
            ],
        )

    python_change = next(change for change in result["changes"] if change["language"] == "python")
    assert python_change["source"] == "observation"
    assert python_change["command"][0] == sys.executable

    persisted = load_lsp_bindings(tmp_path)
    assert persisted["python"][0] == sys.executable
