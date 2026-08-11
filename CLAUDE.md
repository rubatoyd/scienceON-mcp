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

### 2026-08-11 — 기동 불능 2건 수정 (자매 프로젝트 kci-openapi-mcp 점검 중 발견)
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
