# 자료 수집 워크플로 (반복 운영 SOP)

> 새 연구 프로젝트의 **초반 자료 수집 단계**마다 이 절차를 그대로 반복한다.
> 목표: 동일한 방식으로 누구나/언제나 재현 가능한 문헌 메타데이터 세트를 산출.

## 0. 전제 (최초 1회만)
- `.env` 자격증명 설정 완료, 구독 티켓 확인(ARTI·REPORT·ATT·RESEARCHER·ORGAN).
- 토큰 발급 검증 완료(`scienceON_status` 또는 `cli status`).

## 1. 주제·범위 정의
- 연구 질문 → 검색어(동의어·영문 포함), 대상 `target`(ARTI/REPORT), 연도 범위, 목표 건수.
- 산출: 한 줄 수집 명세 (예: "ARTI, TI/AB='학습부진 대학생', 2015–2024, ~800건").

## 2. 검색 설정 작성
- `config/search.example.yaml` → `config/<프로젝트명>.yaml` 로 복제 후 수정.
- 검색 필드코드는 [SCIENCEON_API_GUIDE.md](SCIENCEON_API_GUIDE.md) §4 표를 따른다.

## 3. 시범 검색 (소량)
- `rows=10, max_records=10` 으로 1회 호출 → 결과 적합성·필드 스키마 확인.
- 첫 응답 XML 원본을 저장해 정규화 매핑(가이드 §7)을 확정/갱신.

## 4. 본 수집
- 페이징: `recordCount`로 총건수 파악 → `curPage` 순회.
- **throttle(0.3~1초)·동시성 1~2** 준수. 5xx/네트워크는 지수 백오프 재시도.
- 필요 시 CN으로 상세(초록) 보강(2단계).

## 5. 정규화·중복 제거·저장
- 표준 스키마로 매핑, 제어번호(CN) 기준 중복 제거.
- 출력: `output/<프로젝트명>/` 아래 **xlsx·csv·json·sqlite** (config에서 선택).
- 원본 XML은 `raw`로 함께 보존.

## 6. 검수
- 건수(요청 대비 수집), 핵심 필드 결측률(title/year/abstract), 중복 잔존 0 확인.
- 비정상(0건/과대건수)이면 쿼리·필드코드 재점검.

## 7. 수집 기록(manifest)
- `output/<프로젝트명>/manifest.json` 에 쿼리·일시·총건수·포맷·도구버전 기록 → 재현성.

---

## ✅ 반복 사용 체크리스트
- [ ] 주제→수집 명세 1줄 정리
- [ ] config 복제·수정 (target/필드/연도/건수)
- [ ] 시범 10건으로 스키마·적합성 확인
- [ ] 본 수집 (throttle·재시도·중복제거)
- [ ] 4종 출력 + raw 보존
- [ ] 검수(건수·결측·중복) 통과
- [ ] manifest 기록

## 운영 모드별 실행 (자세히는 [README](../README.md))
- **MCP(대화형 탐색)**: Claude에게 도구 호출 지시 → 미리보기 후 export.
- **CLI(배치·재현)**: `python -m scienceon.cli --config config/<프로젝트>.yaml`.
- 프롬프트 템플릿: [PROMPTS.md](PROMPTS.md).
