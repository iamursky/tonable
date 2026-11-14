"""Exercise the public entry point through a real MCP stdio client."""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import tonable


def test_stdio_initialization_discovery_and_disconnected_status(tmp_path):
    async def check():
        # Isolate discovery from a user's running Live and private session file.
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tonable"],
            env={**os.environ, "HOME": str(tmp_path)},
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                assert initialized.serverInfo.name == "tonable"
                assert initialized.serverInfo.version == tonable.__version__
                tools = await client.list_tools()
                assert len(tools.tools) == 31
                assert "read_set" in {tool.name for tool in tools.tools}
                result = await client.call_tool("live_status", {})
                assert not result.isError
                status = json.loads(result.content[0].text)
                assert status["connected"] is False
                assert status["code"] == "not_running"

    asyncio.run(asyncio.wait_for(check(), timeout=20))
