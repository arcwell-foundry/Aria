"""Configuration management using Pydantic Settings."""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Supabase Configuration
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: SecretStr = SecretStr("")
    SUPABASE_SERVICE_ROLE_KEY: SecretStr = SecretStr("")

    # Anthropic Claude API
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")

    # OpenAI (for embeddings - required by Graphiti)
    OPENAI_API_KEY: SecretStr = SecretStr("")

    # Neo4j (Graphiti) Configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: SecretStr = SecretStr("")

    # Tavus (Phase 6)
    TAVUS_API_KEY: SecretStr | None = None
    TAVUS_PERSONA_ID: str = ""
    TAVUS_REPLICA_ID: str = ""
    TAVUS_CALLBACK_URL: str = ""
    TAVUS_GUARDRAILS_ID: str = ""
    TAVUS_WEBHOOK_SECRET: str = ""  # Webhook signature verification secret

    # Daily.co (Phase 6)
    DAILY_API_KEY: SecretStr | None = None

    # Composio OAuth Configuration
    COMPOSIO_API_KEY: SecretStr | None = None
    COMPOSIO_BASE_URL: str = "https://api.composio.dev"  # Deprecated: SDK manages its own URL

    # Skills.sh Integration Configuration
    SKILLS_SH_API_URL: str = "https://api.skills.sh/v1"
    SKILLS_SH_GITHUB_URL: str = "https://raw.githubusercontent.com/skills-sh/skills/main"
    SKILLS_SYNC_INTERVAL_HOURS: int = 24
    SKILLS_MAX_CONTEXT_SUMMARIES: int = 50

    # Exa API (web research for enrichment — optional)
    EXA_API_KEY: str = ""
    EXA_WEBHOOK_SECRET: str = ""  # Webhook signature verification secret

    # Application Settings
    APP_SECRET_KEY: SecretStr = SecretStr("")
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_URL: str = "http://localhost:3000"  # Base URL for webhook callbacks

    # Stripe Configuration (US-928)
    STRIPE_SECRET_KEY: SecretStr = SecretStr("")
    STRIPE_WEBHOOK_SECRET: SecretStr = SecretStr("")
    STRIPE_PRICE_ID: str = ""  # Default price ID for annual subscription

    # Resend Email Configuration (US-934)
    RESEND_API_KEY: SecretStr = SecretStr("")
    FROM_EMAIL: str = "ARIA <aria@luminone.com>"

    # Rate Limiting Configuration (US-930)
    RATE_LIMIT_ENABLED: bool = True  # Global rate limiting toggle
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100  # Default limit for all endpoints

    # Logging
    LOG_FORMAT: Literal["text", "json"] = "text"
    LOG_LEVEL: str = "INFO"

    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Confidence Scoring Configuration
    CONFIDENCE_DECAY_RATE_PER_DAY: float = 0.05 / 30  # 5% per month
    CONFIDENCE_CORROBORATION_BOOST: float = 0.10  # +10% per corroborating source
    CONFIDENCE_MAX: float = 0.99  # Maximum confidence after boosts
    CONFIDENCE_MIN_THRESHOLD: float = 0.3  # Minimum for inclusion in responses
    CONFIDENCE_REFRESH_WINDOW_DAYS: int = 7  # Days before decay starts after refresh

    # Salience Decay Configuration (US-218)
    SALIENCE_HALF_LIFE_DAYS: int = 30  # Days for salience to decay to 50%
    SALIENCE_ACCESS_BOOST: float = 0.1  # Boost per memory retrieval
    SALIENCE_MIN: float = 0.01  # Minimum salience (never zero)

    # Cost Governor Configuration (Wave 0)
    COST_GOVERNOR_ENABLED: bool = True
    COST_GOVERNOR_DAILY_TOKEN_BUDGET: int = 2_000_000
    COST_GOVERNOR_DAILY_THINKING_BUDGET: int = 500_000
    COST_GOVERNOR_SOFT_LIMIT_PERCENT: float = 0.80
    COST_GOVERNOR_MAX_RETRIES_PER_GOAL: int = 3
    COST_GOVERNOR_INPUT_TOKEN_COST_PER_M: float = 3.00
    COST_GOVERNOR_OUTPUT_TOKEN_COST_PER_M: float = 15.00
    COST_GOVERNOR_THINKING_TOKEN_COST_PER_M: float = 15.00

    @field_validator("SUPABASE_URL")
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        """Validate that SUPABASE_URL is a valid URL."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("SUPABASE_URL must start with http:// or https://")
        return v.rstrip("/") if v else v

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"

    @property
    def is_configured(self) -> bool:
        """Check if required settings are configured."""
        return bool(
            self.SUPABASE_URL
            and self.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
            and self.ANTHROPIC_API_KEY.get_secret_value()
        )

    @property
    def exa_configured(self) -> bool:
        """Check if Exa API is configured for web enrichment."""
        return bool(self.EXA_API_KEY)

    async def check_exa_credits(self) -> tuple[bool, str]:
        """Check if Exa API has available credits.

        Returns:
            Tuple of (has_credits, message) where message explains any issues.
        """
        if not self.EXA_API_KEY:
            return False, "EXA_API_KEY not configured"

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Use a minimal search to test credits
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": self.EXA_API_KEY},
                    json={
                        "query": "test",
                        "numResults": 1,
                    },
                    timeout=10.0,
                )
                if response.status_code == 200:
                    return True, "Exa API operational"
                elif response.status_code == 402:
                    return False, "Exa API credits exceeded. Visit dashboard.exa.ai to top up."
                else:
                    error_body = response.text[:200]
                    return False, f"Exa API error (status {response.status_code}): {error_body}"
        except Exception as e:
            return False, f"Exa API connection failed: {e}"

    def validate_startup(self) -> None:
        """Validate that all required secrets are configured.

        Raises:
            ValueError: If any required secret is missing or empty.
        """
        required_secrets = {
            "SUPABASE_URL": self.SUPABASE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": self.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
            "ANTHROPIC_API_KEY": self.ANTHROPIC_API_KEY.get_secret_value(),
            "APP_SECRET_KEY": self.APP_SECRET_KEY.get_secret_value(),
        }
        missing = [name for name, value in required_secrets.items() if not value or value == ""]
        if missing:
            raise ValueError(f"Required secrets are missing or empty: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings instance with validated configuration.

    Raises:
        ValueError: If required secrets are missing.
    """
    settings = Settings()
    settings.validate_startup()
    return settings


# Global settings instance - import this for easy access
settings = get_settings()
