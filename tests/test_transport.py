"""전송(transport) 선택 검증 — Claude 외 클라이언트·원격 호스팅 지원.

핵심 회귀: **기본은 반드시 stdio 여야 한다.** 기존 등록(uvx --from git+… scienceon-mcp)은 인자 없이
서버를 띄우므로, 기본값이 바뀌면 모든 사용자의 MCP 가 한 번에 죽는다.
"""
import pytest

from scienceon_mcp import server as s


@pytest.fixture
def spy(monkeypatch):
    """mcp.run 을 가로채고 settings 변경을 원복한다(테스트 간 상태 누수 방지)."""
    calls = {}
    monkeypatch.setattr(s.mcp, "run", lambda **kw: calls.update(kw))
    host, port = s.mcp.settings.host, s.mcp.settings.port
    yield calls
    s.mcp.settings.host, s.mcp.settings.port = host, port


def test_default_is_stdio(spy):
    s.main([])
    assert spy["transport"] == "stdio"


def test_default_does_not_touch_bind_settings(spy):
    before = (s.mcp.settings.host, s.mcp.settings.port)
    s.main([])
    assert (s.mcp.settings.host, s.mcp.settings.port) == before


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_http_transports_selectable(spy, transport):
    s.main(["--transport", transport])
    assert spy["transport"] == transport


def test_host_and_port_applied(spy):
    s.main(["--transport", "sse", "--host", "0.0.0.0", "--port", "9124"])
    assert s.mcp.settings.host == "0.0.0.0"
    assert s.mcp.settings.port == 9124


def test_env_selects_transport(spy, monkeypatch):
    monkeypatch.setenv("SCIENCEON_MCP_TRANSPORT", "streamable-http")
    s.main([])
    assert spy["transport"] == "streamable-http"


def test_unknown_args_do_not_kill_server(spy):
    s.main(["--bogus", "x"])
    assert spy["transport"] == "stdio"


def test_non_numeric_port_env_is_ignored(spy, monkeypatch):
    monkeypatch.setenv("SCIENCEON_MCP_PORT", "abc")
    before = s.mcp.settings.port
    s.main([])
    assert s.mcp.settings.port == before
