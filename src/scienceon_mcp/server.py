"""ScienceON MCP 서버 (FastMCP).

Claude 등 MCP 클라이언트에 검색/상세/수집 도구를 노출한다.
자격증명은 MCP 설정의 env 블록 또는 .env 에서 로드한다.

검색필드(field): BI(전체) TI(제목) AB(초록) AU(저자) KW(키워드) PB(발행기관) PY(발행연도)
다중어는 queries=[...] 로 전달 → 서버측 OR(파이프)로 합집합. contains=[...] 는 후처리 필터.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import ScienceONClient, ScienceONError

mcp = FastMCP("scienceON")


def _client() -> ScienceONClient:
    return ScienceONClient()


def _year_str(year_from: int | None, year_to: int | None) -> str | None:
    if year_from and year_to:
        return f"{year_from}~{year_to}" if year_from != year_to else str(year_from)
    if year_from:
        return str(year_from)
    return None


def _terms(query: str | None, queries: list[str] | None) -> list[str]:
    if queries:
        return [q for q in queries if q and q.strip()]
    return [query] if query and query.strip() else []


@mcp.tool()
def scienceON_status() -> dict:
    """ScienceON 연결/토큰 상태 점검. 실패 시 원인 힌트와 현재 공인 IP 를 반환."""
    info: dict[str, Any] = {}
    try:
        import requests
        info["public_ip"] = requests.get("https://api.ipify.org", timeout=8).text
    except Exception:
        info["public_ip"] = "unknown"
    try:
        from .auth import TokenManager
        tok = TokenManager().get_access_token(force=True)
        info.update(ok=True, message="토큰 발급 성공", access_token_preview=tok[:8] + "…")
    except Exception as e:
        info.update(ok=False, error=str(e),
                    hint="E4006/IP 오류면 API Gateway IP관리에 위 public_ip 등록·활성화 필요.")
    return info


@mcp.tool()
def scienceON_search(query: str | None = None, queries: list[str] | None = None,
                     target: str = "ARTI", field: str = "BI",
                     year_from: int | None = None, year_to: int | None = None,
                     rows: int = 20, contains: list[str] | None = None,
                     lang: list[str] | None = None) -> dict:
    """ScienceON 문헌 검색.

    query: 단일 검색어 / queries: 여러 검색어(개별검색 후 CN 합집합) — 둘 중 하나
    target: ARTI(논문)·REPORT(보고서)·ATT(동향)·RESEARCHER·ORGAN
    field: BI(전체)·TI(제목)·AB(초록)·AU(저자)·KW(키워드). 와일드카드 `*` 사용 가능(예: 느린*).
    year_from~year_to: 발행연도(범위는 PY 틸드). rows: 반환 건수(최대 100).
    contains: 원본 전체필드에 이 문자열(들) 포함 결과만(대소문자 무시 후처리 필터).
    lang: 허용 언어(예: ["한국어"]) — 국내(국문) 한정 등.
    """
    terms = _terms(query, queries)
    if not terms:
        return {"error": "query 또는 queries 중 하나는 필요합니다."}
    try:
        recs = _client().search_terms(target, terms, field=field, year=_year_str(year_from, year_to),
                                      max_records=min(rows, 100), rows=min(rows, 100),
                                      contains=contains, lang=lang)
    except ScienceONError as e:
        return {"error": str(e)}
    recs = recs[:rows]
    return {"count": len(recs), "records": [r.to_row() for r in recs]}


@mcp.tool()
def scienceON_detail(control_no: str, target: str = "ARTI") -> dict:
    """제어번호(CN)로 상세 서지·초록 조회."""
    try:
        r = _client().detail(target, control_no)
    except ScienceONError as e:
        return {"error": str(e)}
    return r.to_row() if r else {"error": "결과 없음"}


@mcp.tool()
def scienceON_export(query: str | None = None, queries: list[str] | None = None,
                     target: str = "ARTI", field: str = "BI",
                     year_from: int | None = None, year_to: int | None = None,
                     contains: list[str] | None = None, lang: list[str] | None = None,
                     formats: list[str] | None = None, max_records: int = 500,
                     out_dir: str | None = None, name: str | None = None) -> dict:
    """검색 결과를 대량 수집해 파일로 저장(xlsx/csv/json/sqlite). 저장 경로 반환.

    queries=[...] 여러 용어 개별검색 후 CN 합집합. contains=[...] 후처리 필터, lang=["한국어"] 국내한정.
    out_dir 미지정 시 사용자 홈의 `scienceon-output/` 에 저장(MCP는 임의 cwd에서 기동).
    """
    from .exporters import export
    terms = _terms(query, queries)
    if not terms:
        return {"error": "query 또는 queries 중 하나는 필요합니다."}
    try:
        recs = _client().search_terms(target, terms, field=field, year=_year_str(year_from, year_to),
                                      max_records=max_records, rows=100, contains=contains, lang=lang)
    except ScienceONError as e:
        return {"error": str(e)}
    fmts = formats or ["xlsx", "csv", "json"]
    nm = (name or f"{target}_{terms[0]}").replace(" ", "_")[:60]
    base = out_dir or str(Path.home() / "scienceon-output")
    paths = export(recs, fmts, base, nm)
    return {"count": len(recs), "files": paths}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
