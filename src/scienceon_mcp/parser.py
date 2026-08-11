"""ScienceON 응답(XML) → 정규화 레코드.

실제 태그/metaCode 명은 첫 라이브 응답으로 확정한다(docs §7). 그 전까지는
원본 태그/속성을 그대로 수집하고, FIELD_CANDIDATES 로 정규화 필드에 매핑한다.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from .models import Record

# 정규화 필드 → 원본 metaCode 후보(우선순위). ARTI 는 라이브 검증 완료.
# REPORT 등 타 target 은 다른 metaCode 를 쓸 수 있어 후보를 함께 둔다(raw 에 원본 보존).
FIELD_CANDIDATES: dict[str, list[str]] = {
    "control_no": ["CN", "ArticleId", "cn", "controlNo"],
    "title": ["Title", "TI", "title", "reportTitle", "titleName"],
    "authors": ["Author", "AU", "author", "Inventor", "Applicant"],
    "pub_year": ["Pubyear", "PubYear", "PY", "Pubdate", "year", "PublishYear"],
    "publisher": ["Publisher", "PB", "Organization", "publisherName"],
    "journal": ["JournalName", "JN", "journal", "pubName"],
    "abstract": ["Abstract", "AB", "abstract"],
    "keywords": ["Keyword", "KW", "keyword"],
    "doi": ["DOI", "doi"],
    "url": ["ContentURL", "FulltextURL", "MobileURL", "Link", "url"],
}

_TOTAL_TAGS = {"totalcount", "totalCount", "recordcount", "recordCount", "count", "TotalCount"}


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1]  # 네임스페이스 제거


def _find_total(root: ET.Element) -> int:
    for el in root.iter():
        if _localname(el.tag) in _TOTAL_TAGS and (el.text or "").strip().isdigit():
            return int(el.text.strip())
    return 0


def _iter_record_elems(root: ET.Element):
    # 결과 레코드는 recordList/record 에만 존재. parameterData 등 다른 곳의 item 을
    # 레코드로 오인하지 않도록 경로를 한정한다(0건 응답에서 빈 레코드 생성 방지).
    recs = root.findall(".//recordList/record")
    if recs:
        return recs
    return [el for el in root.iter() if _localname(el.tag).lower() == "record"]


def parse_response(xml_text: str) -> tuple[int, list[dict[str, Any]]]:
    """XML 문자열 → (총건수, [원본 레코드 dict])."""
    root = ET.fromstring(xml_text)
    total = _find_total(root)
    records: list[dict[str, Any]] = []
    for rec in _iter_record_elems(root):
        d: dict[str, Any] = {}
        for el in rec.iter():
            if el is rec:
                continue
            key = el.attrib.get("metaCode") or _localname(el.tag)
            val = (el.text or "").strip()
            if not val:
                continue
            if key in d:
                d[key] = d[key] + [val] if isinstance(d[key], list) else [d[key], val]
            else:
                d[key] = val
        if d:
            records.append(d)
    return total, records


def normalize(raw: dict[str, Any], source: str) -> Record:
    def pick(field: str):
        for k in FIELD_CANDIDATES[field]:
            if k in raw:
                return raw[k]
        return None

    def as_list(v) -> list[str]:
        if v is None:
            return []
        return v if isinstance(v, list) else [str(v)]

    def as_str(v) -> str:
        if v is None:
            return ""
        return "; ".join(v) if isinstance(v, list) else str(v)

    return Record(
        source=source,
        control_no=as_str(pick("control_no")),
        title=as_str(pick("title")),
        authors=as_list(pick("authors")),
        pub_year=as_str(pick("pub_year")),
        publisher=as_str(pick("publisher")),
        journal=as_str(pick("journal")),
        abstract=as_str(pick("abstract")),
        keywords=as_list(pick("keywords")),
        doi=as_str(pick("doi")),
        url=as_str(pick("url")),
        raw=raw,
    )
