# Claude Desktop 확장(.mcpb)

`manifest.json` = Claude Desktop 데스크톱 확장 정의. 설치 시 **인증키·Client ID·MAC 입력 UI**가
뜨고, 입력값은 안전하게 저장되어 MCP 서버 실행 시 환경변수로 주입된다.
서버 실행은 `uvx --from git+…/scienceon-mcp scienceon-mcp` (uv 필요, clone 불필요).

## 재빌드
```bash
npx -y @anthropic-ai/mcpb validate mcpb/manifest.json
npx -y @anthropic-ai/mcpb pack mcpb dist/scienceon-mcp.mcpb
```
빌드된 `.mcpb` 는 GitHub Release 에 첨부해 배포한다.

## 설치 (사용자)
1. [Releases](https://github.com/rubatoyd/scienceON-mcp/releases) 에서 `scienceon-mcp.mcpb` 다운로드
2. Claude Desktop 에 드래그(또는 더블클릭) → 설치 창에서 키 3종 입력 → 완료
3. 전제: [uv](https://docs.astral.sh/uv/) 설치 (`winget install astral-sh.uv`)

> 설치 후 도구가 안 보이면 Claude Desktop 재시작. 동작 안 하면 README 의 수동 `uvx` 설정으로 대체.
