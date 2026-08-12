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
from .config import API_URL, Credentials, use_os_trust
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
        use_os_trust()  # 교육망/사내망 SSL 인터셉션 CA를 OS 저장소로 신뢰(검증 유지)
        self.creds = creds or Credentials.from_env()
        self.tokens = token_manager or TokenManager(self.creds)
        self.throttle = throttle
        self.timeout = timeout

    def _call(self, params: dict) -> str:
        base = {"client_id": self.creds.client_id,
                "token": self.tokens.get_access_token(), "version": "1.0"}
        base.update(params)
        r = None
        for attempt in range(3):
            try:
                r = requests.get(API_URL, params=base, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                # ⚠️ 예외 객체를 그대로 올리면 안 된다 — requests 예외 메시지에는 **요청 URL 전체**가
                #    담기고, 이 URL 의 쿼리에는 client_id 와 access token 이 들어 있다.
                #    도구의 _safe 가 그 메시지를 응답에 실으면 자격증명이 LLM 트랜스크립트로 흘러간다.
                if attempt < 2:
                    time.sleep(1.5 * (2 ** attempt))
                    continue
                raise ScienceONError("NETWORK", f"네트워크 오류({type(e).__name__}) — 연결/SSL 확인 후 재시도.") from None
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (2 ** attempt))  # 지수 백오프
                continue
            break
        if r is None:  # pragma: no cover
            raise ScienceONError("NETWORK", "요청 실패.")
        if r.status_code == 429:
            raise ScienceONError("429", "요청 한도 초과(Too Many Requests). throttle 상향 또는 잠시 후 재시도.")
        if r.status_code >= 400:
            # ⚠️ raise_for_status() 금지 — 메시지에 token·client_id 가 든 URL 이 그대로 들어간다.
            raise ScienceONError(str(r.status_code), "ScienceON 서버 응답 오류.")
        # ⚠️ charset 헤더가 없으면 requests 가 Latin-1 로 폴백해 **한글이 통째로 깨진다**
        #    (적대적 검증에서 `한글 제목` → `í\x95\x9cê¸\x80` 로 재현). 서버가 헤더를 빼먹는
        #    경우가 실제로 있으므로 UTF-8 로 보정한다. 자매 프로젝트 nl 과 동일 처방.
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or "utf-8"
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
                    sort_field: str = "", include: str = "",
                    retry_incomplete: int = 1) -> tuple[list[Record], dict]:
        """search() + 회수 메타 — 조용한 절단 방지.

        meta = {target, query, total, fetched, truncated, total_mismatch, sweeps}
          total         : ScienceON 이 보고한 전체 건수(`TotalCount`)
          fetched       : 실제 회수·중복제거 후 반환 건수
          truncated     : **우리 상한(max_records)에 걸렸다** — 올리면 늘어난다
          total_mismatch: 끝까지 페이징했는데 total 에 못 미쳤다 — 올려도 늘지 않는다
          sweeps        : 1보다 크면 불완전 회수를 재스윕으로 보정한 것
        절단 여부를 호출자에게 **반드시** 노출한다 — 상한에 걸린 결과를 완전한 코퍼스로
        오인하면 계량서지·텍스트마이닝 분석 전체가 무효가 된다.
        """
        # ⚠️ 하한 1 필수 — rowCount=0 이면 API 가 total 까지 0 으로 돌려준다.
        #    그러면 결과가 실제로 있는데도 "결과 없음"으로 조용히 오보된다(kci 에서 실측 확인).
        rows = max(1, min(rows, 100))
        max_records = max(1, max_records)
        # ⚠️ 여러 페이지가 필요하면 **페이지 크기를 최대로 올린다.** rows 는 전송 단위일 뿐
        #    결과 집합을 바꾸지 않는데, 작게 두면 같은 데이터를 받으려고 요청 수만 늘어난다.
        #    적대적 검증에서 rows=1·max_records=300 조합이 **300회 요청**을 유발했다 —
        #    공공 API 에 대한 예의 문제이자 실패 확률·소요시간 문제다. nl 과 동일 처방.
        if max_records > rows:
            rows = 100
        # 그래도 폭주하지 않도록 절대 상한을 둔다(1000 페이지 가드는 너무 헐겁다).
        max_requests = max(2, -(-max_records // rows) + 2)
        requests_made = 0
        out: list[Record] = []
        seen: set = set()
        page = 1
        total = 0
        while len(out) < max_records and requests_made < max_requests:
            requests_made += 1
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
        # ── 불완전 회수 보정 ────────────────────────────────────────────────────
        # 다중 페이지 질의에서 회수량이 호출마다 흔들린다(kci 실측: 동일 조건 3회에 204/204/205,
        # 합집합 205·교집합 203). 페이지 경계에서 정렬이 미세하게 바뀌면 한 건이 두 페이지 사이로
        # 빠지는 것으로 보인다. 단일 페이지 질의는 안정적이었다.
        # → total 에 못 미쳤고 우리 상한도 아니면 한 번 더 훑어 합집합을 취한다(코퍼스 재현성).
        sweeps = 1
        while (retry_incomplete > 0 and total and len(out) < min(total, max_records)
               and len(out) < max_records):
            retry_incomplete -= 1
            sweeps += 1
            before = len(out)
            page = 1
            while len(out) < max_records and page <= 1000:
                _, recs2, _ = self.search_page(target, query, page=page, rows=rows,
                                               sort_field=sort_field, include=include)
                if not recs2:
                    break
                for r in recs2:
                    k = r.control_no or (r.title, r.pub_year)
                    if k not in seen:
                        seen.add(k)
                        out.append(r)
                if total and page * rows >= total:
                    break
                page += 1
                time.sleep(self.throttle)
            if len(out) == before:
                break

        out = out[:max_records]
        # ⚠️ truncated 와 total_mismatch 를 **분리**한다 (2026-08-11 적대적 검증에서 발견).
        #    예전엔 `fetched < total` 하나로 뭉쳐 있어, 페이징을 끝까지 돌았는데도 truncated=True 가
        #    떴다(실측: TI '경계선지능' total 263 / 실회수 262, 중복제거 0건).
        #    API 의 total 은 **실제 서빙량보다 클 수 있다**. 그때 "max_records 를 올리라"는 조언은
        #    틀린 처방이며 사용자를 무한 재수집으로 몬다.
        # 상한에 닿았더라도 total 을 다 채웠으면 잘린 것이 없다 — 그때 truncated 를 붙이면
        # 전수 수집한 결과에 경고가 달려 무의미한 재수집을 유도한다.
        hit_cap = len(out) >= max_records and (not total or len(out) < total)
        return out, {"target": target, "query": query, "total": total, "fetched": len(out),
                     "truncated": hit_cap,          # 우리 상한에 걸림 → 올리면 해결된다
                     "sweeps": sweeps,              # 1보다 크면 불완전 회수를 보정한 것
                     "total_mismatch": (not hit_cap) and bool(total) and len(out) < total}

    def search(self, target: str, query, *, max_records: int = 100, rows: int = 100,
               sort_field: str = "", include: str = "") -> list[Record]:
        """레코드만 반환하는 얇은 래퍼. 절단 여부까지 필요하면 search_meta() 를 쓴다."""
        return self.search_meta(target, query, max_records=max_records, rows=rows,
                                sort_field=sort_field, include=include)[0]

    def search_terms_meta(self, target: str, terms, *, field: str = "BI", year: str | None = None,
                          max_records: int = 3000, rows: int = 100, sort_field: str = "",
                          include: str = "", contains=None, lang=None,
                          retry_incomplete: int = 1) -> tuple[list[Record], dict]:
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
                                       sort_field=sort_field, include=include,
                                       retry_incomplete=retry_incomplete)
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
                # ⚠️ **마지막 축이면 남은 축이 없으므로 '조기 중단'이 아니다.**
                #    그대로 True 로 두면 전수 수집한 코퍼스에 truncated 가 붙어, 사용자가
                #    max_records 를 올려 무의미한 재수집을 반복하게 된다.
                stopped_early = term is not terms[-1]
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
            # API 가 보고한 total 이 실제 서빙량보다 큰 축이 하나라도 있으면 표시.
            # 절단과 달리 max_records 를 올려도 해결되지 않는다 → 조언이 달라야 한다.
            "total_mismatch": any(a.get("total_mismatch") for a in axes),
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
        elif meta["total_mismatch"]:
            # 상한에 걸리지 않았는데 total 에 못 미친 경우 — 올려도 해결되지 않는다.
            meta["notice"] = (
                "ℹ️ API 가 보고한 total 보다 실제 회수량이 적습니다. 페이징은 끝까지 돌았으므로 "
                "**절단이 아니며 max_records 를 올려도 늘지 않습니다** — API 의 total 이 실제 서빙 "
                "가능 건수보다 큰 경우입니다(실측 확인). 회수량을 확정 수치로 쓰세요."
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
                           sort_field: str = "",
                           retry_incomplete: int = 1) -> tuple[list[Record], dict]:
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
                sort_field=sort_field, contains=g.get("contains"), lang=g.get("lang"),
                retry_incomplete=retry_incomplete)
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
                           "returned": gm["returned"], "truncated": gm["truncated"],
                           "total_mismatch": gm.get("total_mismatch", False), "new": new})
            if len(out) >= max_records:
                stopped_early = g is not groups[-1]   # 마지막 그룹이면 조기 중단이 아니다
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
            "total_mismatch": any(g.get("total_mismatch") for g in gmetas),
            "returned": len(out),
        }
        if meta["truncated"]:
            meta["warning"] = (
                f"⚠️ 절단됨 — max_records={max_records} 상한에 걸렸습니다. "
                f"실행한 그룹 {len(gmetas)}/{len(groups)}개의 total 합은 "
                f"{meta['union_upper_bound']}건(합집합 상한)입니다. max_records 를 올려 재수집하세요."
            )
        elif meta["total_mismatch"]:
            meta["notice"] = (
                "ℹ️ API 가 보고한 total 보다 실제 회수량이 적습니다. 페이징은 끝까지 돌았으므로 "
                "**절단이 아니며 max_records 를 올려도 늘지 않습니다.** 회수량을 확정 수치로 쓰세요."
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
