# scienceon-mcp 기능 구현 계획 (ROADMAP)

> 공식 매뉴얼 v2.4 + 공식 샘플(Python/Java/C#/JS/PHP) + 라이브 실측을 근거로 한
> 단계별 구현 계획. 우선순위 P0(핵심)~P3(확장), 규모 S/M/L.

## 0. 현재 상태 (구현·검증 완료)
- 토큰: AES-256-CBC(고정 IV)·refresh·홈 캐시. 검색/상세/페이징·429 백오프.
- 타깃: **ARTI·REPORT 라이브 검증**(출력 metaCode 동일 → 동일 파서로 동작).
- 검색: 다중쿼리 합집합 · 와일드카드 `*` · `|` OR · contains(전체필드·대소문자무시) ·
  lang(언어) · 연도범위(`~`) · 그룹별 max.
- 인터페이스: MCP 4도구(status/search/detail/export) + CLI(status/search/detail/collect, 다중그룹 config).
- 출력: xlsx/csv/json/sqlite. 공개 저장소(MIT).

---

## P0 — 수집 품질·재현성 (정밀화)

### P0.1 타깃별 필드맵 정식화 (parser) — M
- 현재 `FIELD_CANDIDATES` 는 ARTI 후보 공유. **target별 검색필드/출력필드 맵을 분리**.
- 확정 규격(매뉴얼):
  - **REPORT**: search BI/TI/AU/PB/KW/AB/PY/CN · out CN/Publisher/Pubdate/Pubyear/Title/Abstract/Author/PageInfo/FulltextURL/ContentURL/Keyword · DBCode(TRKO 국내연구보고서·KOSEN·RESEAT·KGPS·ICON·KMR)
  - **ATT(동향)**: search +SU(주제분류)/CC(국가과기표준분류) · out +RegDate/Subject/SubjectCode
  - **PATENT**: search TI(발명명칭)/PA(출원인)/AN/AD/RN/RD/IPN/AB/IN(발명자)/IC(IPC)/… · 별도 출력맵 필요
  - RESEARCHER/ORGAN/AUTHOR: 인물·기관 메타(이름/소속/식별자)
- 효과: REPORT/ATT 도 제목·저자·초록·키워드 정규화 정확. 검색필드 검증(E4007 예방).

### P0.2 검색필드·정렬 노출 — S
- `field` 화이트리스트를 target별로 검증, `sort_field`/`sortBy`(TREND) 파라미터를 search/export·MCP에 노출(기본 pubyear desc).

### P0.3 수집 manifest — S
- `output/<project>/manifest.json`: 쿼리/그룹·연도·target·총건수·필드결측·수집일시·도구버전 기록 → 재현성·인용 근거.

### P0.4 증분 수집(UPSERT) 옵션 — M
- sqlite 를 PK=CN 의 `INSERT OR REPLACE` 모드로 전환(옵션). 다회차/주기적 수집 누적·갱신.
  현재 스냅샷(DROP) 기본 유지, `--append`/config `mode: upsert` 추가.

---

## P1 — 동향 워크플로·다중그룹 (사용성)

### P1.1 MCP `scienceON_collect_groups` 도구 — M ✅ **완료 (v0.3.0)**
- 다중 그룹(field/terms/contains/lang/max)을 **MCP 한 번에** → config 없이 대화형 동향수집.
  `save=false` 로 저장 없이 미리보기 가능(응답은 앞 100건만).

### P1.2 동향 산출 헬퍼 — M
- 수집 코퍼스에서 **연도×건수 피벗 · 키워드 빈도/신흥어 · 게재지 분포** 를 CSV/표로.
  CLI `scienceon trends --input <json>` / MCP `scienceON_trends`. (정식 토픽모델은 R STM 핸드오프)

### P1.3 REPORT/ATT 통합 동향 프리셋 — S
- ARTI+REPORT(+ATT) 다중 target 수집을 하나의 config 로(현재 target 단일). `targets: [ARTI, REPORT]`.

---

## P2 — API 표면 확대 (커버리지)

### P2.1 신규 타깃 — M
- PATENT(특허), AUTHOR(저자전거), SCENT(과학향기), TREND, SNEWS(과기뉴스, RD 날짜),
  KACADEMY(교육정보), FUNCTION/SERVICE(지식인프라), APPLICANT(출원인), DDC(주제분류·`subject` 파라미터).
- 각 타깃 검색필드·특수 파라미터 매핑(샘플 확인됨).

### P2.2 링크리졸버 RESOLVER — M
- `atitle`/`id`(CN·DOI)/`issn`+`volume`+`issue`+`date`+`spage` 로 **원문 링크 해석**.
  도구 `scienceON_resolve` → 수집 레코드의 원문 접근성 보강.

### P2.3 인용·참고·관련 문헌 — L
- 상세(browse) 응답의 `SimilarPubyear`(관련)/`CitingPubyear`(인용)/`CitedPubyear`(참고) 활용 +
  다중 API(CallApiInfo) 체이닝 → **인용 네트워크** 추출 `scienceON_citations`.

### P2.4 권호 TOC(VOLUME)·콘텐츠 추천(RECOMMEND) — S
- VOLUME: `cn`+`volno` 목차. RECOMMEND: `recomType`+`cn`+`uid` 관련문헌.

---

## P3 — 견고성·배포 (공개 품질)

### P3.1 자동 테스트(pytest) — M ✅ **완료** (26종)
- 파서(저장된 XML 픽스처)·토큰 암호화(AES 벡터)·쿼리 빌더·exporters 단위테스트. 라이브는 mock.

### P3.2 CI + 배포 — M ✅ **대부분 완료** (CI + 태그 릴리스 + MCP 레지스트리 발행. PyPI 는 미배포)
- GitHub Actions(ruff lint + pytest), 버전 태그·릴리스, **PyPI 배포**(`uvx scienceon-mcp`로 설치 없이 실행).

### P3.3 운영 설정·로깅 — S
- throttle/concurrency/타임아웃 config, 구조화 로깅(자격증명 마스킹), 429 누적 경고.

### P3.4 문서 — S
- README 영문 보강, 타깃별 필드 표(docs), MCP 사용 예시(동향수집 시나리오).

---

## 권장 실행 순서
1. **P0.1 + P0.3**(타깃 필드맵·manifest) → 수집 정확·재현성 확보
2. **P1.1 + P1.3**(MCP 다중그룹·다중 target) → 대화형 동향수집 완성
3. **P2.1**(신규 타깃) → 커버리지
4. **P3.1 + P3.2**(테스트·CI·PyPI) → 공개 신뢰도·배포
5. P2.2/P2.3(리졸버·인용) → 심화 분석 지원

> 설계 원칙: 공용 코어(client/parser) 확장이 MCP·CLI에 동시 반영되도록 유지. 모든 신규
> 타깃·파라미터는 **라이브 소량 검증 후** 확정(추정 금지). 대량 호출 전 throttle·한도 준수.
