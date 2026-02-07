"""
Dual-mode stdio transport for MCP.

Auto-detects client framing from the first non-whitespace byte on stdin:
  '{' → newline mode  (read line-by-line, write <json>\n)
  'C' → framed mode   (Content-Length: N\r\n\r\n<N bytes>)

Drop-in replacement for ``mcp.server.stdio.stdio_server``.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage


class _StdioReader:
    """Buffered binary reader that auto-detects newline vs Content-Length framing."""

    def __init__(self, stream: anyio.AsyncFile[bytes]) -> None:
        self._stream = stream
        self._buf = b""
        self.mode: str | None = None  # "newline" or "framed"

    async def _fill(self, min_bytes: int = 1) -> None:
        """Read more data from the stream into the buffer."""
        while len(self._buf) < min_bytes:
            chunk = await self._stream.read(65536)
            if not chunk:
                raise EOFError("stdin closed")
            self._buf += chunk

    async def _detect_mode(self) -> None:
        """Detect framing mode from the first non-whitespace byte."""
        while True:
            await self._fill(1)
            # Skip leading whitespace
            stripped = self._buf.lstrip()
            if not stripped:
                self._buf = b""
                continue
            # Update buffer to stripped version
            self._buf = stripped
            first = chr(stripped[0])
            if first == "C":
                self.mode = "framed"
            else:
                self.mode = "newline"
            return

    async def read_message(self) -> bytes:
        """Read and return the next complete JSON-RPC message as bytes."""
        if self.mode is None:
            await self._detect_mode()

        if self.mode == "newline":
            return await self._read_newline()
        else:
            return await self._read_framed()

    async def _read_newline(self) -> bytes:
        """Read a newline-delimited message."""
        while b"\n" not in self._buf:
            try:
                # Force reading more data even if buffer is non-empty
                await self._fill(len(self._buf) + 1)
            except EOFError:
                # Return remaining buffer content on EOF (last message
                # may lack a trailing newline, e.g. subprocess.run input).
                remaining = self._buf.strip()
                self._buf = b""
                if remaining:
                    return remaining
                raise
        line, self._buf = self._buf.split(b"\n", 1)
        return line.strip()

    async def _read_framed(self) -> bytes:
        """Read a Content-Length framed message."""
        # Read headers until \r\n\r\n
        while b"\r\n\r\n" not in self._buf:
            await self._fill()

        header_end = self._buf.index(b"\r\n\r\n")
        headers = self._buf[:header_end].decode("ascii")
        self._buf = self._buf[header_end + 4 :]

        # Parse Content-Length
        content_length = None
        for header_line in headers.split("\r\n"):
            if header_line.lower().startswith("content-length:"):
                content_length = int(header_line.split(":", 1)[1].strip())
                break

        if content_length is None:
            raise ValueError("Missing Content-Length header in framed message")

        # Read body
        await self._fill(content_length)
        body = self._buf[:content_length]
        self._buf = self._buf[content_length:]
        return body


@asynccontextmanager
async def dual_stdio_server() -> (
    AsyncIterator[
        tuple[
            MemoryObjectReceiveStream[SessionMessage | Exception],
            MemoryObjectSendStream[SessionMessage],
        ]
    ]
):
    """
    Async context manager matching the interface of ``mcp.server.stdio.stdio_server``.

    Yields ``(read_stream, write_stream)`` where messages are automatically
    framed in whichever mode the client uses.
    """
    read_send, read_recv = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    write_send, write_recv = anyio.create_memory_object_stream[SessionMessage](0)

    stdin = anyio.wrap_file(sys.stdin.buffer)
    stdout = anyio.wrap_file(sys.stdout.buffer)

    reader = _StdioReader(stdin)

    async def stdin_task() -> None:
        async with read_send:
            while True:
                try:
                    data = await reader.read_message()
                    if not data:
                        continue
                    msg = JSONRPCMessage.model_validate_json(data)
                    await read_send.send(SessionMessage(message=msg))
                except EOFError:
                    return
                except Exception as exc:
                    await read_send.send(exc)

    async def stdout_task() -> None:
        async with write_recv:
            async for session_message in write_recv:
                json_bytes = session_message.message.model_dump_json(
                    by_alias=True, exclude_none=True
                ).encode("utf-8")

                if reader.mode == "framed":
                    header = f"Content-Length: {len(json_bytes)}\r\n\r\n".encode("ascii")
                    await stdout.write(header + json_bytes)
                else:
                    await stdout.write(json_bytes + b"\n")
                await stdout.flush()

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_task)
        tg.start_soon(stdout_task)
        yield read_recv, write_send
        tg.cancel_scope.cancel()
