"""What clients see in tools/list (see docs/clients.md).

Every tool needs a description, annotations, and a typed, described argument list;
the total stays within the tool budget.
"""

import asyncio

from tonable import bridge, server
from tonable.tools import session

MAX_TOOLS = 25
# Reserved for compatibility with existing clients.
FORBIDDEN_ARGUMENTS = {"device", "session_id"}


def list_tools():
    return asyncio.run(server.mcp.list_tools())


def test_tool_budget():
    assert 0 < len(list_tools()) <= MAX_TOOLS


def test_every_tool_is_described():
    for tool in list_tools():
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is not None, tool.name
        schema = tool.inputSchema
        assert schema["type"] == "object", tool.name
        for name, prop in schema.get("properties", {}).items():
            assert name not in FORBIDDEN_ARGUMENTS, (tool.name, name)
            assert "type" in prop or "anyOf" not in prop, (tool.name, name)
            assert prop.get("description"), (tool.name, name)


def test_instructions_are_short():
    assert len(server.INSTRUCTIONS.strip().splitlines()) <= 25


def test_live_status_without_live(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "bridge", bridge.Bridge(tmp_path / "none.json"))
    out = session.live_status()
    assert out["connected"] is False
    assert out["code"] == "not_running"
    assert "Control Surface" in out["hint"]


def test_read_tool_error_is_readable(monkeypatch, tmp_path):
    import pytest
    from mcp.server.fastmcp.exceptions import ToolError

    monkeypatch.setattr(server, "bridge", bridge.Bridge(tmp_path / "none.json"))
    with pytest.raises(ToolError) as err:
        session.read_set()
    assert str(err.value).startswith("not_running: ")
    assert "Control Surface" in str(err.value)


def test_tolerant_arguments():
    """null, "" and a lone string are accepted."""
    from pydantic import TypeAdapter

    from tonable.tools import AllParameters, ParameterNames

    names = TypeAdapter(ParameterNames)
    assert names.validate_python(None) == []
    assert names.validate_python("") == []
    assert names.validate_python("Release") == ["Release"]
    assert names.validate_python({"Release": "400 ms"}) == ["Release"]
    flag = TypeAdapter(AllParameters)
    assert flag.validate_python(None) is False
    assert flag.validate_python("") is False
    assert flag.validate_python("true") is True


def test_schemas_have_no_any_of():
    for tool in list_tools():
        assert "anyOf" not in str(tool.inputSchema), tool.name


def test_server_reports_tonable_version():
    import tonable

    options = server.mcp._mcp_server.create_initialization_options()
    assert options.server_name == "tonable"
    assert options.server_version == tonable.__version__
