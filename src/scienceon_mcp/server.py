"""ScienceON MCP 서버 (FastMCP).

Claude 등 MCP 클라이언트에 검색/상세/수집 도구를 노출한다.
자격증명은 MCP 설정의 env 블록 또는 .env 에서 로드한다.

검색필드(field): BI(전체) TI(제목) AB(초록) AU(저자) KW(키워드) PB(발행기관) PY(발행연도)
다중어는 queries=[...] 로 전달 → 서버측 OR(파이프)로 합집합. contains=[...] 는 후처리 필터.
"""
from __future__ import annotations

import argparse
import functools
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import ScienceONClient, ScienceONError

mcp = FastMCP("scienceON")


def _safe(fn):
    """도구는 **항상 JSON 직렬화 가능한 dict** 를 반환 — 어떤 예외도 도구 밖으로 누수 금지.

    (네트워크/SSL/HTTP/파싱/자격증명 예외가 MCP 프로토콜 밖으로 새어 클라이언트가 깨지는 것을 방지.
    ScienceONError 만 잡던 시절에는 자격증명 누락이 RuntimeError 로 그대로 새어나갔다 — 실측 확인.
    자격증명 자체는 auth/_call 단계에서 메시지에 실리지 않으므로 노출 위험 없음.)
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapper


# 도구 안전성 힌트(MCP annotations) — 디렉터리 심사·클라이언트 표시에 사용.
# 전부 외부 API 조회(openWorld). export 만 파일 생성(쓰기, 비파괴).
_READ = {"readOnlyHint": True, "openWorldHint": True}
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}


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


@mcp.tool(annotations=_READ)
@_safe
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


@mcp.tool(annotations=_READ)
@_safe
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

    반환값의 total 은 ScienceON 이 보고한 전체 건수(축별 합, 합집합 상한)이고,
    truncated=true 면 rows 상한에 잘린 것이다. 이때 warning 이 함께 붙는다.
    ⚠️ 절단된 결과를 완전한 코퍼스로 오인하면 후속 분석이 무효가 된다.
    """
    terms = _terms(query, queries)
    if not terms:
        return {"error": "query 또는 queries 중 하나는 필요합니다."}
    try:
        recs, meta = _client().search_terms_meta(
            target, terms, field=field, year=_year_str(year_from, year_to),
            max_records=min(rows, 100), rows=min(rows, 100),
            contains=contains, lang=lang)
    except ScienceONError as e:
        return {"error": str(e)}
    recs = recs[:rows]
    out = {"count": len(recs), "total": meta["union_upper_bound"],
           "truncated": meta["truncated"], "records": [r.to_row() for r in recs]}
    if meta.get("warning"):
        out["warning"] = meta["warning"]
    return out


@mcp.tool(annotations=_READ)
@_safe
def scienceON_detail(control_no: str, target: str = "ARTI") -> dict:
    """제어번호(CN)로 상세 서지·초록 조회."""
    try:
        r = _client().detail(target, control_no)
    except ScienceONError as e:
        return {"error": str(e)}
    return r.to_row() if r else {"error": "결과 없음"}


@mcp.tool(annotations=_WRITE)
@_safe
def scienceON_export(query: str | None = None, queries: list[str] | None = None,
                     target: str = "ARTI", field: str = "BI",
                     year_from: int | None = None, year_to: int | None = None,
                     contains: list[str] | None = None, lang: list[str] | None = None,
                     formats: list[str] | None = None, max_records: int = 500,
                     out_dir: str | None = None, name: str | None = None) -> dict:
    """검색 결과를 대량 수집해 파일로 저장(xlsx/csv/json/sqlite). 저장 경로 반환.

    queries=[...] 여러 용어 개별검색 후 CN 합집합. contains=[...] 후처리 필터, lang=["한국어"] 국내한정.
    out_dir 미지정 시 사용자 홈의 `scienceon-output/` 에 저장(MCP는 임의 cwd에서 기동).

    ⚠️ **max_records(기본 500)는 조용히 자르지 않는다** — 상한에 걸리면 meta.truncated=true 와
    warning 이 붙는다. meta.union_upper_bound 는 실행한 검색축들의 total 합(합집합 상한)이므로,
    절단됐다면 max_records 를 그 위로 올려 재수집해야 코퍼스가 완결된다.
    수집량이 max_records 와 정확히 일치하면 거의 항상 절단이다.
    """
    from .exporters import export
    terms = _terms(query, queries)
    if not terms:
        return {"error": "query 또는 queries 중 하나는 필요합니다."}
    try:
        recs, meta = _client().search_terms_meta(
            target, terms, field=field, year=_year_str(year_from, year_to),
            max_records=max_records, rows=100, contains=contains, lang=lang)
    except ScienceONError as e:
        return {"error": str(e)}
    fmts = formats or ["xlsx", "csv", "json"]
    nm = (name or f"{target}_{terms[0]}").replace(" ", "_")[:60]
    base = out_dir or str(Path.home() / "scienceon-output")
    paths = export(recs, fmts, base, nm)
    out = {"count": len(recs), "files": paths,
           "meta": {k: meta[k] for k in ("axes", "axes_planned", "axes_run", "union",
                                         "union_upper_bound", "max_records", "truncated",
                                         "returned") if k in meta}}
    if meta.get("warning"):
        out["warning"] = meta["warning"]
    return out


@mcp.tool(annotations=_WRITE)
@_safe
def scienceON_collect_groups(groups: list[dict], target: str = "ARTI",
                             year_from: int | None = None, year_to: int | None = None,
                             max_records: int = 3000, save: bool = True,
                             formats: list[str] | None = None,
                             out_dir: str | None = None, name: str | None = None) -> dict:
    """여러 **검색 그룹**을 한 코퍼스로 합쳐 수집(CN 중복제거). config 파일 없이 대화형으로.

    그룹마다 다른 필드·후처리 필터를 걸 수 있어, 단일 검색어로는 못 만드는 코퍼스를 만든다.
    각 group = {"field": "BI", "terms": [...], "contains": [...], "lang": [...], "max": N}
      field   : BI(전체)·TI(제목)·AB(초록)·AU(저자)·KW(키워드)
      terms   : 그 필드로 **개별 검색**할 용어들(와일드카드 `*` 가능)
      contains: 원본 전체필드 substring 후처리 필터(노이즈 제거, 대소문자 무시)
      lang    : 허용 언어(예: ["한국어"]) — 국문 논문 한정 등
      max     : 그 그룹만의 상한(미지정 시 max_records)

    예) 변별력 있는 단어는 BI 로 그대로, 색인 안 되는 토큰은 TI 와일드카드 + contains 로 정밀화:
        [{"field":"BI","terms":["경계선지능","경계선 지능"]},
         {"field":"TI","terms":["느린*"],"contains":["느린학습자","느린 학습자"]}]

    save=true(기본) 면 파일로 저장하고 경로를 반환한다. save=false 면 레코드를 직접 반환하되
    응답 폭주를 막기 위해 **앞 100건만** 싣는다(meta 는 전량 기준).

    ⚠️ meta.truncated=true 면 상한에 걸려 잘린 것이다 — meta.union_upper_bound(그룹별 total 합)
    위로 max_records 를 올려 재수집해야 코퍼스가 완결된다.
    """
    if not groups:
        return {"error": "groups 는 최소 1개 필요합니다. 예: [{\"field\":\"BI\",\"terms\":[\"경계선지능\"]}]"}
    try:
        recs, meta = _client().search_groups_meta(
            target, groups, year=_year_str(year_from, year_to), max_records=max_records)
    except ScienceONError as e:
        return {"error": str(e)}
    out: dict[str, Any] = {"count": len(recs), "meta": meta}
    if save:
        from .exporters import export
        fmts = formats or ["xlsx", "csv", "json"]
        nm = (name or f"{target}_groups").replace(" ", "_")[:60]
        base = out_dir or str(Path.home() / "scienceon-output")
        out["files"] = export(recs, fmts, base, nm)
    else:
        out["records"] = [r.to_row() for r in recs[:100]]
        out["records_truncated_for_response"] = len(recs) > 100
    if meta.get("warning"):
        out["warning"] = meta["warning"]
    return out


def _env_port(name: str) -> int | None:
    """숫자가 아니면 조용히 무시 — 잘못된 환경변수 하나로 서버가 못 뜨면 안 된다."""
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.isdigit() else None


def main(argv: list[str] | None = None) -> None:
    """MCP 서버 기동.

    기본은 **stdio** — 클라이언트가 로컬 서브프로세스로 띄우는 방식이고 기존 동작과 동일하다.
    `--transport sse|streamable-http` 로 HTTP 전송도 된다. MCP 를 지원하는 어떤 클라이언트든
    (Cursor·Cline·Zed·OpenAI Agents SDK·자체 에이전트) 붙을 수 있고, 원격 호스팅도 가능하다.

    ⚠️ **HTTP 전송에는 인증이 없다.** 기본 바인드는 루프백(127.0.0.1)이다. 외부 주소에 열면
       자격증명을 품은 서버를 그대로 공개하는 것과 같으므로 신뢰된 망에서만 쓸 것.
    """
    p = argparse.ArgumentParser(prog="scienceon-mcp", description="KISTI ScienceON MCP 서버")
    p.add_argument("--transport", choices=["stdio", "sse", "streamable-http"],
                   default=os.environ.get("SCIENCEON_MCP_TRANSPORT") or "stdio",
                   help="전송 방식 (기본 stdio). 환경변수 SCIENCEON_MCP_TRANSPORT 로도 지정 가능.")
    p.add_argument("--host", default=os.environ.get("SCIENCEON_MCP_HOST"),
                   help="HTTP 전송 바인드 주소 (기본 127.0.0.1 — 루프백)")
    p.add_argument("--port", type=int, default=_env_port("SCIENCEON_MCP_PORT"),
                   help="HTTP 전송 포트 (기본 8000)")
    # 클라이언트가 예기치 않은 인자를 넘겨도 서버는 떠야 한다 → 미지의 인자는 경고만 하고 무시
    args, unknown = p.parse_known_args(argv)
    if unknown:
        print(f"[scienceon-mcp] 알 수 없는 인자 무시: {unknown}", file=sys.stderr)
    if args.host:
        mcp.settings.host = args.host
    if args.port:
        mcp.settings.port = args.port
    if args.transport != "stdio":
        path = mcp.settings.sse_path if args.transport == "sse" else mcp.settings.streamable_http_path
        print(f"[scienceon-mcp] {args.transport} 전송 — "
              f"http://{mcp.settings.host}:{mcp.settings.port}{path}", file=sys.stderr)
        if mcp.settings.host not in ("127.0.0.1", "localhost", "::1"):
            print("[scienceon-mcp] ⚠️ 루프백 외 주소에 바인드했습니다. HTTP 전송에는 인증이 없어 "
                  "자격증명을 가진 서버가 그대로 노출됩니다. 신뢰된 망에서만 사용하세요.", file=sys.stderr)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
