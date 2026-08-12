"""코드 리뷰 지적 회귀 테스트.

배경: 지적 7건 중 다수가 **테스트가 닿지 않는 지점**에 있었다. 특히 `cli.py` 는 어떤 테스트도
임포트하지 않아 문법 오류조차 통과했다. 그 사각을 함께 메운다.
"""
import importlib
import pathlib

import pytest
import requests

from scienceon_mcp import client as sc
from scienceon_mcp import server as s
from scienceon_mcp.models import Record


# ── 모든 모듈이 임포트되는가 (문법 오류 조기 검출) ────────────────────────────

@pytest.mark.parametrize("mod", [p.stem for p in
                                 sorted(pathlib.Path(__file__).parents[1]
                                        .glob("src/scienceon_mcp/*.py"))
                                 if p.stem != "__init__"])
def test_every_module_imports(mod):
    """회귀: cli.py 가 어떤 테스트에도 임포트되지 않아 깨진 문자열 리터럴이 통과했다."""
    importlib.import_module(f"scienceon_mcp.{mod}")


# ── 자격증명이 예외 메시지로 새지 않는가 (최우선) ────────────────────────────

def _resp(status, url):
    r = requests.Response()
    r.status_code, r.url, r.reason = status, url, "Unauthorized"
    return r


def test_http_error_does_not_leak_credentials(monkeypatch):
    """회귀: raise_for_status() 는 **요청 URL 전체**를 예외 메시지에 넣는다.

    이 URL 쿼리에는 client_id 와 access token 이 들어 있어, _safe 가 그 메시지를 응답에
    실으면 자격증명이 MCP 응답 → LLM 트랜스크립트로 흘러간다.
    """
    leaky = ("https://apigateway.kisti.re.kr/openapicall.do"
             "?client_id=SECRET_ID&token=SECRET_TOKEN&version=1.0")
    c = sc.ScienceONClient.__new__(sc.ScienceONClient)
    c.timeout, c.throttle = 5, 0
    c.creds = type("C", (), {"client_id": "SECRET_ID"})()
    c.tokens = type("T", (), {"get_access_token": lambda self: "SECRET_TOKEN"})()
    monkeypatch.setattr(sc.requests, "get", lambda *a, **k: _resp(401, leaky))

    with pytest.raises(sc.ScienceONError) as e:
        c._call({"action": "search"})
    msg = str(e.value)
    assert "SECRET_TOKEN" not in msg
    assert "SECRET_ID" not in msg
    assert "apigateway" not in msg      # URL 자체가 실리지 않는다


def test_network_error_does_not_leak_credentials(monkeypatch):
    """ConnectionError/Timeout/SSLError 도 메시지에 URL 을 담는다."""
    c = sc.ScienceONClient.__new__(sc.ScienceONClient)
    c.timeout, c.throttle = 5, 0
    c.creds = type("C", (), {"client_id": "SECRET_ID"})()
    c.tokens = type("T", (), {"get_access_token": lambda self: "SECRET_TOKEN"})()

    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError(
            "HTTPSConnectionPool: url=https://x/openapicall.do?token=SECRET_TOKEN")

    monkeypatch.setattr(sc.requests, "get", _boom)
    with pytest.raises(sc.ScienceONError) as e:
        c._call({"action": "search"})
    assert "SECRET_TOKEN" not in str(e.value)


def test_token_endpoint_does_not_leak_payload(monkeypatch):
    """토큰 URL 에는 accounts(AES 페이로드)·refreshToken 이 실린다."""
    from scienceon_mcp import auth

    def _boom(*a, **k):
        raise requests.exceptions.Timeout("timeout for url: https://x?accounts=SECRET_AES")

    monkeypatch.setattr(auth.requests, "get", _boom)
    with pytest.raises(RuntimeError) as e:
        auth._get_json("https://x?accounts=SECRET_AES", 5, "토큰 발급")
    assert "SECRET_AES" not in str(e.value)


# ── 마지막 축/그룹이 상한을 채워도 '조기 중단'이 아니다 ──────────────────────

def _stub_meta(recs, total):
    def _f(*a, **k):
        return list(recs), {"target": "ARTI", "query": {}, "total": total,
                            "fetched": len(recs), "truncated": False,
                            "total_mismatch": False, "sweeps": 1}
    return _f


def test_last_axis_filling_cap_is_not_early_stop(monkeypatch):
    """회귀: 마지막 축이 정확히 상한을 채우면 남은 축이 없는데도 truncated 가 붙었다.

    전수 수집된 코퍼스를 두고 max_records 를 올려 무의미한 재수집을 반복하게 된다.
    """
    recs = [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(5)]
    c = sc.ScienceONClient.__new__(sc.ScienceONClient)
    c.throttle = 0
    monkeypatch.setattr(c, "search_meta", _stub_meta(recs, 5))
    _, meta = c.search_terms_meta("ARTI", ["only"], max_records=5)
    assert meta["axes_run"] == meta["axes_planned"] == 1
    assert meta["truncated"] is False       # 마지막(유일) 축 → 조기 중단 아님


def test_non_last_axis_filling_cap_is_early_stop(monkeypatch):
    recs = [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(5)]
    c = sc.ScienceONClient.__new__(sc.ScienceONClient)
    c.throttle = 0
    monkeypatch.setattr(c, "search_meta", _stub_meta(recs, 5))
    _, meta = c.search_terms_meta("ARTI", ["t1", "t2"], max_records=5)
    assert meta["axes_run"] < meta["axes_planned"]
    assert meta["truncated"] is True


# ── 문서에 있는 스위치가 도구까지 닿는가 ─────────────────────────────────────

def test_retry_incomplete_reaches_tools(monkeypatch):
    """회귀: README 는 끌 수 있다고 안내하는데 도구·CLI 어디에도 인자가 없었다."""
    cap = {}

    class _C:
        def search_terms_meta(self, *a, **k):
            cap.update(k)
            return [], {"union_upper_bound": 0, "truncated": False,
                        "total_mismatch": False, "returned": 0}

    monkeypatch.setattr(s, "_client", lambda: _C())
    s.scienceON_search(query="x", retry_incomplete=0)
    assert cap["retry_incomplete"] == 0


def test_collect_groups_filename_includes_terms(monkeypatch):
    """회귀: 기본 파일명이 `{target}_groups` 고정이라 두 번째 호출이 첫 산출물을 덮어썼다."""
    seen = {}

    class _C:
        def search_groups_meta(self, *a, **k):
            return [], {"truncated": False, "total_mismatch": False, "returned": 0}

    monkeypatch.setattr(s, "_client", lambda: _C())
    monkeypatch.setattr("scienceon_mcp.exporters.export",
                        lambda recs, fmts, base, nm: seen.setdefault("nm", nm) or [])
    s.scienceON_collect_groups(groups=[{"field": "BI", "terms": ["경계선지능"]}])
    assert "경계선지능" in seen["nm"]
