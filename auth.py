import os
from typing import Optional

from breeze_connect import BreezeConnect

try:
    import pyotp
except Exception:  # pragma: no cover
    pyotp = None


class BreezeSessionManager:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        session_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        totp_secret: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("ICICI_API_KEY")
        self.api_secret = api_secret or os.getenv("ICICI_API_SECRET")
        self.session_token = session_token or os.getenv("ICICI_SESSION_TOKEN")
        self.username = username or os.getenv("ICICI_USERNAME")
        self.password = password or os.getenv("ICICI_PASSWORD")
        self.totp_secret = totp_secret or os.getenv("ICICI_TOTP_SECRET")
        self.client = None

    def generate_totp(self) -> Optional[str]:
        if not self.totp_secret:
            return None
        if pyotp is None:
            raise ImportError("pyotp is required when ICICI_TOTP_SECRET is set")
        return pyotp.TOTP(self.totp_secret).now()

    def refresh_session(self):
        if not self.api_key or not self.api_secret:
            raise RuntimeError("ICICI_API_KEY and ICICI_API_SECRET are required for LIVE mode.")
        if not self.session_token:
            raise RuntimeError(
                "ICICI_SESSION_TOKEN is missing. Use the official ICICI Breeze login flow and store the valid "
                "apisession token in environment or GitHub Secrets before running LIVE mode."
            )

        self.client = BreezeConnect(api_key=self.api_key)
        try:
            self.client.generate_session(api_secret=self.api_secret, session_token=self.session_token)
            return self.client
        except Exception as exc:  # pragma: no cover - depends on live exchange auth status
            raise RuntimeError(
                "ICICI Breeze session refresh failed. Validate ICICI_API_SECRET and ICICI_SESSION_TOKEN. "
                "If the session expired, renew it via the official ICICI login flow."
            ) from exc

    def get_client(self):
        return self.refresh_session()
