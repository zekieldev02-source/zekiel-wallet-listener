from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    BACKEND_URL: str = "http://127.0.0.1:8000"
    INTERNAL_API_KEY: str = "changeme-internal-key"

    HELIUS_WS_URL: str = "wss://mainnet.helius-rpc.com"
    HELIUS_API_KEY: str = ""

    LISTENER_HTTP_PORT: int = 8001

    ACTIVE_USERS_REFRESH_SECONDS: int = 60
    WS_RECONNECT_SECONDS: int = 5
    HTTP_TIMEOUT_SECONDS: int = 5

    @property
    def helius_ws_endpoint(self) -> str:
        return f"{self.HELIUS_WS_URL}/?api-key={self.HELIUS_API_KEY}"

    @property
    def helius_enhanced_tx_url(self) -> str:
        return f"https://api.helius.xyz/v0/transactions?api-key={self.HELIUS_API_KEY}"


settings = Settings()
