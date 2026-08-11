# scienceon-mcp

[![CI](https://github.com/rubatoyd/scienceon-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rubatoyd/scienceon-mcp/actions/workflows/ci.yml)

KISTI **ScienceOn OpenAPI** 문헌 검색·메타데이터 수집기 — **MCP 서버 + CLI**.
자기 ScienceOn API 키만 발급받으면 누구나 Claude(또는 CLI)에서 국내외 논문·보고서
서지 메타데이터를 검색·수집할 수 있습니다.

> An MCP server + CLI for KISTI ScienceOn OpenAPI. Bring your own API key and let
> Claude search & collect academic literature metadata in any project.

## 무엇을 할 수 있나

- 🔎 **검색**: 논문(ARTI)·보고서(REPORT) 등 서지 메타데이터 검색
- 📄 **상세**: 제어번호(CN)로 초록·서지 전체 조회
- 💾 **수집**: 결과를 **xlsx / csv / json / sqlite** 로 저장
- 🤖 **두 가지 사용법**: Claude에서 도구 호출(MCP) · 터미널 배치(CLI) — 같은 코어 공유

지원 티켓: `ARTI` 논문 · `REPORT` 보고서 · `ATT` 동향 · `RESEARCHER` 연구자 · `ORGAN` 연구기관
(계정 구독 범위에 따름)

## 요구사항

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (패키지 관리)
- ScienceOn API 자격증명 (아래 발급 방법)

## 1) API 키 발급

1. [ScienceOn](https://scienceon.kisti.re.kr) 회원가입·로그인
2. **API Gateway → 인증키 발급 신청** → 승인 후 `인증키`·`Client ID` 발급
3. **인증키관리**에서 신청 **MAC 주소** 등록, **IP관리**에서 호출 PC의 공인 IP 등록
4. 사용할 **서비스 콘텐츠(티켓)** 체크 (논문/보고서 등)

## 2) 설치

**전제: [uv](https://docs.astral.sh/uv/) 설치** (Windows: `winget install astral-sh.uv`).

### 방법 0 — 원클릭 (.mcpb, Claude Desktop)
[Releases](https://github.com/rubatoyd/scienceon-mcp/releases) 에서 **`scienceon-mcp.mcpb`** 다운로드 →
Claude Desktop 에 더블클릭/드래그 → **설치 창에서 인증키·Client ID·MAC 입력** → 완료.

### 방법 A — uvx (설정 직접, 설치 불필요)
clone·venv 없이 아래 4)의 `uvx` 설정이 GitHub 버전을 자동 빌드·실행합니다.

> 코드를 수정·기여하려면(개발용) clone 후 `uv sync` — 클라우드 동기화 폴더(OneDrive 등)면
> venv를 폴더 밖에: `export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/scienceon-mcp"` 후 `uv sync`.

## 3) 자격증명
자기 ScienceOn 키(발급: 위 1)를 **MCP 설정 `env` 블록**(아래) 또는 `.env`(`.env.example` 복사)로 전달.
코드/커밋/로그엔 넣지 마세요.

## 4) Claude에 MCP 연결 (설치 불필요 · uvx)

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scienceon": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/rubatoyd/scienceon-mcp", "scienceon-mcp"],
      "env": {
        "SCIENCEON_AUTH_KEY": "발급_32자리_인증키",
        "SCIENCEON_CLIENT_ID": "발급_client_id",
        "SCIENCEON_MAC_ADDRESS": "AA-BB-CC-DD-EE-FF"
      }
    }
  }
}
```

**Claude Code**:

```bash
claude mcp add scienceon -- uvx --from "git+https://github.com/rubatoyd/scienceon-mcp" scienceon-mcp
```

> 첫 실행 시 빌드(수 초), 이후 캐시. 최신 반영은 `uvx --refresh ...`.
> 개발용 로컬 설치를 쓰면 command 를 venv 파이썬으로:
> `…\.venvs\scienceon-mcp\Scripts\python.exe -m scienceon_mcp.server`

연결되면 Claude에서 `scienceon_search`, `scienceon_detail`, `scienceon_export`,
`scienceon_status` 도구를 사용할 수 있습니다.

## 5) CLI 사용 (배치·재현)

```bash
uv run scienceon status                                   # 토큰/연결 확인
uv run scienceon search --target ARTI --query "인공지능" --year 2015~2024 --rows 100
uv run scienceon collect --config config/search.example.yaml   # 설정 기반 대량 수집
```

## 문서

- [docs/SCIENCEON_API_GUIDE.md](docs/SCIENCEON_API_GUIDE.md) — API 호출 규격 레퍼런스
- [docs/COLLECTION_WORKFLOW.md](docs/COLLECTION_WORKFLOW.md) — 반복 수집 SOP
- [docs/PROMPTS.md](docs/PROMPTS.md) — Claude 구동용 프롬프트 템플릿
- [docs/ROADMAP.md](docs/ROADMAP.md) — 기능 구현 계획(로드맵)

## 보안

- 자격증명은 **`.env` 또는 MCP `env` 블록**으로만 전달 — 코드/커밋/로그에 넣지 마세요.
- `.env`, 토큰 캐시는 `.gitignore` 로 제외됩니다.

## 관련 프로젝트
- [ansua79/scienceon-mcp](https://github.com/ansua79/scienceon-mcp) — KISTI 개발자의 ScienceOn MCP.
  ScienceOn **전 API(논문·특허·보고서·동향·연구자·기관·기술트렌드·뉴스 등 17개 도구)** 를 대화형으로
  폭넓게 노출하고 GUI 설치기도 제공. **폭넓은 탐색**이 목적이면 이 도구를 권장합니다.

> 본 프로젝트는 **연구용 자료수집·코퍼스 구축**에 특화되어 있습니다 — 다중쿼리 합집합 · 와일드카드 ·
> 후처리 필터(contains/lang) · 다중그룹 수집 · **xlsx/csv/json/sqlite 대량 내보내기** · config 재현 수집.
> (위 공식 도구와 역할이 상호 보완적)

## 라이선스

MIT © Yeondong Yang. 본 프로젝트는 KISTI의 비공식 클라이언트이며 KISTI와 제휴 관계가 없습니다.
ScienceOn 데이터 이용은 KISTI 약관·트래픽 정책을 따릅니다.
