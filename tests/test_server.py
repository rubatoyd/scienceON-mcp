"""MCP 도구 계층 단위 테스트 (라이브 호출 없음).

다루는 것: 예외 누수 차단(_safe) · 안전성 annotations · 다중그룹 수집 도구.
"""
import pytest

from scienceon_mcp import server as s
from scienceon_mcp.models import Record


# --- 예외 누수 차단 ------------------------------------------------------------

def test_safe_converts_exception_to_dict():
    @s._safe
    def boom():
        raise ValueError("터짐")

    r = boom()
    assert isinstance(r, dict)
    assert r["error"].startswith("ValueError:")


@pytest.mark.parametrize("call", [
    lambda: s.scienceON_search(query="x"),
    lambda: s.scienceON_detail(control_no="CN1"),
    lambda: s.scienceON_export(query="x"),
    lambda: s.scienceON_collect_groups(groups=[{"field": "BI", "terms": ["x"]}]),
])
def test_tools_never_leak_exceptions(monkeypatch, call):
    """자격증명 누락 등 ScienceONError 가 아닌 예외도 도구 밖으로 새면 안 된다.

    회귀: 예전에는 _client() 의 RuntimeError(자격증명 누락)가 그대로 전파돼
    MCP 프로토콜을 흔들 수 있었다(실측 확인).
    """
    def _raise():
        raise RuntimeError("필수 환경변수 누락")

    monkeypatch.setattr(s, "_client", _raise)
    r = call()
    assert isinstance(r, dict)
    assert "RuntimeError" in r["error"]


# --- 안전성 annotations --------------------------------------------------------

def _tools():
    return {t.name: t for t in s.mcp._tool_manager.list_tools()}


def test_every_tool_declares_annotations():
    for name, t in _tools().items():
        assert t.annotations is not None, f"{name} 에 annotations 없음"
        assert t.annotations.openWorldHint is True, f"{name}: 외부 API 조회이므로 openWorld"
        assert t.annotations.readOnlyHint is not None, f"{name}: readOnlyHint 미선언"


def test_write_tools_marked_non_destructive():
    """파일을 만드는 도구만 쓰기로 표시하고, 파괴적이지 않음을 명시한다."""
    tools = _tools()
    for name in ("scienceON_export", "scienceON_collect_groups"):
        a = tools[name].annotations
        assert a.readOnlyHint is False
        assert a.destructiveHint is False
    for name in ("scienceON_status", "scienceON_search", "scienceON_detail"):
        assert tools[name].annotations.readOnlyHint is True


# --- 다중그룹 수집 -------------------------------------------------------------

class _StubClient:
    def __init__(self, recs, meta):
        self._recs, self._meta = recs, meta

    def search_groups_meta(self, *a, **k):
        return list(self._recs), dict(self._meta)


def _recs(n):
    return [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(n)]


def test_collect_groups_rejects_empty_groups():
    r = s.scienceON_collect_groups(groups=[])
    assert "error" in r and "groups" in r["error"]


def test_collect_groups_caps_records_in_response(monkeypatch):
    """save=false 응답은 앞 100건만 싣되, 잘렸다는 사실을 표시한다."""
    meta = {"truncated": False, "union_upper_bound": 150, "returned": 150}
    monkeypatch.setattr(s, "_client", lambda: _StubClient(_recs(150), meta))
    r = s.scienceON_collect_groups(groups=[{"field": "BI", "terms": ["x"]}], save=False)
    assert r["count"] == 150
    assert len(r["records"]) == 100
    assert r["records_truncated_for_response"] is True


def test_collect_groups_surfaces_truncation_warning(monkeypatch):
    meta = {"truncated": True, "union_upper_bound": 9999, "returned": 10,
            "warning": "⚠️ 절단됨 — max_records=10 상한에 걸렸습니다."}
    monkeypatch.setattr(s, "_client", lambda: _StubClient(_recs(10), meta))
    r = s.scienceON_collect_groups(groups=[{"field": "BI", "terms": ["x"]}], save=False)
    assert r["meta"]["truncated"] is True
    assert "절단" in r["warning"]
