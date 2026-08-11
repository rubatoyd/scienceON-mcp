"""환경설정 및 자격증명 로딩.

자격증명은 코드/로그에 하드코딩하지 않고 `.env`(gitignore)에서만 읽는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# .env 를 한 번 로드 (이미 설정된 환경변수는 덮어쓰지 않음)
load_dotenv(override=False)

# 엔드포인트 (필요 시 .env 로 재정의 가능)
TOKEN_URL = os.environ.get(
    "SCIENCEON_TOKEN_URL", "https://apigateway.kisti.re.kr/tokenrequest.do"
)
API_URL = os.environ.get(
    "SCIENCEON_API_URL", "https://apigateway.kisti.re.kr/openapicall.do"
)


_TRUST_INJECTED = False


def use_os_trust() -> bool:
    """OS 신뢰 저장소(Windows/macOS)로 TLS 검증을 위임.

    교육망(학교/교육청)·사내망의 SSL 인터셉션은 자체서명 루트 CA를 OS 신뢰저장소에 심어둔다.
    requests 는 기본적으로 certifi 만 보므로 그 CA를 모른다 → truststore 로 OS 저장소를 쓰게 하면
    **검증을 끄지 않고도** 통과한다. `SCIENCEON_OS_TRUST=0` 이면 비활성. (한 번만 주입)

    ⚠️ 이전에는 MCP 등록 명령줄(`uv run --with truststore … inject_into_ssl()`)에만 걸려 있어
       `.mcpb` 번들 등 다른 기동 경로에는 적용되지 않았다. 정식 의존성으로 옮겨 모든 경로를 덮는다.
    """
    global _TRUST_INJECTED
    if _TRUST_INJECTED:
        return True
    if (os.environ.get("SCIENCEON_OS_TRUST") or "1").strip() in ("0", "false", "no"):
        return False
    try:
        import truststore

        truststore.inject_into_ssl()
        _TRUST_INJECTED = True
        return True
    except Exception as e:  # noqa: BLE001
        import logging

        logging.getLogger("scienceon_mcp").warning(
            "truststore OS 신뢰저장소 주입 실패(%s) — TLS 인터셉션 망에서 인증서 오류 가능. "
            "대안: REQUESTS_CA_BUNDLE 로 루트 CA 지정.", type(e).__name__)
        return False


@dataclass(frozen=True)
class Credentials:
    """ScienceON API Gateway 발급 자격증명."""

    auth_key: str       # 32자리 — AES-256 암호화 키
    client_id: str      # 호출 식별자
    mac_address: str    # 토큰 페이로드 (등록 MAC)
    account_id: str | None = None

    @classmethod
    def from_env(cls) -> "Credentials":
        missing = [
            k
            for k in ("SCIENCEON_AUTH_KEY", "SCIENCEON_CLIENT_ID", "SCIENCEON_MAC_ADDRESS")
            if not os.environ.get(k)
        ]
        if missing:
            raise RuntimeError(
                "필수 환경변수 누락: "
                + ", ".join(missing)
                + " — .env(.env.example 참고)를 설정하세요."
            )
        return cls(
            auth_key=os.environ["SCIENCEON_AUTH_KEY"].strip(),
            client_id=os.environ["SCIENCEON_CLIENT_ID"].strip(),
            mac_address=os.environ["SCIENCEON_MAC_ADDRESS"].strip(),
            account_id=(os.environ.get("SCIENCEON_ACCOUNT_ID") or "").strip() or None,
        )

    def redacted(self) -> str:
        """로그용 마스킹 표현 (자격증명 노출 방지)."""
        def mask(s: str) -> str:
            return f"{s[:4]}…{s[-2:]}" if s and len(s) > 6 else "***"

        return (
            f"Credentials(auth_key={mask(self.auth_key)}, "
            f"client_id={mask(self.client_id)}, mac={self.mac_address})"
        )
