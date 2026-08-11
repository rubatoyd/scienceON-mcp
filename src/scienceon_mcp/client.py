"""ScienceON OpenAPI 호출 클라이언트 — 검색/상세/페이징.

데이터 호출(라이브 검증):
  openapicall.do?client_id=&token=&version=1.0&action=search|browse
                &target=ARTI|REPORT|...&searchQuery={"필드":"검색어"}&curPage=&rowCount=
응답: XML (성공 시 resultSummary/statusCode=200, 레코드는 .//record/item[@metaCode]).
"""
from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET

import requests

from .auth import TokenManager
from .config import API_URL, Credentials
from .models import Record
from .parser import normalize, parse_response


class ScienceONError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


_HINTS = {
    "E4006": "토큰 발급용 MAC 추출 실패(암호화 오류). 인증키/암호화 스킴 확인.",
    "E4107": "accounts MAC 이 신청 MAC 과 불일치.",
    "E4103": "Access Token 만료/오류 — 재발급 필요.",
    "E4104": "신청정보가 승인상태가 아님.",
    "E4007": "searchField(검색필드) 값 오류.",
    "E4008": "target 값 오류.",
}


def _check_xml_error(text: str) -> None:
    if "errorCode" not in text and "errorDetail" not in text:
        return
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return
    sc = (root.findtext(".//statusCode") or "").strip()
    if sc and sc != "200":
        code = (root.findtext(".//errorCode") or sc).strip()
        msg = (root.findtext(".//errorMessage") or root.findtext(".//statusMessage") or "").strip()
        if code in _HINTS:
            msg = f"{msg} — {_HINTS[code]}"
        raise ScienceONError(code, msg)


class ScienceONClient:
    def __init__(self, creds: Credentials | None = None, *, throttle: float = 0.5,
                 timeout: int = 20, token_manager: TokenManager | None = None):
        self.creds = creds or Credentials.from_env()
        self.tokens = token_manager or TokenManager(self.creds)
        self.throttle = throttle
        self.timeout = timeout

    def _call(self, params: dict) -> str:
        base = {"client_id": self.creds.client_id,
                "token": self.tokens.get_access_token(), "version": "1.0"}
        base.update(params)
        for attempt in range(3):
            r = requests.get(API_URL, params=base, timeout=self.timeout)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (2 ** attempt))  # 지수 백오프
                continue
            break
        if r.status_code == 429:
            raise ScienceONError("429", "요청 한도 초과(Too Many Requests). throttle 상향 또는 잠시 후 재시도.")
        r.raise_for_status()
        _check_xml_error(r.text)
        return r.text

    def search_page(self, target: str, query, *, page: int = 1, rows: int = 20,
                    sort_field: str = "", include: str = "") -> tuple[int, list[Record], str]:
        q = query if isinstance(query, str) else json.dumps(query, ensure_ascii=False, separators=(",", ":"))
        params = {"action": "search", "target": target, "searchQuery": q,
                  "curPage": page, "rowCount": rows}
        if sort_field:
            params["sortField"] = sort_field
        if include:
            params["include"] = include
        text = self._call(params)
        total, raws = parse_response(text)
        return total, [normalize(r, target) for r in raws], text

    def search_meta(self, target: str, query, *, max_records: int = 100, rows: int = 100,
                    sort_field: str = "", include: str = "") -> tuple[list[Record], dict]:
        """search() + 회수 메타 — 조용한 절단 방지.

        meta = {target, query, total, fetched, truncated}
          total    : ScienceON 이 보고한 전체 건수(`TotalCount`)
          fetched  : 실제 회수·중복제거 후 반환 건수
          truncated: fetched < total (= max_records 상한에 걸려 잘렸다는 뜻)
        절단 여부를 호출자에게 **반드시** 노출한다 — 상한에 걸린 결과를 완전한 코퍼스로
        오인하면 계량서지·텍스트마이닝 분석 전체가 무효가 된다.
        """
        out: list[Record] = []
        seen: set = set()
        page = 1
        total = 0
        while len(out) < max_records and page <= 1000:
            total_p, recs, _ = self.search_page(target, query, page=page, rows=rows,
                                                sort_field=sort_field, include=include)
            if total_p:
                total = total_p
            if not recs:
                break
            before = len(out)
            for r in recs:
                key = r.control_no or (r.title, r.pub_year)
                if key in seen:
                    continue
                seen.add(key)
                out.append(r)
            if len(out) == before:  # 이번 페이지에 새 레코드 없음 → 종료(끝/중복)
                break
            if total and page * rows >= total:
                break
            page += 1
            time.sleep(self.throttle)
        out = out[:max_records]
        return out, {"target": target, "query": query, "total": total, "fetched": len(out),
                     "truncated": bool(total) and len(out) < total}

    def search(self, target: str, query, *, max_records: int = 100, rows: int = 100,
               sort_field: str = "", include: str = "") -> list[Record]:
        """레코드만 반환하는 얇은 래퍼. 절단 여부까지 필요하면 search_meta() 를 쓴다."""
        return self.search_meta(target, query, max_records=max_records, rows=rows,
                                sort_field=sort_field, include=include)[0]

    def search_terms_meta(self, target: str, terms, *, field: str = "BI", year: str | None = None,
                          max_records: int = 3000, rows: int = 100, sort_field: str = "",
                          include: str = "", contains=None, lang=None) -> tuple[list[Record], dict]:
        """여러 검색어를 **각각 개별 검색**해 CN 기준 합집합(중복제거) + 회수 메타.

        (서버측 파이프 OR 은 공백 포함 용어에서 토큰이 분리돼 과대매칭되므로 사용하지 않는다.)
        contains: 원본 전체 필드(국문/영문 제목·초록·키워드 등)에 해당 문자열(들)이 포함된
                  레코드만 남김(대소문자 무시). 예: '느린학습자' 또는 'borderline intellectual functioning'.
        lang: 허용 언어(예: ['한국어']) — raw 의 Lang 으로 국내(국문) 한정 등에 사용.

        meta = {axes[], axes_planned, axes_run, union, union_upper_bound,
                max_records, truncated, returned, (contains_filtered_out), (warning)}
          union_upper_bound: 실행한 축들의 total 합 = 합집합 크기의 **상한**(중복 미보정)
          truncated: 상한에 걸려 축을 다 못 돌았거나 어느 축이든 잘렸으면 True
        """
        terms = [t.strip() for t in (terms or []) if t and t.strip()]
        out: list[Record] = []
        seen: set = set()
        axes: list[dict] = []
        stopped_early = False
        for term in terms:
            q = {field: term}
            if year:
                q["PY"] = year
            recs, m = self.search_meta(target, q, max_records=max_records, rows=rows,
                                       sort_field=sort_field, include=include)
            new = 0
            for r in recs:
                key = r.control_no or (r.title, r.pub_year)
                if key in seen:
                    continue
                seen.add(key)
                out.append(r)
                new += 1
            axes.append({**m, "term": term, "field": field, "new": new})
            if len(out) >= max_records:
                stopped_early = True
                break
        out = out[:max_records]
        planned = len(terms)
        meta = {
            "axes": axes,
            "axes_planned": planned,
            "axes_run": len(axes),
            "union": len(out),
            "union_upper_bound": sum(a["total"] for a in axes),
            "max_records": max_records,
            "truncated": bool(stopped_early or len(axes) < planned
                              or any(a["truncated"] for a in axes)),
        }
        if contains:
            subs = [s.lower() for s in ([contains] if isinstance(contains, str) else list(contains))]

            def _hit(r: Record) -> bool:
                parts = [r.title, r.abstract,
                         "; ".join(r.keywords) if isinstance(r.keywords, list) else (r.keywords or "")]
                parts += [v for v in r.raw.values() if isinstance(v, str)]
                hay = "\n".join(parts).lower()
                return any(s in hay for s in subs)

            kept = [r for r in out if _hit(r)]
            meta["contains_filtered_out"] = len(out) - len(kept)
            out = kept
        if lang:
            langs = [lang] if isinstance(lang, str) else list(lang)
            kept = [r for r in out if (r.raw.get("Lang") or "") in langs]
            meta["lang_filtered_out"] = len(out) - len(kept)
            out = kept
        meta["returned"] = len(out)
        if meta["truncated"]:
            meta["warning"] = (
                f"⚠️ 절단됨 — max_records={max_records} 상한에 걸렸습니다. "
                f"실행한 검색축 {len(axes)}/{planned}개의 total 합은 {meta['union_upper_bound']}건"
                f"(합집합 상한)입니다. max_records 를 그 위로 올려 재수집하세요."
            )
        return out, meta

    def search_terms(self, target: str, terms, *, field: str = "BI", year: str | None = None,
                     max_records: int = 3000, rows: int = 100, sort_field: str = "",
                     include: str = "", contains=None, lang=None) -> list[Record]:
        """레코드만 반환하는 얇은 래퍼. 절단 여부까지 필요하면 search_terms_meta() 를 쓴다."""
        return self.search_terms_meta(target, terms, field=field, year=year,
                                      max_records=max_records, rows=rows, sort_field=sort_field,
                                      include=include, contains=contains, lang=lang)[0]

    def search_groups_meta(self, target: str, groups, *, year: str | None = None,
                           max_records: int = 3000, rows: int = 100,
                           sort_field: str = "") -> tuple[list[Record], dict]:
        """여러 검색 그룹을 합집합(CN 중복제거) + 회수 메타.

        각 group = {field, terms:[...], contains:[...]} — 그룹별로 다른 필드·후처리 필터 적용.
        예) 경계선지능(BI, 필터 없음) + 느린*(TI, contains=느린학습자) 를 한 코퍼스로.

        meta = {groups[], groups_planned, groups_run, union, union_upper_bound,
                max_records, truncated, returned, (warning)}
        """
        out: list[Record] = []
        seen: set = set()
        gmetas: list[dict] = []
        groups = list(groups or [])
        stopped_early = False
        for g in groups:
            terms = g.get("terms") or ([g["term"]] if g.get("term") else [])
            recs, gm = self.search_terms_meta(
                target, terms, field=g.get("field", "BI"), year=year,
                max_records=int(g.get("max", max_records)), rows=rows,
                sort_field=sort_field, contains=g.get("contains"), lang=g.get("lang"))
            new = 0
            for r in recs:
                key = r.control_no or (r.title, r.pub_year)
                if key in seen:
                    continue
                seen.add(key)
                out.append(r)
                new += 1
            gmetas.append({"field": g.get("field", "BI"), "terms": terms,
                           "union_upper_bound": gm["union_upper_bound"],
                           "returned": gm["returned"], "truncated": gm["truncated"], "new": new})
            if len(out) >= max_records:
                stopped_early = True
                break
        out = out[:max_records]
        meta = {
            "groups": gmetas,
            "groups_planned": len(groups),
            "groups_run": len(gmetas),
            "union": len(out),
            "union_upper_bound": sum(g["union_upper_bound"] for g in gmetas),
            "max_records": max_records,
            "truncated": bool(stopped_early or len(gmetas) < len(groups)
                              or any(g["truncated"] for g in gmetas)),
            "returned": len(out),
        }
        if meta["truncated"]:
            meta["warning"] = (
                f"⚠️ 절단됨 — max_records={max_records} 상한에 걸렸습니다. "
                f"실행한 그룹 {len(gmetas)}/{len(groups)}개의 total 합은 "
                f"{meta['union_upper_bound']}건(합집합 상한)입니다. max_records 를 올려 재수집하세요."
            )
        return out, meta

    def search_groups(self, target: str, groups, *, year: str | None = None,
                      max_records: int = 3000, rows: int = 100, sort_field: str = "") -> list[Record]:
        """레코드만 반환하는 얇은 래퍼. 절단 여부까지 필요하면 search_groups_meta() 를 쓴다."""
        return self.search_groups_meta(target, groups, year=year, max_records=max_records,
                                       rows=rows, sort_field=sort_field)[0]

    def detail(self, target: str, cn: str) -> Record | None:
        text = self._call({"action": "browse", "target": target, "cn": cn})
        _, raws = parse_response(text)
        return normalize(raws[0], target) if raws else None
