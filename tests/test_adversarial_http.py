"""적대적 검증 — **실제 HTTP 왕복**으로 전송·인코딩·재시도 계층을 태운다.

왜 별도로 두는가: `requests.get` 을 monkeypatch 하는 테스트는 **전송·charset 감지·
재시도/백오프·URL 파라미터 인코딩 계층을 통째로 건너뛴다.** 이 저장소는 그 층이
한 번도 검증된 적 없었고, 로컬 서버를 띄워 돌리자마자 결함 3종이 나왔다(2026-08-12):

  🔴 토큰 응답 본문을 예외에 담아 refresh_token·client_id 가 MCP 응답까지 누출
  🔴 charset 헤더가 없으면 한글이 통째로 깨짐(Latin-1 폴백)
  🔴 rows=1·max_records=300 조합이 300회 요청을 유발

**이 저장소는 자격증명을 URL 쿼리에 싣는 유일한 프로젝트**다(토큰 엔드포인트에
client_id·accounts(AES 페이로드)·refreshToken 이 들어간다). 그래서 누출 검사가 최우선이다.
"""
from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

# 이 값들이 예외·응답 어디에도 나오면 안 된다
AUTH_KEY = "A" * 32
CLIENT_ID = "SECRET-CLIENT-ID-13579"
MAC = "AA:BB:CC:DD:EE:FF"
REFRESH = "SECRET-REFRESH-TOKEN-24680"
ACCESS = "SECRET-ACCESS-TOKEN-97531"
SECRETS = (AUTH_KEY, CLIENT_ID, REFRESH, ACCESS)

_XML = ('<?xml version="1.0" encoding="UTF-8"?><root><statusCode>200</statusCode>'
        "<TotalCount>{total}</TotalCount><recordList>{recs}</recordList></root>")
_REC = ('<record><item metaCode="CN">CN{i}</item><item metaCode="Title">한글 제목 {i}</item>'
        '<item metaCode="Pubyear">2020</item></record>')

STATE = {"mode": "normal", "total": 300, "calls": [], "fail_left": 0}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # 조용히
        pass

    def _send(self, body: bytes, status=200, ctype="text/xml; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        STATE["calls"].append({"path": u.path, "q": q})
        mode = STATE["mode"]

        if "tokenrequest" in u.path:
            if mode == "token_http_500":
                return self._send(b"boom", 500, "text/plain")
            if mode == "token_not_json":
                return self._send(b"<html>error</html>", 200, "text/html")
            if mode == "token_no_access":
                # 실패 응답에도 자격증명이 실려 온다 — 누출 후보 경로
                return self._send(json.dumps({"refresh_token": REFRESH,
                                              "client_id": CLIENT_ID,
                                              "error": "invalid_grant"}).encode(),
                                  200, "application/json")
            return self._send(json.dumps({"access_token": ACCESS, "refresh_token": REFRESH,
                                          "access_token_expire": "2030-01-01 00:00:00"}).encode(),
                              200, "application/json")

        rows = int(q.get("rowCount", 10) or 10)
        page = int(q.get("curPage", 1) or 1)
        total = STATE["total"]
        start = (page - 1) * rows
        n = max(0, min(rows, total - start))
        body = _XML.format(total=total, recs="".join(_REC.format(i=start + i) for i in range(n)))

        if mode == "api_http_500":
            return self._send(b"server error", 500, "text/plain")
        if mode == "api_429":
            return self._send(b"slow down", 429, "text/plain")
        if mode == "api_malformed":
            return self._send(b"<root><statusCode>200</statusCode><recordList><record>")
        if mode == "api_error_xml":
            return self._send(b'<?xml version="1.0"?><root><statusCode>401</statusCode>'
                              b"<errorCode>E4006</errorCode><errorMessage>IP</errorMessage></root>")
        if mode == "api_empty":
            return self._send(b"")
        if mode == "api_no_charset":
            return self._send(body.encode("utf-8"), 200, "text/xml")   # charset 없음
        if mode == "api_flaky" and STATE["fail_left"] > 0:
            STATE["fail_left"] -= 1
            return self._send(b"tmp", 503, "text/plain")
        return self._send(body.encode("utf-8"))


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def client(server, monkeypatch, tmp_path):
    """실제 소켓으로 로컬 서버를 때리는 클라이언트."""
    import scienceon_mcp.auth as authmod
    import scienceon_mcp.client as clientmod
    import scienceon_mcp.config as cfg

    monkeypatch.setattr(cfg, "TOKEN_URL", f"{server}/tokenrequest.do", raising=False)
    monkeypatch.setattr(authmod, "TOKEN_URL", f"{server}/tokenrequest.do", raising=False)
    monkeypatch.setattr(clientmod, "API_URL", f"{server}/openapicall.do", raising=False)
    monkeypatch.setattr(authmod, "_CACHE", tmp_path / "tok.json", raising=False)
    for k, v in (("SCIENCEON_AUTH_KEY", AUTH_KEY), ("SCIENCEON_CLIENT_ID", CLIENT_ID),
                 ("SCIENCEON_MAC_ADDRESS", MAC), ("SCIENCEON_OS_TRUST", "0")):
        monkeypatch.setenv(k, v)

    def make(mode="normal", total=300, fail=0):
        STATE.update(mode=mode, total=total, calls=[], fail_left=fail)
        return clientmod.ScienceONClient(throttle=0)
    return make


def _leaked(text: str) -> list[str]:
    return [s for s in SECRETS if s in text]


# ══ 자격증명 누출 — 최우선 ═══════════════════════════════════════════════════
@pytest.mark.parametrize("mode", [
    "token_http_500", "token_not_json", "token_no_access",
    "api_http_500", "api_429", "api_malformed", "api_error_xml", "api_empty",
])
def test_어떤_오류_경로에서도_자격증명이_새지_않는다(client, mode):
    """🔴 `token_no_access` 에서 실제로 샜다 — 토큰 응답 본문을 예외에 담고 있었다.

    이 저장소는 `raise_for_status` 로 같은 유형을 이미 한 번 고쳤는데 이 경로만 남아 있었다.
    """
    c = client(mode)
    msg = ""
    try:
        c.search("ARTI", {"BI": "테스트"}, max_records=10, rows=10)
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}"
    assert not _leaked(msg), f"[{mode}] 예외에 자격증명: {msg[:200]}"


@pytest.mark.parametrize("mode", ["token_no_access", "api_http_500", "api_error_xml"])
def test_MCP_도구_응답에_자격증명이_없다(client, mode, monkeypatch):
    """예외가 `_safe` 를 타고 MCP 응답 → LLM 트랜스크립트로 흘러가는 경로를 막는다."""
    from scienceon_mcp import server as srv
    c = client(mode)
    monkeypatch.setattr(srv, "ScienceONClient", lambda *a, **k: c)
    for out in (srv.scienceON_status(), srv.scienceON_search("테스트", rows=5)):
        assert isinstance(out, dict)
        blob = json.dumps(out, ensure_ascii=False, default=str)
        assert not _leaked(blob), f"[{mode}] 응답에 자격증명"


# ══ 전송 계층 ════════════════════════════════════════════════════════════════
def test_charset_헤더가_없어도_한글이_깨지지_않는다(client):
    """🔴 실제로 깨졌다 — `한글 제목` → `í\\x95\\x9cê¸\\x80`(UTF-8 을 Latin-1 로 읽음).

    monkeypatch 로 문자열을 돌려주는 테스트로는 절대 잡히지 않는 결함이다.
    """
    recs = client("api_no_charset").search("ARTI", {"BI": "테스트"}, max_records=5, rows=5)
    assert recs and "한글" in recs[0].title


@pytest.mark.parametrize("fails, ok", [(1, True), (2, True), (3, False)])
def test_일시적_503_재시도(client, fails, ok):
    from scienceon_mcp.client import ScienceONError
    c = client("api_flaky", fail=fails)
    if ok:
        assert c.search("ARTI", {"BI": "테스트"}, max_records=5, rows=5)
    else:
        with pytest.raises(ScienceONError):
            c.search("ARTI", {"BI": "테스트"}, max_records=5, rows=5)


@pytest.mark.parametrize("rows", [1, 5, 20])
def test_작은_rows_가_호출_폭주를_일으키지_않는다(client, rows):
    """🔴 rows=1·max_records=300 이 **300회 요청**을 유발했다.

    rows 는 전송 단위일 뿐 결과를 바꾸지 않으므로 여러 페이지가 필요하면 최대로 올린다.
    """
    c = client("normal", total=300)
    recs = c.search("ARTI", {"BI": "테스트"}, max_records=300, rows=rows)
    api_calls = [x for x in STATE["calls"] if "openapicall" in x["path"]]
    assert len(recs) == 300
    assert len(api_calls) <= 8, f"rows={rows} → {len(api_calls)}회 요청"


def test_자격증명은_쿼리로는_전달된다(client):
    """누출 검사가 과해서 **정상 전달까지 막지는 않았는지** 확인(대조군)."""
    client("normal").search("ARTI", {"BI": "테스트"}, max_records=5, rows=5)
    api = [x for x in STATE["calls"] if "openapicall" in x["path"]]
    assert api and api[0]["q"].get("client_id") == CLIENT_ID
    assert api[0]["q"].get("token") == ACCESS
