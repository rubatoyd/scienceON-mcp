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


def test_search_terms_contains_filter(monkeypatch):
    recs = [
        Record(source="ARTI", control_no="A", title="느린 학습자 연구",
               keywords=["느린 학습자"], raw={"Lang": "한국어"}),
        Record(source="ARTI", control_no="B", title="무관한 학습자 논문", raw={"Lang": "영어"}),
    ]
    c = _client_without_init()
    monkeypatch.setattr(c, "search", lambda *a, **k: list(recs))
    out = c.search_terms("ARTI", ["x"], contains=["느린 학습자"])
    assert [r.control_no for r in out] == ["A"]


def test_search_terms_lang_filter(monkeypatch):
    recs = [
        Record(source="ARTI", control_no="A", title="t", raw={"Lang": "한국어"}),
        Record(source="ARTI", control_no="B", title="t", raw={"Lang": "영어"}),
    ]
    c = _client_without_init()
    monkeypatch.setattr(c, "search", lambda *a, **k: list(recs))
    out = c.search_terms("ARTI", ["x"], lang=["한국어"])
    assert [r.control_no for r in out] == ["A"]


def test_search_terms_union_dedup(monkeypatch):
    # 여러 용어가 같은 CN 을 반환해도 합집합에서 중복 제거
    recs = [Record(source="ARTI", control_no="A", title="t", raw={})]
    c = _client_without_init()
    monkeypatch.setattr(c, "search", lambda *a, **k: list(recs))
    out = c.search_terms("ARTI", ["term1", "term2"])
    assert len(out) == 1
