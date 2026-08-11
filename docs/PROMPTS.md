# Claude 구동용 프롬프트 템플릿

연구 초반 자료수집 단계에서 Claude에게 ScienceON 수집기를 시키는 프롬프트 모음.
`[ ]` 부분만 바꿔 쓰면 된다.

---

## A. MCP 모드 (Claude가 도구 직접 호출 — 권장)

> MCP 서버가 Claude Desktop/Code에 연결돼 있어야 함(README 참고).

### A-1. 연결 확인
```
scienceON_status 도구로 연결 상태를 확인해줘.
```

### A-2. 탐색 검색 → 미리보기
```
scienceON_search 로 ScienceON에서 "[검색어]" 를 [ARTI/REPORT] 대상,
[BI 전체/TI 제목/AB 초록] 필드, [2015]~[2024]년으로 [20]건 검색해서
제목·저자·연도·초록요약 표로 보여줘.
```

### A-3. 적합성 판단 후 대량 수집·저장
```
방금 결과가 연구주제 "[주제]"에 적합해 보이면, scienceON_export 로
같은 조건에서 [300]건을 [xlsx, csv, json, sqlite]로 output/[프로젝트명]에 저장해줘.
저장 후 건수와 파일 경로를 알려줘.
```

### A-4. 상세/초록 보강
```
scienceON_detail 로 CN [제어번호]의 초록 전문과 서지정보를 가져와줘.
```

---

## B. CLI 모드 (Claude가 설정 작성 + 터미널 실행)

```
ScienceON 수집기로 아래 조건의 자료를 수집해줘.
- 주제/검색어: [검색어]
- 대상: [ARTI 논문 / REPORT 보고서]
- 필드: [BI 전체 / TI 제목 / AB 초록]
- 연도: [2015~2024]
- 목표 건수: [300]
- 출력: [xlsx, csv, json, sqlite]

순서:
1) config/[프로젝트명].yaml 를 config/search.example.yaml 형식으로 작성
2) `uv run scienceon collect --config config/[프로젝트명].yaml` 실행
3) 저장된 파일 경로와 건수, 핵심필드 결측/중복 간단 점검 결과 보고
```

---

## C. 신규 프로젝트 부트스트랩

```
새 연구 프로젝트 "[프로젝트명]"의 자료수집 단계를 시작한다.
docs/COLLECTION_WORKFLOW.md 절차를 따라:
1) 연구질문 "[질문]" 에서 검색어 후보(동의어·영문 포함)를 제안
2) 시범 10건 검색으로 적합성 확인
3) 합의되면 본 수집(목표 [N]건)하고 4종 포맷으로 저장
4) manifest(쿼리·일시·건수) 기록
각 단계마다 결과를 보여주고 다음 단계 진행 여부를 물어봐.
```

---

## 참고: 검색필드 코드
`BI`(전체) · `TI`(제목) · `AB`(초록) · `AU`(저자) · `KW`(키워드) · `PB`(발행기관) · `PY`(발행연도)
대상(target): `ARTI` 논문 · `REPORT` 보고서 · `ATT` 동향 · `RESEARCHER` 연구자 · `ORGAN` 연구기관
