from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_name: str = Field(default="emoji_casino", alias="APP_NAME")
    public_domain: str | None = Field(default=None, alias="PUBLIC_DOMAIN")
    bot_token_test: str = Field(alias="BOT_TOKEN_TEST")
    bot_token_main: str = Field(alias="BOT_TOKEN_MAIN")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    payment_provider_token: str = Field(alias="PAYMENT_PROVIDER_TOKEN")
    payments_enabled: bool = Field(default=True, alias="PAYMENTS_ENABLED")
    bonus_bet_frac: float = Field(default=0.2, alias="BONUS_BET_FRAC")
    max_bonus_bet_cap: int = Field(default=500, alias="MAX_BONUS_BET_CAP")
    welcome_bonus_coins: int = Field(default=0, alias="WELCOME_BONUS_COINS")
    welcome_free_spins: int = Field(default=0, alias="WELCOME_FREE_SPINS")
    welcome_enabled: bool = Field(default=False, alias="WELCOME_ENABLED")
    bonus_wr_enabled: bool = Field(default=True, alias="BONUS_WR_ENABLED")
    wr_welcome: float = Field(default=1.0, alias="WR_WELCOME")
    cap_welcome: float = Field(default=1.0, alias="CAP_WELCOME")
    admin_id: int | None = Field(default=None, alias="ADMIN_ID")
    treasury_xtr_start: int = Field(default=0, alias="TREASURY_XTR_START")
    treasury_floor_xtr: int = Field(default=0, alias="TREASURY_FLOOR_XTR")
    gifts_budget_xtr_day: int = Field(default=0, alias="GIFTS_BUDGET_XTR_DAY")
    gift_small_cost_bonus: int = Field(default=0, alias="GIFT_SMALL_COST_BONUS")
    gift_small_cost_xtr: int = Field(default=0, alias="GIFT_SMALL_COST_XTR")
    gift_medium_cost_bonus: int = Field(default=0, alias="GIFT_MEDIUM_COST_BONUS")
    gift_medium_cost_xtr: int = Field(default=0, alias="GIFT_MEDIUM_COST_XTR")
    gift_big_cost_bonus: int = Field(default=0, alias="GIFT_BIG_COST_BONUS")
    gift_big_cost_xtr: int = Field(default=0, alias="GIFT_BIG_COST_XTR")
    referral_bonus_coins: int = Field(default=0, alias="REFERRAL_BONUS_COINS")
    referral_wr: float = Field(default=1.0, alias="REFERRAL_WR")
    referral_cap: int = Field(default=0, alias="REFERRAL_CAP")
    crash_jwt_secret: str = Field(alias="CRASH_JWT_SECRET")
    crash_jwt_ttl: int = Field(default=600, alias="CRASH_JWT_TTL")
    crash_bet_min: int = Field(default=10, alias="CRASH_BET_MIN")
    crash_bet_max: int = Field(default=100_000, alias="CRASH_BET_MAX")
    crash_bet_duration_ms: int = Field(default=5000, alias="CRASH_BET_DURATION_MS")
    crash_round_duration_ms: int = Field(default=20000, alias="CRASH_ROUND_DURATION_MS")

    @property
    def bot_tokens(self) -> dict[str, str]:
        tokens: dict[str, str] = {}
        if self.bot_token_main:
            tokens["main"] = self.bot_token_main
        if self.bot_token_test:
            tokens["test"] = self.bot_token_test
        return tokens


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
