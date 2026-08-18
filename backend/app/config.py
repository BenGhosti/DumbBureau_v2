from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:////appdata/dumbbureau/db.sqlite"
    admin_recovery_secret: str = "LOCKED_UNTIL_ENV"
    secret_key: str = "change-me-in-production"
    # Optional dedicated key for at-rest encryption (AES-128-GCM + Argon2id).
    # Falls back to SECRET_KEY when empty.
    encryption_key: str = ""
    log_level: str = "INFO"
    # No default here on purpose: this must be YOUR reverse proxy's fixed
    # IP (see .env.example). An empty value means client_ip() never trusts
    # X-Forwarded-For/X-Real-IP and always falls back to the direct TCP
    # peer - safe-by-default rather than guessing a network that may not
    # match your actual proxy setup.
    trusted_proxy_ips: str = ""
    cors_origins: str = "http://localhost:8360"
    appdata_dir: Path = Path("/appdata/dumbbureau")

    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "DumbBureau"
    webauthn_origin: str = "http://localhost:8360"

    challenge_ttl_seconds: int = 300
    access_token_ttl_minutes: int = 60
    invite_token_ttl_days: int = 7
    recovery_token_ttl_minutes: int = 30

    @property
    def templates_dir(self) -> Path:
        return self.appdata_dir / "templates"

    @property
    def exports_dir(self) -> Path:
        return self.appdata_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.appdata_dir / "logs"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [
            o.strip()
            for o in self.trusted_proxy_ips.replace(" ", ",").split(",")
            if o.strip()
        ]

    def ensure_dirs(self) -> None:
        for directory in (self.templates_dir, self.exports_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
