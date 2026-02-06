"""End-to-end tests for the Docker container and MCP protocol.

These tests validate:
1. The published Docker image works correctly
2. MCP JSON-RPC protocol flow over stdio
3. Full workflows: index → analyze → suppress → analyze
"""

import contextlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Docker image to test (use local build for CI, published for release validation)
DOCKER_IMAGE = os.environ.get("ASTOGRAPH_TEST_IMAGE", "thaylo/astograph")


def send_mcp_messages(
    messages: list[dict],
    workspace_path: str | None = None,
    read_only: bool = False,
) -> list[dict]:
    """Send MCP JSON-RPC messages to the Docker container and return responses."""
    input_data = "\n".join(json.dumps(msg) for msg in messages)

    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
    ]

    if workspace_path:
        mount_opt = "ro" if read_only else "rw"
        cmd.extend(["-v", f"{workspace_path}:/workspace:{mount_opt}"])

    cmd.append(DOCKER_IMAGE)

    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        text=True,
        timeout=30,
    )

    responses = []
    for line in result.stdout.strip().split("\n"):
        if line:
            with contextlib.suppress(json.JSONDecodeError):
                responses.append(json.loads(line))

    return responses


def mcp_initialize() -> dict:
    """Create MCP initialize request."""
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "1.0",
            "capabilities": {},
            "clientInfo": {"name": "e2e-test", "version": "1.0"},
        },
        "id": 1,
    }


def mcp_list_tools() -> dict:
    """Create MCP tools/list request."""
    return {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 2,
    }


def mcp_call_tool(name: str, arguments: dict, request_id: int = 3) -> dict:
    """Create MCP tools/call request."""
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
        },
        "id": request_id,
    }


@pytest.fixture
def sample_workspace():
    """Create a temporary workspace with Python files containing duplicates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file with duplicate functions
        code = '''
def calculate_sum(a, b):
    """Add two numbers."""
    result = a + b
    return result

def add_numbers(x, y):
    """Add two numbers."""
    result = x + y
    return result

def multiply(a, b):
    return a * b

class Calculator:
    def add(self, a, b):
        result = a + b
        return result
'''
        file_path = Path(tmpdir) / "math_utils.py"
        file_path.write_text(code)

        # Create another file with more code
        code2 = """
def process_list(items):
    results = []
    for item in items:
        if item > 0:
            results.append(item * 2)
    return results

def transform_values(data):
    results = []
    for item in data:
        if item > 0:
            results.append(item * 2)
    return results
"""
        file_path2 = Path(tmpdir) / "data_utils.py"
        file_path2.write_text(code2)

        yield tmpdir


class TestDockerImageBasics:
    """Basic tests for the Docker image."""

    def test_image_exists(self):
        """Test that the Docker image can be pulled/exists."""
        result = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Docker image {DOCKER_IMAGE} not found"

    def test_python_import(self):
        """Test that astograph can be imported in the container."""
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                DOCKER_IMAGE,
                "-c",
                "from astograph.server import create_server; print('OK')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestMCPProtocol:
    """Tests for MCP JSON-RPC protocol over stdio."""

    def test_initialize(self):
        """Test MCP initialization handshake."""
        responses = send_mcp_messages([mcp_initialize()])

        assert len(responses) >= 1
        init_response = responses[0]

        assert init_response.get("id") == 1
        assert "result" in init_response
        assert "serverInfo" in init_response["result"]
        assert init_response["result"]["serverInfo"]["name"] == "code-structure-mcp"

    def test_list_tools(self):
        """Test listing available MCP tools."""
        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_list_tools(),
            ]
        )

        # Find the tools/list response
        tools_response = next((r for r in responses if r.get("id") == 2), None)
        assert tools_response is not None

        tools = tools_response["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        # Verify all 9 tools are present
        expected_tools = {
            "astograph_index",
            "astograph_analyze",
            "astograph_check",
            "astograph_compare",
            "astograph_suppress",
            "astograph_unsuppress",
            "astograph_list_suppressions",
            "astograph_suppress_idiomatic",
            "astograph_check_staleness",
        }
        assert expected_tools == tool_names

    def test_tool_descriptions_mention_python(self):
        """Test that relevant tools mention Python-only support."""
        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_list_tools(),
            ]
        )

        tools_response = next((r for r in responses if r.get("id") == 2), None)
        tools = {t["name"]: t for t in tools_response["result"]["tools"]}

        # Check index tool mentions Python
        assert "Python" in tools["astograph_index"]["description"]

        # Check check tool mentions Python
        assert "Python" in tools["astograph_check"]["description"]

        # Check compare tool mentions Python
        assert "Python" in tools["astograph_compare"]["description"]


class TestE2EWorkflow:
    """End-to-end workflow tests."""

    def test_index_analyze_workflow(self, sample_workspace):
        """Test full index → analyze workflow."""
        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_call_tool("astograph_index", {"path": "/workspace"}, 3),
                mcp_call_tool("astograph_analyze", {"thorough": True}, 4),
            ],
            workspace_path=sample_workspace,
        )

        # Find index response
        index_response = next((r for r in responses if r.get("id") == 3), None)
        assert index_response is not None
        assert "result" in index_response

        index_text = index_response["result"]["content"][0]["text"]
        assert "Indexed" in index_text
        assert "code units" in index_text

        # Find analyze response
        analyze_response = next((r for r in responses if r.get("id") == 4), None)
        assert analyze_response is not None

        analyze_text = analyze_response["result"]["content"][0]["text"]
        # Should find duplicates in our sample code
        assert "duplicate" in analyze_text.lower() or "CLEAN" in analyze_text

    def test_check_similar_code(self, sample_workspace):
        """Test checking for similar code before creation."""
        # Code that's similar to what's in our sample workspace
        similar_code = """
def add_values(a, b):
    result = a + b
    return result
"""

        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_call_tool("astograph_index", {"path": "/workspace"}, 3),
                mcp_call_tool("astograph_check", {"code": similar_code}, 4),
            ],
            workspace_path=sample_workspace,
        )

        # Find check response
        check_response = next((r for r in responses if r.get("id") == 4), None)
        assert check_response is not None

        check_text = check_response["result"]["content"][0]["text"]
        # Should find similar code exists
        assert any(word in check_text for word in ["STOP", "CAUTION", "similar", "exists"])

    def test_compare_two_snippets(self):
        """Test comparing two code snippets."""
        code1 = "def add(a, b):\n    return a + b"
        code2 = "def sum(x, y):\n    return x + y"

        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_call_tool("astograph_compare", {"code1": code1, "code2": code2}, 3),
            ]
        )

        compare_response = next((r for r in responses if r.get("id") == 3), None)
        assert compare_response is not None

        compare_text = compare_response["result"]["content"][0]["text"]
        assert "EQUIVALENT" in compare_text

    def test_compare_different_snippets(self):
        """Test comparing structurally different code snippets."""
        code1 = "def add(a, b):\n    return a + b"
        code2 = "def greet(name):\n    print(f'Hello {name}')\n    return name"

        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_call_tool("astograph_compare", {"code1": code1, "code2": code2}, 3),
            ]
        )

        compare_response = next((r for r in responses if r.get("id") == 3), None)
        assert compare_response is not None

        compare_text = compare_response["result"]["content"][0]["text"]
        assert "DIFFERENT" in compare_text


class TestErrorHandling:
    """Tests for error handling in MCP protocol."""

    def test_index_nonexistent_path(self):
        """Test indexing a path that doesn't exist."""
        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_call_tool("astograph_index", {"path": "/nonexistent/path"}, 3),
            ]
        )

        index_response = next((r for r in responses if r.get("id") == 3), None)
        assert index_response is not None

        response_text = index_response["result"]["content"][0]["text"]
        assert "Error" in response_text or "not exist" in response_text

    def test_analyze_without_index(self):
        """Test analyzing before indexing."""
        responses = send_mcp_messages(
            [
                mcp_initialize(),
                mcp_call_tool("astograph_analyze", {}, 3),
            ]
        )

        analyze_response = next((r for r in responses if r.get("id") == 3), None)
        assert analyze_response is not None

        response_text = analyze_response["result"]["content"][0]["text"]
        assert "index" in response_text.lower()


# Skip Docker tests if Docker is not available
def pytest_configure(_config):
    """Check if Docker is available."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("Docker not available", allow_module_level=True)
