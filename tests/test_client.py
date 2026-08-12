"""클라이언트 오류처리·후처리 필터 단위 테스트 (라이브 호출 없음)."""
import pytest

from scienceon_mcp.client import ScienceONClient, ScienceONError, _check_xml_error
from scienceon_mcp.models import Record

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MetaData><resultSummary><statusCode>401</statusCode></resultSummary>
<errorDetail><errorCode>E4103</errorCode><errorMessage>Access Token 값 오류</errorMessage></errorDetail></MetaData>"""

OK_XML = """<MetaData><resultSummary><statusCode>200</statusCode></resultSummary></MetaData>"""


def test_check_xml_error_raises():
    with pytest.raises(ScienceONError) as e:
        _check_xml_error(ERROR_XML)
    assert e.value.code == "E4103"


def test_check_xml_error_ok():
    _check_xml_error(OK_XML)  # 200 이면 예외 없음


def _client_without_init():
    c = ScienceONClient.__new__(ScienceONClient)  # __init__(자격증명) 우회
    c.throttle = 0
    return c


def _stub_search_meta(recs, total=None):
    """search_meta 대체 스텁 — (records, meta) 를 돌려준다.

    total 을 넘기면 서버가 보고한 전체 건수를 흉내낸다(절단 시나리오 재현용).
    """
    def _f(*a, **k):
        r = list(recs)
        t = len(r) if total is None else total
        return r, {"target": "ARTI", "query": {}, "total": t,
                   "fetched": len(r), "truncated": bool(t) and len(r) < t}
    return _f


def test_search_terms_contains_filter(monkeypatch):
    recs = [
        Record(source="ARTI", control_no="A", title="느린 학습자 연구",
               keywords=["느린 학습자"], raw={"Lang": "한국어"}),
        Record(source="ARTI", control_no="B", title="무관한 학습자 논문", raw={"Lang": "영어"}),
    ]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs))
    out = c.search_terms("ARTI", ["x"], contains=["느린 학습자"])
    assert [r.control_no for r in out] == ["A"]


def test_search_terms_lang_filter(monkeypatch):
    recs = [
        Record(source="ARTI", control_no="A", title="t", raw={"Lang": "한국어"}),
        Record(source="ARTI", control_no="B", title="t", raw={"Lang": "영어"}),
    ]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs))
    out = c.search_terms("ARTI", ["x"], lang=["한국어"])
    assert [r.control_no for r in out] == ["A"]


def test_search_terms_union_dedup(monkeypatch):
    # 여러 용어가 같은 CN 을 반환해도 합집합에서 중복 제거
    recs = [Record(source="ARTI", control_no="A", title="t", raw={})]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs))
    out = c.search_terms("ARTI", ["term1", "term2"])
    assert len(out) == 1


# --- 조용한 절단 방지 회귀 테스트 ---------------------------------------------

def test_search_terms_meta_flags_truncation(monkeypatch):
    """축이 잘리면 truncated=True 와 사람이 읽을 warning 이 반드시 붙는다."""
    recs = [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(10)]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs, total=500))
    out, meta = c.search_terms_meta("ARTI", ["x"], max_records=10)
    assert len(out) == 10
    assert meta["truncated"] is True
    assert meta["union_upper_bound"] == 500
    assert "warning" in meta and "500" in meta["warning"]


def test_search_terms_meta_no_false_alarm(monkeypatch):
    """전수 회수했으면 truncated=False 이고 warning 이 없어야 한다."""
    recs = [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(3)]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs, total=3))
    out, meta = c.search_terms_meta("ARTI", ["x"], max_records=100)
    assert meta["truncated"] is False
    assert "warning" not in meta
    assert meta["returned"] == len(out) == 3


def test_search_terms_meta_stops_early_marks_truncated(monkeypatch):
    """max_records 에 걸려 남은 축을 못 돌면 axes_run < axes_planned 이고 truncated=True."""
    recs = [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(5)]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs, total=5))
    out, meta = c.search_terms_meta("ARTI", ["t1", "t2", "t3"], max_records=5)
    assert meta["axes_planned"] == 3
    assert meta["axes_run"] == 1          # 첫 축에서 상한 도달 → 나머지 미실행
    assert meta["truncated"] is True


def test_search_terms_wrapper_keeps_list_contract(monkeypatch):
    """기존 호출부 호환 — search_terms 는 여전히 리스트만 반환한다."""
    recs = [Record(source="ARTI", control_no="A", title="t", raw={})]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs))
    out = c.search_terms("ARTI", ["x"])
    assert isinstance(out, list) and out[0].control_no == "A"


def test_search_groups_meta_aggregates(monkeypatch):
    """그룹 수집도 절단 사실을 합산해 노출한다."""
    recs = [Record(source="ARTI", control_no=f"A{i}", title="t", raw={}) for i in range(4)]
    c = _client_without_init()
    monkeypatch.setattr(c, "search_meta", _stub_search_meta(recs, total=99))
    out, meta = c.search_groups_meta("ARTI", [{"field": "BI", "terms": ["x"]}], max_records=50)
    assert meta["groups_planned"] == 1
    assert meta["truncated"] is True
    assert meta["union_upper_bound"] == 99
    assert "warning" in meta


# ── 불완전 회수 보정 (kci 에서 실측된 현상의 이식) ─────────────────────────────

def _rec(cn):
    return Record(source="ARTI", control_no=cn, title="t", raw={})


def test_retry_recovers_records_missed_by_unstable_paging(monkeypatch):
    """다중 페이지 질의에서 회수량이 흔들릴 때 재스윕으로 total 을 채운다.

    kci 실측: 동일 조건 3회에 204/204/205, 합집합 205·교집합 203.
    보정 off 면 204 고정, on 이면 205 회수됨을 라이브로 확인했다.
    """
    seq = {"n": 0}
    c = _client_without_init()

    def _page(target, query, *, page=1, rows=100, sort_field="", include=""):
        seq["n"] += 1
        if page > 1:
            return 2, [], ""
        return 2, [_rec("A" if seq["n"] <= 1 else "B")], ""

    monkeypatch.setattr(c, "search_page", _page)
    recs, meta = c.search_meta("ARTI", {"TI": "x"}, max_records=100)
    assert meta["sweeps"] == 2
    assert meta["fetched"] == 2 == meta["total"]
    assert meta["total_mismatch"] is False
    assert {r.control_no for r in recs} == {"A", "B"}


def test_retry_can_be_disabled(monkeypatch):
    c = _client_without_init()
    monkeypatch.setattr(c, "search_page",
                        lambda *a, **k: (2, [_rec("A")], "") if k.get("page", 1) == 1 else (2, [], ""))
    _, meta = c.search_meta("ARTI", {"TI": "x"}, max_records=100, retry_incomplete=0)
    assert meta["sweeps"] == 1
    assert meta["total_mismatch"] is True


def test_request_size_never_zero(monkeypatch):
    """rowCount=0 이면 API 가 total 까지 0 으로 준다 → 요청 크기 하한 1."""
    seen = {}
    c = _client_without_init()

    def _page(target, query, *, page=1, rows=100, **k):
        seen["rows"] = rows
        return (5, [_rec("A")], "") if page == 1 else (5, [], "")

    monkeypatch.setattr(c, "search_page", _page)
    c.search_meta("ARTI", {"TI": "x"}, max_records=0, rows=0)
    assert seen["rows"] >= 1
