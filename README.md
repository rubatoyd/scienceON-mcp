# scienceON-mcp

<!-- mcp-name: io.github.rubatoyd/scienceon-mcp -->

[![CI](https://github.com/rubatoyd/scienceON-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rubatoyd/scienceON-mcp/actions/workflows/ci.yml)

KISTI **ScienceON OpenAPI** 문헌 검색·메타데이터 수집기 — **MCP 서버 + CLI**.
자기 ScienceON API 키만 발급받으면 누구나 Claude(또는 CLI)에서 국내외 논문·보고서
서지 메타데이터를 검색·수집할 수 있습니다.

> An MCP server + CLI for KISTI ScienceON OpenAPI. Bring your own API key and let
> Claude search & collect academic literature metadata in any project.

## 현재 상태 (v0.4.0)

- ✅ 라이브 검증 완료 · pytest 37 + 콜드 스타트 스모크 CI · 도구 annotations
- ✅ **공식 MCP 레지스트리 발행됨**: `io.github.rubatoyd/scienceon-mcp`
- ✅ 자체완결 `.mcpb`(win/mac/linux, Python·uv 불필요) + 경량 `.mcpb` + uvx
- ⚠️ `mcp` SDK는 **1.x 고정**(`mcp>=1.2.0,<2`) — 2.0 에서 `mcp.server.fastmcp` 가 제거되어 상한 없이는 기동 실패

> **Claude 앱 안에서 검색해 설치할 수는 없습니다.** 공식 MCP 레지스트리 등재와 Claude Desktop
> **인앱 커넥터 디렉터리**는 별개이고 자동 동기화되지 않습니다. 아래 `.mcpb` 설치 · CLI 등록 ·
> 수동 config 중 하나를 쓰세요.

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
- ScienceON API 자격증명 (아래 발급 방법)

## 1) API 키 발급

1. [ScienceON](https://scienceon.kisti.re.kr) 회원가입·로그인
2. **API Gateway → 인증키 발급 신청** → 승인 후 `인증키`·`Client ID` 발급
3. **인증키관리**에서 신청 **MAC 주소** 등록, **IP관리**에서 호출 PC의 공인 IP 등록
4. 사용할 **서비스 콘텐츠(티켓)** 체크 (논문/보고서 등)

## 2) 설치

**전제: [uv](https://docs.astral.sh/uv/) 설치** (Windows: `winget install astral-sh.uv`).

### 방법 0 — 원클릭 (.mcpb, Claude Desktop)

[Releases](https://github.com/rubatoyd/scienceON-mcp/releases/latest) 에서 내려받아 Claude Desktop 에
더블클릭/드래그 → **설치 창에서 인증키·Client ID·MAC 입력** → 완료. 두 종류가 있습니다.

| 자산 | 특징 |
|---|---|
| **`scienceon-mcp-win-x64.mcpb`** / `…-macos-arm64.mcpb` / `…-linux-x64.mcpb` | **(권장) 자체완결** — Python·uv 불필요 |
| `scienceon-mcp.mcpb` | 경량(수 KB). 실행에 `uv` 필요 |

### 방법 A — uvx (설정 직접, 설치 불필요)
clone·venv 없이 아래 4)의 `uvx` 설정이 GitHub 버전을 자동 빌드·실행합니다.

> 코드를 수정·기여하려면(개발용) clone 후 `uv sync` — 클라우드 동기화 폴더(OneDrive 등)면
> venv를 폴더 밖에: `export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/scienceon-mcp"` 후 `uv sync`.

## 3) 자격증명
자기 ScienceON 키(발급: 위 1)를 **MCP 설정 `env` 블록**(아래) 또는 `.env`(`.env.example` 복사)로 전달.
코드/커밋/로그엔 넣지 마세요.

## 4) Claude에 MCP 연결 (설치 불필요 · uvx)

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scienceon": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/rubatoyd/scienceON-mcp", "scienceon-mcp"],
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
claude mcp add scienceon -- uvx --from "git+https://github.com/rubatoyd/scienceON-mcp" scienceon-mcp
```

> 첫 실행 시 빌드(수 초), 이후 캐시. 최신 반영은 `uvx --refresh ...`.
> 개발용 로컬 설치를 쓰면 command 를 venv 파이썬으로:
> `…\.venvs\scienceon-mcp\Scripts\python.exe -m scienceon_mcp.server`

### MCP 도구 (5종)

| 도구 | 하는 일 |
|---|---|
| `scienceON_status` | 연결/토큰 점검 (+공인 IP — E4006 진단용) |
| `scienceON_search` | 문헌 검색 — 다중쿼리·와일드카드(`*`)·연도범위·contains·lang |
| `scienceON_detail` | 제어번호(CN)로 초록·서지 전체 |
| `scienceON_export` | 대량 수집 → xlsx/csv/json/sqlite 저장 |
| `scienceON_collect_groups` | **다중 검색그룹**을 한 코퍼스로 합쳐 수집 — config 파일 없이 대화형 |

> **⚠️ 절단은 조용히 일어나지 않는다 (v0.2.0~)**
>
> 수집 도구는 `total`·`truncated` 를 함께 반환합니다. **수집량이 `max_records` 와 정확히 일치하면
> 거의 항상 절단된 것**이고, 그때는 경고 문구가 붙습니다. `meta.union_upper_bound`(실행한 검색축들의
> total 합 = 합집합 상한) 위로 `max_records` 를 올려 재수집해야 코퍼스가 완결됩니다.
> 절단된 결과를 완전한 코퍼스로 오인하면 후속 분석이 통째로 무효가 됩니다.

#### ⚠️ 회수량과 `total` 이 다를 때 — 절단인가 아닌가 (v0.4.0)

적대적 검증에서 **API 가 보고한 `total` 이 실제 서빙량보다 클 수 있다**는 것이 확인됐습니다
(실측: TI '경계선지능' total 263 / 실회수 262, 중복제거 0건). 그래서 두 사건을 **다른 플래그**로 구분합니다.

| 플래그 | 뜻 | 대처 |
|---|---|---|
| `truncated: true` | **우리 상한(`max_records`)에 걸렸다** | 상한을 올려 재수집하면 해결됩니다 |
| `total_mismatch: true` | 페이징을 끝까지 돌았는데 `total` 에 못 미쳤다 | **올려도 늘지 않습니다.** 회수량을 확정 수치로 쓰세요 |

> v0.4.0 이전에는 이 둘을 `truncated` 하나로 뭉쳐, 전수 수집을 마친 뒤에도 "상한을 올리라"는
> **틀린 조언**이 붙었습니다. 그 값을 읽던 코드가 있다면 의미가 달라졌으니 확인하세요.

**불완전 회수 자동 보정** — 다중 페이지 질의는 호출마다 결과가 흔들립니다(자매 프로젝트 kci 실측:
동일 조건 3회에 204/204/205, 레코드 합집합 205·교집합 203). 단일 페이지 질의는 안정적입니다.
그래서 `total` 에 못 미치고 상한도 아니면 **한 번 더 훑어 합집합**을 취합니다.
`meta.sweeps` 가 1보다 크면 보정이 돌았다는 뜻입니다. 끄려면 `retry_incomplete=0`.

**`scienceON_collect_groups` 가 왜 필요한가** — 단일 검색어로는 못 만드는 코퍼스가 있습니다.
변별력 있는 단어는 전체(BI)로 그대로 검색하고, 색인이 안 되는 토큰은 제목(TI) 와일드카드 +
`contains` 후처리로 정밀화하는 식으로 **그룹마다 다른 전략**을 걸어 합집합을 만듭니다.

```jsonc
[
  { "field": "BI", "terms": ["경계선지능", "경계선 지능"] },
  { "field": "TI", "terms": ["느린*"], "contains": ["느린학습자", "느린 학습자"] }
]
```
`save: false` 로 부르면 저장 없이 결과를 미리 볼 수 있습니다(응답에는 앞 100건만 실림).

### 다른 MCP 클라이언트 (Claude 전용 아님)

**소스에 Claude 결합 코드가 없습니다.** 공식 MCP SDK 의 표준 **stdio** 서버이므로 MCP 를 지원하는
에이전트면 그대로 붙습니다 — Cursor · Windsurf · Cline · Zed · VS Code Copilot(agent mode) ·
OpenAI Agents SDK · MCP SDK 로 만든 자체 클라이언트 등. 등록 형태는 위 `claude_desktop_config.json`
예시의 `command`/`args`/`env` 3요소를 각 클라이언트 설정에 그대로 옮기면 됩니다.

#### 전송 방식 — stdio(기본) · SSE · Streamable HTTP

로컬 서브프로세스(stdio)뿐 아니라 **HTTP 로도 띄울 수 있습니다.** 원격 호스팅이나 stdio 를 못 쓰는
클라이언트를 위한 경로입니다.

```bash
scienceon-mcp                                 # 기본: stdio (기존과 동일)
scienceon-mcp --transport streamable-http     # http://127.0.0.1:8000/mcp
scienceon-mcp --transport sse --port 9000     # http://127.0.0.1:9000/sse
```
환경변수로도 지정 가능: `SCIENCEON_MCP_TRANSPORT` · `SCIENCEON_MCP_HOST` · `SCIENCEON_MCP_PORT`.

> ⚠️ **HTTP 전송에는 인증이 없습니다.** 기본 바인드는 루프백(`127.0.0.1`)이라 같은 PC 에서만
> 접근됩니다. `--host 0.0.0.0` 으로 외부에 열면 **자격증명을 품은 서버를 그대로 공개하는 것**과
> 같습니다 — 신뢰된 망에서만, 필요하면 앞단에 리버스 프록시·인증을 두고 쓰세요.
> 서버도 기동 시 경고를 찍습니다.

**남은 제약** — 도구 설명이 **한국어**라 한국어를 다루는 모델이어야 도구 선택이 정확합니다.

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

## 보안 / 네트워크

- 자격증명은 **`.env` 또는 MCP `env` 블록**으로만 전달 — 코드/커밋/로그에 넣지 마세요.
- `.env`, 토큰 캐시는 `.gitignore` 로 제외됩니다.
- **교육망(학교·교육청)·사내망 SSL 인터셉션** 대응: `truststore` 로 **OS 신뢰저장소**를 사용해
  통과합니다(TLS 검증을 끄지 않습니다). 정식 의존성이라 `.mcpb` 설치본에도 적용됩니다.
  비활성하려면 `SCIENCEON_OS_TRUST=0`.
- 자격증명 오류·타임아웃 등 **어떤 예외도 도구 밖으로 새지 않습니다**(항상 `{"error": …}` 형태로 반환).

## 관련 프로젝트
- [ansua79/scienceon-mcp](https://github.com/ansua79/scienceon-mcp) — KISTI 개발자의 ScienceON MCP.
  ScienceON **전 API(논문·특허·보고서·동향·연구자·기관·기술트렌드·뉴스 등 17개 도구)** 를 대화형으로
  폭넓게 노출하고 GUI 설치기도 제공. **폭넓은 탐색**이 목적이면 이 도구를 권장합니다.

> 본 프로젝트는 **연구용 자료수집·코퍼스 구축**에 특화되어 있습니다 — 다중쿼리 합집합 · 와일드카드 ·
> 후처리 필터(contains/lang) · 다중그룹 수집 · **xlsx/csv/json/sqlite 대량 내보내기** · config 재현 수집.
> (위 공식 도구와 역할이 상호 보완적)

## 라이선스

MIT © Yeondong Yang. 본 프로젝트는 KISTI의 비공식 클라이언트이며 KISTI와 제휴 관계가 없습니다.
ScienceON 데이터 이용은 KISTI 약관·트래픽 정책을 따릅니다.
