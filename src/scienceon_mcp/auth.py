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

from .config import TOKEN_URL, Credentials

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


def request_token(creds: Credentials, *, timeout: int = 15) -> dict[str, Any]:
    """신규 Access/Refresh 토큰 발급."""
    accounts = quote(encrypt_accounts(creds.auth_key, creds.mac_address))
    url = f"{TOKEN_URL}?client_id={creds.client_id}&accounts={accounts}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(creds: Credentials, refresh_token: str, *, timeout: int = 15) -> dict[str, Any]:
    """Refresh Token 으로 Access Token 재발급."""
    url = f"{TOKEN_URL}?refreshToken={refresh_token}&client_id={creds.client_id}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


class TokenManager:
    """Access Token 캐시·만료·자동 갱신 관리."""

    def __init__(self, creds: Credentials | None = None):
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
            raise RuntimeError(f"토큰 발급 실패 — 응답: {tok}")

        self._tok = tok
        self._exp_epoch = self._parse_expire(tok)
        self._save_cache()
        return tok["access_token"]
