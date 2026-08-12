"""AES256 토큰 발급/캐시/갱신 — 공식 ScienceON 샘플 스킴(라이브 검증 완료).

암호화(공식 Python 샘플 기준):
  - 평문: {"datetime":"YYYYMMDDHHMMSS","mac_address":"<MAC>"} (compact, 공백 제거)
  - AES-256-CBC, key=인증키(UTF-8 32바이트), IV='jvHJ1EFA0IXBrxxz'(고정 16바이트), PKCS7
  - urlsafe base64 인코딩 → URL 인코딩
토큰 발급:  tokenrequest.do?client_id=<ID>&accounts=<enc>
토큰 재발급: tokenrequest.do?refreshToken=<RT>&client_id=<ID>
"""
from __future__ import annotations

import base64
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from .config import TOKEN_URL, Credentials, use_os_trust

_IV = b"jvHJ1EFA0IXBrxxz"  # 공식 샘플 고정 IV (16바이트)
# 실행 cwd 와 무관하게 토큰을 재사용하도록 홈 디렉토리에 캐시 (MCP는 임의 cwd에서 기동)
_CACHE = Path.home() / ".scienceon_token_cache.json"


def encrypt_accounts(auth_key: str, mac_address: str) -> str:
    """{datetime, mac_address} 를 AES256 암호화 → urlsafe base64 문자열."""
    key = auth_key.encode("utf-8")
    if len(key) != 32:
        raise ValueError(f"인증키는 32바이트여야 합니다 (현재 {len(key)}).")
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    plain = json.dumps({"datetime": now, "mac_address": mac_address}).replace(" ", "")
    ct = AES.new(key, AES.MODE_CBC, _IV).encrypt(pad(plain.encode("utf-8"), 16))
    return base64.urlsafe_b64encode(ct).decode("ascii")


def _get_json(url: str, timeout: int, what: str) -> dict[str, Any]:
    """토큰 엔드포인트 호출 — **예외 메시지에 URL 을 절대 싣지 않는다.**

    ⚠️ 이 URL 의 쿼리에는 client_id·accounts(AES 페이로드)·refreshToken 이 들어 있다.
       requests 예외(HTTPError/ConnectionError/Timeout/SSLError)는 메시지에 요청 URL 전체를
       담으므로, 그대로 올리면 도구의 _safe 를 타고 자격증명이 MCP 응답에 실린다.
       상태코드와 예외 타입명만 보고한다.
    """
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"{what} 실패 — 네트워크 오류({type(e).__name__}).") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"{what} 실패 — HTTP {resp.status_code}.")
    return resp.json()


def request_token(creds: Credentials, *, timeout: int = 15) -> dict[str, Any]:
    """신규 Access/Refresh 토큰 발급."""
    accounts = quote(encrypt_accounts(creds.auth_key, creds.mac_address))
    url = f"{TOKEN_URL}?client_id={creds.client_id}&accounts={accounts}"
    return _get_json(url, timeout, "토큰 발급")


def refresh_access_token(creds: Credentials, refresh_token: str, *, timeout: int = 15) -> dict[str, Any]:
    """Refresh Token 으로 Access Token 재발급."""
    url = f"{TOKEN_URL}?refreshToken={refresh_token}&client_id={creds.client_id}"
    return _get_json(url, timeout, "토큰 갱신")


class TokenManager:
    """Access Token 캐시·만료·자동 갱신 관리."""

    def __init__(self, creds: Credentials | None = None):
        # 토큰 발급도 HTTPS 다 — 클라이언트 없이 단독 사용되는 경로까지 덮는다
        use_os_trust()
        self.creds = creds or Credentials.from_env()
        self._tok: dict[str, Any] | None = None
        self._exp_epoch: float = 0.0
        self._load_cache()

    def _load_cache(self) -> None:
        if _CACHE.exists():
            try:
                data = json.loads(_CACHE.read_text(encoding="utf-8"))
                if data.get("client_id") == self.creds.client_id:
                    self._tok = data.get("token")
                    self._exp_epoch = float(data.get("exp_epoch", 0))
            except Exception:
                self._tok, self._exp_epoch = None, 0.0

    def _save_cache(self) -> None:
        try:
            _CACHE.write_text(
                json.dumps({"client_id": self.creds.client_id,
                            "token": self._tok, "exp_epoch": self._exp_epoch}),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _parse_expire(tok: dict[str, Any]) -> float:
        raw = (tok.get("access_token_expire") or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
            try:
                return datetime.strptime(raw, fmt).timestamp()
            except (ValueError, TypeError):
                continue
        return time.time() + 7200  # Access Token 기본 2시간

    def get_access_token(self, *, force: bool = False) -> str:
        if not force and self._tok and time.time() < self._exp_epoch - 90:
            return self._tok["access_token"]

        tok: dict[str, Any] | None = None
        # 캐시에 refresh_token 이 있으면 우선 재발급 시도
        if not force and self._tok and self._tok.get("refresh_token"):
            try:
                rt = refresh_access_token(self.creds, self._tok["refresh_token"])
                if "access_token" in rt:
                    tok = rt
                    # 재발급 응답에 refresh 정보가 없으면 기존 값 유지
                    tok.setdefault("refresh_token", self._tok["refresh_token"])
                    tok.setdefault("refresh_token_expire", self._tok.get("refresh_token_expire", ""))
            except Exception:
                tok = None

        if tok is None:
            tok = request_token(self.creds)
        if "access_token" not in tok:
            # 🔴 **응답 본문을 그대로 실으면 안 된다.** 토큰 엔드포인트는 실패 응답에도
            #    `refresh_token`·`client_id` 를 담아 보내고, 이 예외는 도구의 `_safe` 를 타고
            #    MCP 응답 → LLM 트랜스크립트까지 흘러간다. 적대적 검증에서 실제로 재현됐다
            #    (`scienceON_status` 응답에 refresh_token 이 그대로 실렸다).
            #    이 저장소는 `raise_for_status` 로 같은 유형을 이미 한 번 고쳤는데 이 경로만 남아 있었다.
            #    진단에 필요한 건 **어떤 키가 왔는가**지 값이 아니다.
            keys = ", ".join(sorted(tok)) or "(빈 응답)"
            raise RuntimeError(
                f"토큰 발급 실패 — 응답에 access_token 이 없습니다. 받은 필드: {keys}")

        self._tok = tok
        self._exp_epoch = self._parse_expire(tok)
        self._save_cache()
        return tok["access_token"]
