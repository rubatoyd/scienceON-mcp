"""ScienceON 수집기 CLI — status / search / detail / collect.

예:
  scienceon status
  scienceon search --query 경계선지능 --query 느린학습자 --target ARTI --year 2015~2024 --rows 50
  scienceon detail --target ARTI --cn JAKO202109950460817
  scienceon collect --config config/search.example.yaml
"""
from __future__ import annotations

import argparse
import sys

from .client import ScienceONClient, ScienceONError


def cmd_status(args) -> int:
    try:
        import requests
        ip = requests.get("https://api.ipify.org", timeout=8).text
    except Exception:
        ip = "unknown"
    print("public_ip:", ip)
    try:
        from .auth import TokenManager
        tok = TokenManager().get_access_token(force=True)
        print("OK: 토큰 발급 성공 (", tok[:8], "… )")
        return 0
    except Exception as e:
        print("FAIL:", e)
        print("힌트: E4006/IP 오류면 API Gateway IP관리에 위 public_ip 등록·활성화 필요.")
        return 1


def cmd_search(args) -> int:
    try:
        recs = ScienceONClient().search_terms(
            args.target, args.query, field=args.field, year=args.year,
            max_records=max(args.rows, 100), rows=min(args.rows, 100), contains=args.contains)
    except ScienceONError as e:
        print("오류:", e)
        return 1
    for r in recs[:args.rows]:
        print(f"[{r.pub_year}] {r.title}  / {'; '.join(r.authors)}  ({r.control_no})")
    print(f"\n표시 {min(len(recs), args.rows)}건 / 합집합 {len(recs)}건")
    return 0


def cmd_detail(args) -> int:
    try:
        r = ScienceONClient().detail(args.target, args.cn)
    except ScienceONError as e:
        print("오류:", e)
        return 1
    if not r:
        print("결과 없음")
        return 1
    for k, v in r.to_row().items():
        print(f"{k:12}: {v}")
    return 0


def _collect_target(client: ScienceONClient, target: str, cfg: dict, common: dict):
    """단일 target 수집 — searches(다중그룹) 우선, 없으면 terms/query. (records, meta) 반환."""
    if cfg.get("searches"):
        return client.search_groups_meta(target, cfg["searches"], **common)
    terms = cfg.get("terms") or ([cfg["query"]] if cfg.get("query") else [])
    if not terms:
        raise ValueError("config 에 searches / terms / query 중 하나가 필요합니다.")
    return client.search_terms_meta(target, terms, field=cfg.get("field", "BI"),
                                    contains=cfg.get("contains"), **common)


def cmd_collect(args) -> int:
    import yaml
    from .exporters import export
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    year = str(cfg["year"]) if cfg.get("year") else None
    sort = cfg.get("sort") or {}
    common = dict(year=year, max_records=int(cfg.get("max_records", 2000)),
                  rows=int(cfg.get("rows_per_page", 100)), sort_field=sort.get("field", ""))
    client = ScienceONClient(throttle=float(cfg.get("throttle_sec", 0.5)))
    targets = cfg.get("targets") or [cfg.get("target", "ARTI")]
    try:
        recs: list = []
        seen: set = set()
        metas: list[tuple[str, dict]] = []
        for tgt in targets:  # 다중 target(예: ARTI+REPORT) → CN 합집합
            got, meta = _collect_target(client, tgt, cfg, common)
            metas.append((tgt, meta))
            for r in got:
                key = r.control_no or (r.title, r.pub_year)
                if key in seen:
                    continue
                seen.add(key)
                recs.append(r)
    except (ScienceONError, ValueError) as e:
        print("오류:", e)
        return 1
    out = cfg.get("output", {})
    project = cfg.get("project", "collect")
    paths = export(recs, out.get("formats", ["xlsx", "csv", "json"]),
                   out.get("dir", f"output/{project}"), project)
    from collections import Counter
    bysrc = Counter(r.source for r in recs)
    print(f"수집 {len(recs)}건 (target {','.join(targets)} → {dict(bysrc)}) 저장:")
    for p in paths:
        print("  -", p)
    # 조용한 절단 방지 — 상한에 걸린 코퍼스를 완전한 것으로 오인하면 후속 분석이 무효가 된다
    for tgt, meta in metas:
        if meta.get("truncated"):
            print(f"\n⚠️ [{tgt}] {meta.get('warning', '절단됨')}")
        elif meta.get("total_mismatch"):
            # 끝까지 돌았지만 total 에 못 미친 경우 — 여기서 "전수 수집"이라고 하면 오보다
            print(f"\nℹ️ [{tgt}] {meta.get('notice', 'total 과 회수량이 다릅니다')}")
        else:
            print(f"   [{tgt}] 전수 수집 (상한 {meta.get('max_records')}건 미도달, "
                  f"total 합 {meta.get('union_upper_bound')}건)")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="scienceon", description="ScienceON 문헌 메타데이터 수집기")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="연결/토큰 상태 점검").set_defaults(func=cmd_status)

    s = sub.add_parser("search", help="검색 (여러 --query = 서버측 OR 합집합)")
    s.add_argument("--query", required=True, action="append", help="검색어(여러 번 지정 가능)")
    s.add_argument("--target", default="ARTI")
    s.add_argument("--field", default="BI")
    s.add_argument("--year", help="발행연도/범위 예: 2020 또는 2015~2024")
    s.add_argument("--rows", type=int, default=20)
    s.add_argument("--contains", action="append", help="제목/초록/키워드 포함 필터(여러 번 가능)")
    s.set_defaults(func=cmd_search)

    d = sub.add_parser("detail", help="상세보기(CN)")
    d.add_argument("--target", default="ARTI")
    d.add_argument("--cn", required=True)
    d.set_defaults(func=cmd_detail)

    c = sub.add_parser("collect", help="설정 기반 대량 수집 (terms/contains 지원)")
    c.add_argument("--config", required=True)
    c.set_defaults(func=cmd_collect)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
