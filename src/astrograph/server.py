"""
MCP server for code structure analysis.

Auto-indexes the codebase at startup and maintains the index via file watching.

Provides 7 tools (all prefixed with astrograph_):
- astrograph_analyze: Find duplicates and similar patterns
- astrograph_write: Write Python file with duplicate detection (blocks if duplicate exists)
- astrograph_edit: Edit Python file with duplicate detection (blocks if duplicate exists)
- astrograph_suppress: Suppress a duplicate group by hash
- astrograph_unsuppress: Remove suppression from a hash
- astrograph_list_suppressions: List all suppressed hashes
- astrograph_suppress_idiomatic: Suppress all idiomatic patterns at once
"""

import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .tools import CodeStructureTools

# Check for event-driven mode via environment variable
_event_driven = os.environ.get("ASTROGRAPH_EVENT_DRIVEN", "").lower() in ("1", "true", "yes")

# Global tools instance
_tools = CodeStructureTools(event_driven=_event_driven)


def get_tools() -> CodeStructureTools:
    """Get the global tools instance."""
    return _tools


def set_tools(tools: CodeStructureTools) -> None:
    """Set the global tools instance (for testing)."""
    global _tools
    _tools = tools


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("code-structure-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="astrograph_analyze",
                description=(
                    "Analyze the indexed Python codebase for duplicate functions, methods, and "
                    "code blocks (for/while/if/try/with). Returns exact duplicates verified via "
                    "graph isomorphism."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "thorough": {
                            "type": "boolean",
                            "description": (
                                "If true, show ALL duplicates including small ones (~2+ lines). "
                                "If false, show only significant duplicates (~6+ lines). "
                                "Default: true"
                            ),
                            "default": True,
                        },
                        "auto_reindex": {
                            "type": "boolean",
                            "description": (
                                "If true and index is stale, automatically re-index before analyzing. "
                                "Default: true"
                            ),
                            "default": True,
                        },
                    },
                },
            ),
            Tool(
                name="astrograph_suppress",
                description=(
                    "Suppress a duplicate group by its WL hash. "
                    "Use this to mute idiomatic patterns or acceptable duplications "
                    "that don't need to be refactored. The hash is shown in astrograph_analyze output."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "wl_hash": {
                            "type": "string",
                            "description": "The WL hash of the duplicate group to suppress",
                        },
                    },
                    "required": ["wl_hash"],
                },
            ),
            Tool(
                name="astrograph_unsuppress",
                description=(
                    "Remove suppression from a hash, making it appear in astrograph_analyze results again."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "wl_hash": {
                            "type": "string",
                            "description": "The WL hash to unsuppress",
                        },
                    },
                    "required": ["wl_hash"],
                },
            ),
            Tool(
                name="astrograph_list_suppressions",
                description="List all currently suppressed hashes.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="astrograph_suppress_idiomatic",
                description=(
                    "Suppress ALL idiomatic patterns in one call. "
                    "Convenience method to quickly suppress all patterns classified as idiomatic "
                    "(guard clauses, test setup, delegate methods, dict building, etc.). "
                    "Use instead of calling suppress() for each idiomatic pattern."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="astrograph_write",
                description=(
                    "Write Python code to a file with automatic duplicate detection. "
                    "Checks the content for structural duplicates before writing. "
                    "BLOCKS if identical code exists elsewhere (returns existing location). "
                    "WARNS on high similarity but proceeds with write."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the file to write",
                        },
                        "content": {
                            "type": "string",
                            "description": "The Python code content to write",
                        },
                    },
                    "required": ["file_path", "content"],
                },
            ),
            Tool(
                name="astrograph_edit",
                description=(
                    "Edit a Python file with automatic duplicate detection. "
                    "Checks the new_string for structural duplicates before applying. "
                    "BLOCKS if identical code exists elsewhere (returns existing location). "
                    "WARNS on high similarity but proceeds with edit."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the file to edit",
                        },
                        "old_string": {
                            "type": "string",
                            "description": "The exact text to replace (must be unique in file)",
                        },
                        "new_string": {
                            "type": "string",
                            "description": "The replacement Python code",
                        },
                    },
                    "required": ["file_path", "old_string", "new_string"],
                },
            ),
        ]

    # Map external tool names to internal names
    TOOL_NAME_MAP = {
        "astrograph_analyze": "analyze",
        "astrograph_write": "write",
        "astrograph_edit": "edit",
        "astrograph_suppress": "suppress",
        "astrograph_unsuppress": "unsuppress",
        "astrograph_list_suppressions": "list_suppressions",
        "astrograph_suppress_idiomatic": "suppress_idiomatic",
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        internal_name = TOOL_NAME_MAP.get(name, name)
        result = _tools.call_tool(internal_name, arguments)
        return [TextContent(type="text", text=result.text)]

    return server


async def run_server() -> None:
    """Run the MCP server."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
