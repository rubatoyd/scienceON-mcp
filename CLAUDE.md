# scienceon-mcp — 프로젝트 지침

> KISTI ScienceON OpenAPI 문헌 검색·메타데이터 수집기. 누구나 자기 API 키로 쓰는
> **공개 MCP 서버 + CLI**. API 호출 규격은 [docs/SCIENCEON_API_GUIDE.md](docs/SCIENCEON_API_GUIDE.md) 참조.

## 1. 목표
연구 초반 **자료수집 단계**에서 반복 재사용하는 도구. 논문·보고서 등 서지 메타데이터를
검색·수집해 후속 텍스트마이닝 입력 데이터를 안정적으로 생산한다.

## 2. 확정 결정사항
| 항목 | 결정 |
|------|------|
| 언어/런타임 | Python 3.10+ (개발 venv는 3.12) |
| 패키지 관리 | **uv** (pyproject + uv.lock). venv는 **클라우드 폴더 밖** `C:\Users\user\.venvs\scienceon-mcp` (`UV_PROJECT_ENVIRONMENT`, `.claude/settings.local.json` 에 지정) |
| 의존성 | mcp(FastMCP), requests, pycryptodome, openpyxl, python-dotenv, pyyaml |
| 인터페이스 | 공용 코어 + **MCP 서버(server.py)** + **CLI(cli.py)** |
| 수집 대상 | ARTI(논문)·REPORT(보고서) 우선, ATT/RESEARCHER/ORGAN 확장 가능 |
| 출력 | xlsx · csv · json · sqlite |
| 공개 | MIT. `.env`·`reference/`·`output/`·토큰캐시는 gitignore |

## 3. 구조
```
src/scienceon_mcp/
  config.py     # .env 로딩, 엔드포인트
  auth.py       # AES256 토큰 발급/캐시/갱신 (라이브 검증 완료)
  client.py     # 검색/상세/페이징/재시도/에러
  parser.py     # XML(.//record/item[@metaCode]) → 정규화
  models.py     # Record 스키마
  exporters.py  # xlsx/csv/json/sqlite
  server.py     # MCP 도구: scienceON_search/detail/export/status
  cli.py        # status/search/detail/collect
docs/           # API 가이드, 워크플로, 프롬프트
config/         # 검색 설정 템플릿
reference/      # KISTI 매뉴얼·공식 샘플(gitignore, 비공개)
```

## 4. 자격증명 (.env 또는 사용자 환경변수)
- 변수: `SCIENCEON_AUTH_KEY`(32자), `SCIENCEON_CLIENT_ID`, `SCIENCEON_MAC_ADDRESS`, `SCIENCEON_ACCOUNT_ID`
- 구독 티켓(계정별 상이): 예) ARTI·REPORT·ATT·RESEARCHER·ORGAN
- API Gateway **IP관리**에 호출 PC 공인 IP 등록·활성화 필수(미등록 시 E4006). MAC = 신청 시 등록한 대표 MAC.
- ⚠️ 인증키는 코드/로그/커밋 금지 — `.env`(gitignore) 또는 OS 사용자 환경변수로만.

## 5. 핵심 기술사실 (라이브 검증)
- **토큰 발급**: `tokenrequest.do?client_id=&accounts=` — accounts = urlsafe_b64( AES-256-CBC(
  key=인증키 UTF-8 32B, **IV=`jvHJ1EFA0IXBrxxz`(고정)**, PKCS7, 평문 `{"datetime":"YYYYMMDDHHMMSS","mac_address":"..."}`)) → URL 인코딩. (그 고정 IV는 공식 샘플로만 확인 가능했음)
- **데이터 호출**: `openapicall.do?...&action=search|browse&target=ARTI&searchQuery={"BI":"검색어"}&curPage=&rowCount=`
- **응답 XML**: 레코드 `.//record`, 필드 `<item metaCode="...">`. 총건수 `TotalCount`.
  ARTI metaCode: CN/Title/Author/Pubyear/Publisher/JournalName/Abstract/Keyword/DOI/ContentURL.
- Access Token 2시간, Refresh Token 2주. 429(Too Many Requests) 주의 → throttle·백오프 필수.

## 6. 개발 원칙
- 자격증명은 `.env`/MCP env 블록으로만. 로그·예외에 노출 금지.
- 정중한 호출: throttle(기본 0.5s), 지수 백오프, 페이지네이션 안전장치(새 레코드 0이면 종료).
- 원본 XML 필드는 `raw`로 보존. 커밋 메시지 한국어, Claude 서명 금지.
- 라이브 검증 우선(추정 금지) — 대량 호출 전 소량 시범.

## 7. 상태
- ✅ 공개: github.com/rubatoyd/scienceON-mcp (MIT, Release v0.1.0 + `.mcpb` 원클릭)
- ✅ 라이브 검증: 토큰·검색·다중쿼리·와일드카드(`*`)·contains/lang 필터·다중그룹·다중 target(ARTI+REPORT)
- ✅ 배포 3종: uvx-from-git / `.mcpb`(Claude Desktop) / 로컬(개발). 자격증명은 사용자 환경변수+.env.
- ✅ pytest 11종 + GitHub Actions CI
- ⏳ (선택) `.mcpb` 데스크톱 실설치 검증, ROADMAP(docs/ROADMAP.md) P0~P3

### 2026-08-11 (5) — 적대적 검증 반영 (kci 에서 발견된 결함 3종 이식)
kci 를 실제 반복 호출로 깨보다 나온 결함이 이쪽에도 그대로 있었다. **네 번째 전파 사례**다.
- 🔴 **`truncated` 오탐 분리** — `fetched < total` 하나로 판정해 페이징을 끝까지 돌았는데도 True 가 떴다
  (실측: TI '경계선지능' total 263 / 실회수 262, 중복제거 0건). API 의 total 은 실제 서빙량보다 클 수
  있고, 그때 "max_records 를 올리라"는 경고는 틀린 처방이다.
  → `truncated`(우리 상한)와 `total_mismatch`(API total 불일치)를 분리, `notice` 로 다른 조언을 준다.
- 🔴 **`rows<=0` 이 total 을 감춤** — `rowCount=0` 이면 total 까지 0 으로 와 "결과 없음"으로 오보된다.
  → 요청 크기 하한 1 로 클램프(반환 건수는 요청대로 0).
- 🔴 **다중 페이지 질의 결과 불안정 보정** — kci 실측으로 동일 조건 3회에 204/204/205, 합집합 205·
  교집합 203 을 확인했다. `retry_incomplete=1`(기본)로 total 미달 시 한 번 더 훑어 합집합을 취한다.
  `meta.sweeps` 로 보정 여부가 드러난다. 끄려면 `retry_incomplete=0`.
- 테스트 34 → **37**.

### 2026-08-11 (4) — 전송 선택 추가 (Claude 전용 탈피)
- `mcp.run()` 이 인자 없이 호출돼 **stdio 전용**이었다. `main()` 에 `--transport
  stdio|sse|streamable-http` + `--host`/`--port` 를 붙였다(환경변수 `SCIENCEON_MCP_TRANSPORT`/
  `_HOST`/`_PORT` 도 지원). 소스에 Claude 결합 코드는 원래 없었으므로 이로써 원격 호스팅·비 stdio
  클라이언트까지 열린다. kci 와 동일 처방.
- ⚠️ **기본값은 stdio 로 못박아 둘 것** — 기존 등록은 인자 없이 서버를 띄우므로 기본이 바뀌면
  모든 사용자의 MCP 가 한 번에 죽는다. 회귀 테스트로 고정했다.
- ⚠️ **HTTP 전송에는 인증이 없다.** 기본 바인드는 루프백. 외부 노출은 자격증명을 공개하는 것과 같아
  기동 시 경고를 찍는다. 미지의 CLI 인자·비숫자 포트 환경변수는 서버를 죽이지 않고 무시한다.
- 검증: stdio 회귀 + `streamable-http` 실기동(HTTP 200) + 테스트 26 → **34**.

### 2026-08-11 (3) — v0.3.0: 예외 누수 차단 · annotations · 다중그룹 MCP 도구
kci 와의 **비대칭 해소**가 주제다. 이번 세션에서 "한쪽에서 고친 결함이 다른 쪽에 남아 있는" 패턴이
세 번째 반복됐다(mcp 상한 → 조용한 절단 → 예외 누수).

- 🔴 **예외 누수 차단** — 도구들이 `ScienceONError` 만 잡아, 자격증명 누락이 `RuntimeError` 로
  **그대로 새어나가는 것을 실측 확인**했다(네트워크 타임아웃·XML 파싱 오류도 동일). kci 의 `_safe`
  데코레이터를 이식해 전 도구가 항상 dict 를 반환한다. kci 의 `SUBMISSION.md` 는 "예외 누수 없음"을
  디렉터리 심사 기준으로 명시하는데 이쪽엔 그 처방이 없었다.
- 🟡 **MCP annotations 선언** — `readOnlyHint`/`openWorldHint`/`destructiveHint`. 조회 3종은 읽기,
  파일을 만드는 `scienceON_export`·`scienceON_collect_groups` 는 쓰기(비파괴)로 표시. kci 와 동일.
- 🟢 **`scienceON_collect_groups` 신설 (ROADMAP P1.1)** — 클라이언트·CLI 는 다중그룹 수집을
  지원했으나 **MCP 에는 노출되지 않아** Claude 에서 쓸 수 없었다. 그룹별로 다른 field·contains·lang·max
  를 걸어 한 코퍼스로 합친다(config 파일 불필요). `save=false` 면 저장 없이 미리보기(응답 앞 100건만).
- 테스트 16 → **26**(`tests/test_server.py` 신설 — 예외 누수 회귀·annotations·그룹 수집).

### 2026-08-11 (2) — v0.2.0: 조용한 절단 제거 · 표기 통일 · truststore 정식화 · 릴리스 파이프라인
- 🟢 **릴리스 파이프라인 신설(kci 이식)** — 기존에는 CI 가 테스트만 돌리고 릴리스·레지스트리
  경로가 아예 없었다. `.github/workflows/publish-mcp.yml`(태그 푸시 → OS별 PyInstaller 바이너리
  빌드 → 경량 `.mcpb` 팩 → sha256 주입 → GitHub Release → 레지스트리 OIDC 발행),
  `packaging/binary/{entry.py,manifest.json}`, `server.json`, README `mcp-name` 주석 추가.
  두 manifest 는 `mcpb validate` 공식 스키마 검증 통과.
  ⚠️ 레지스트리 이름은 **소문자** `io.github.rubatoyd/scienceon-mcp` — 저장소명(`scienceON-mcp`)과
  다르다. 배포명(`scienceon-mcp`)에 맞췄고 레지스트리 이름 대소문자 취급이 불확실하기 때문이다.
  ⚠️ pycryptodome 은 import 명이 `Crypto` 라 PyInstaller `--collect-all Crypto` 가 필요하다(kci 엔 없는 항목).
- ✅ **v0.2.0 발행 완료 (2026-08-11)** — 이 저장소의 **첫 레지스트리 발행**. 신설 파이프라인이 첫 실행에
  전 단계 통과했다(win/macos/linux 바이너리 빌드 → 릴리스 → OIDC 발행).
  레지스트리 실조회: `io.github.rubatoyd/scienceon-mcp v0.2.0 status:active`.
  릴리스 자산 4종 — 경량 `scienceon-mcp.mcpb`(2KB) + 자체완결 linux 42MB·win 27MB·macos 25MB.
  ✅ **자체완결 바이너리 런타임 검증 완료** — 릴리스 자산을 내려받아 **클린 환경**
     (`env -i`, PATH=system32 만, Python·uv 없음)에서 stdio 핸드셰이크 성공(exit 0, 도구 4종).
     `Crypto` 는 `auth.py` 모듈 최상단 import 라 기동 성공만으로 번들 확인된다.
     `truststore` 는 지연 import 라 별도 확인 필요 → 자격증명 없이 `scienceON_status` 를 호출해
     `ScienceONClient.__init__` → `use_os_trust()` 경로를 태웠고 stderr 에 주입 실패 경고가
     없어 정상 번들 확인. 자격증명 누락은 크래시 없이 구조화된 오류로 반환됐다.
- 🟡 **truststore 를 정식 의존성으로 이관** — 이전에는 MCP 등록 명령줄
  (`uv run --with truststore … inject_into_ssl()`)에만 걸려 있어 **`.mcpb` 번들 경로에는 아예
  들어가지 않았다.** 교육망·사내망 SSL 인터셉션 환경에서 `.mcpb` 설치본이 인증서 오류로 실패한다.
  `config.use_os_trust()` 신설(`SCIENCEON_OS_TRUST=0` 으로 비활성) + `ScienceONClient.__init__`·
  `TokenManager.__init__` 에서 호출 → 모든 기동 경로를 덮는다. 검증을 끄지 않고 OS 저장소를 쓴다.
  `.mcpb` manifest 에 `os_trust` user_config 추가. kci 와 동일 구조.
- 🔴 **조용한 절단 제거(최우선)** — `client.search()` 가 `TotalCount` 를 파싱해 페이지네이션 종료
  조건에만 쓰고 **버렸다**. `scienceON_export` 는 `{count, files}` 만 반환해 `max_records`(기본 500)
  상한에 걸려도 알 방법이 없었다. **수집량이 max_records 와 정확히 일치하면 거의 항상 절단이다.**
  `search_meta`/`search_terms_meta`/`search_groups_meta` 신설 → `total`·`fetched`·`truncated`·
  `axes`·`union_upper_bound` 반환. 도구 응답과 `cli collect` 출력에 경고를 노출한다.
  기존 `search`/`search_terms`/`search_groups` 는 얇은 래퍼로 남겨 호출부 호환 유지.
  회귀 테스트 5건 추가(11 → 16 통과). kci v0.1.3 과 동일 처방.
- **표기 통일 `ScienceOn` → `ScienceON`** — 저장소에 공식 표기가 하나도 없었다. 저장소도
  `rubatoyd/scienceON-mcp` 로 rename. GitHub 는 owner/repo 조회가 **대소문자 무시**라 구 URL 이
  계속 해석되므로 계정명 변경 때와 달리 기동 장애는 없다.
  MCP 서버 키·도구명도 `scienceON`/`scienceON_*` 로 변경(**호출부 호환 깨짐** → v0.2.0).
  보존: 모듈 `scienceon_mcp`(PEP 8), 배포·스크립트명 `scienceon-mcp`, 환경변수 `SCIENCEON_*`.

### 2026-08-11 (1) — 기동 불능 2건 수정 (자매 프로젝트 kci-openapi-mcp 점검 중 발견)
- 🔴 **`mcp` SDK 상한 누락으로 서버가 아예 기동 못 하고 있었다** — `mcp>=1.2.0`(상한 없음)이
  **mcp 2.0** 으로 해석되는데 2.0 은 `mcp.server.fastmcp` 를 제거했다(→ `mcp.server.MCPServer` 체계).
  `uv run --with "scienceon-mcp @ git+…"` 경로는 **uv.lock 을 보지 않고 매번 새로 해석**하므로
  lock 에 1.28.0 이 박혀 있어도 소용없었다. 실제 오류: `ModuleNotFoundError: No module named
  'mcp.server.fastmcp'`. `pyproject.toml` 을 `mcp>=1.2.0,<2` 로 고정(kci 와 동일 처방). 로컬 소스로
  `initialize` 응답·pytest 11종 통과 확인. ⚠️ **원격 HEAD 를 받아오는 MCP 등록분은 push 해야 반영된다.**
- ⚠️ **GitHub 계정명 변경 `rubato103` → `rubatoyd`** — `git remote`·`pyproject.toml`·`README`·
  `mcpb/manifest.json`·`mcpb/README` 갱신. 본 저장소는 `server.json` 이 없어 **레지스트리 미발행**이므로
  네임스페이스 이관 이슈는 없다(kci 는 해당됨).
- ⚠️ **프로젝트 내 `.venv/` 파손** — `pyvenv.cfg` 의 home 이 **다른 사용자 프로필** `C:\Users\rubat\…`
  를 가리켜 `uv lock`·`uv run` 이 exit 103 으로 실패한다(OneDrive 로 유입된 타 PC 산출물, kci 도 동일 증상).
  우회: `UV_PROJECT_ENVIRONMENT=C:/Users/user/.venvs/scienceon-mcp` (이번에 생성, 클라우드 폴더 밖).
- ℹ️ `uv lock` 이 lockfile `revision 2 → 3` 을 올린다(uv 0.10 형식). 내용 변경은 mcp specifier 한 줄뿐.
- ⚠️ **액션 버전 표기: 이동 태그 유무를 구분할 것 (2026-08-11 CI 실패로 학습)** — Node.js 20
  deprecation 해소를 위한 상향 중, `astral-sh/setup-uv` 는 **v7 이후 이동 메이저 태그를 내지 않아**
  (`v5`·`v6`·`v7` 존재, `v8`·`v9` 없음) `@v9` 가 `Unable to resolve action … unable to find
  version v9` 로 즉시 실패했다 → `@v9.0.0` 정확 고정. `actions/*` 는 이동 태그를 유지한다.
  상향 전 `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` 로 실존 확인할 것. kci 와 동일 기록.
- ℹ️ **기동 시 stderr 경고는 무해하다(오진 주의)** — `pydantic_settings … IncompleteFieldDefinitionWarning:
  Field 'lifespan' has an incomplete definition`. pydantic-settings 2.14 에서 새로 생긴 경고이고 대상은
  mcp SDK 의 FastMCP `Settings` 모델이다(우리 코드 아님). `pydantic-settings<2.14` 면 사라지는 것을
  실측했으나 **핀하지 않는다** — 직접 쓰지 않는 전이 의존성을 묶으면 상류 수정 후에도 부채로 남는다.
  MCP 로그에서 이 두 줄은 무시하고 실제 오류만 볼 것. kci 와 동일 증상.
