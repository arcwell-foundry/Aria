"""Supabase client module for database operations."""

import logging
from typing import Any, cast

from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from src.core.config import settings
from src.core.exceptions import DatabaseError, NotFoundError
from supabase import Client, create_client

logger = logging.getLogger(__name__)

_supabase_circuit_breaker = CircuitBreaker("supabase")


class SupabaseClient:
    """Singleton Supabase client for backend operations."""

    _client: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        """Get or create the Supabase client singleton.

        Returns:
            Initialized Supabase client.

        Raises:
            DatabaseError: If client initialization fails.
        """
        if cls._client is None:
            try:
                cls._client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
                )
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.exception("Failed to initialize Supabase client")
                raise DatabaseError(f"Failed to initialize database connection: {e}") from e
        return cls._client

    @classmethod
    def reset_client(cls) -> None:
        """Reset the client singleton (useful for testing)."""
        cls._client = None

    @classmethod
    async def get_user_by_id(cls, user_id: str) -> dict[str, Any]:
        """Fetch a user profile by ID.

        Args:
            user_id: The user's UUID.

        Returns:
            User profile data.

        Raises:
            NotFoundError: If user not found.
            DatabaseError: If database operation fails.
        """
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            response = (
                client.table("user_profiles").select("*").eq("id", user_id).single().execute()
            )
            if response.data is None:
                raise NotFoundError("User", user_id)
            _supabase_circuit_breaker.record_success()
            return cast(dict[str, Any], response.data)
        except NotFoundError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error fetching user", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch user: {e}") from e

    @classmethod
    async def get_company_by_id(cls, company_id: str) -> dict[str, Any]:
        """Fetch a company by ID.

        Args:
            company_id: The company's UUID.

        Returns:
            Company data.

        Raises:
            NotFoundError: If company not found.
            DatabaseError: If database operation fails.
        """
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            response = client.table("companies").select("*").eq("id", company_id).single().execute()
            if response.data is None:
                raise NotFoundError("Company", company_id)
            _supabase_circuit_breaker.record_success()
            return cast(dict[str, Any], response.data)
        except NotFoundError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error fetching company", extra={"company_id": company_id})
            raise DatabaseError(f"Failed to fetch company: {e}") from e

    @classmethod
    async def get_user_settings(cls, user_id: str) -> dict[str, Any]:
        """Fetch user settings by user ID.

        Args:
            user_id: The user's UUID.

        Returns:
            User settings data.

        Raises:
            NotFoundError: If settings not found.
            DatabaseError: If database operation fails.
        """
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            response = (
                client.table("user_settings").select("*").eq("user_id", user_id).single().execute()
            )
            if response.data is None:
                raise NotFoundError("User settings", user_id)
            _supabase_circuit_breaker.record_success()
            return cast(dict[str, Any], response.data)
        except NotFoundError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error fetching user settings", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch user settings: {e}") from e

    @classmethod
    async def create_user_profile(
        cls,
        user_id: str,
        full_name: str | None = None,
        company_id: str | None = None,
        role: str = "user",
    ) -> dict[str, Any]:
        """Create a new user profile.

        Args:
            user_id: The user's UUID (from auth.users).
            full_name: User's full name.
            company_id: Optional company UUID.
            role: User role (default: "user").

        Returns:
            Created user profile data.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            data: dict[str, Any] = {
                "id": user_id,
                "full_name": full_name,
                "company_id": company_id,
                "role": role,
            }
            response = client.table("user_profiles").insert(data).execute()
            if response.data and len(response.data) > 0:
                _supabase_circuit_breaker.record_success()
                return cast(dict[str, Any], response.data[0])
            raise DatabaseError("Failed to create user profile")
        except DatabaseError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error creating user profile", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to create user profile: {e}") from e

    @classmethod
    async def create_user_settings(cls, user_id: str) -> dict[str, Any]:
        """Create default user settings.

        Args:
            user_id: The user's UUID.

        Returns:
            Created user settings data.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "preferences": {},
                "integrations": {},
            }
            response = client.table("user_settings").insert(data).execute()
            if response.data and len(response.data) > 0:
                _supabase_circuit_breaker.record_success()
                return cast(dict[str, Any], response.data[0])
            raise DatabaseError("Failed to create user settings")
        except DatabaseError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error creating user settings", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to create user settings: {e}") from e

    @classmethod
    async def create_company(cls, name: str, domain: str | None = None) -> dict[str, Any]:
        """Create a new company.

        Args:
            name: Company name.
            domain: Optional company domain.

        Returns:
            Created company data.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            data: dict[str, Any] = {"name": name, "domain": domain, "settings": {}}
            response = client.table("companies").insert(data).execute()
            if response.data and len(response.data) > 0:
                _supabase_circuit_breaker.record_success()
                return cast(dict[str, Any], response.data[0])
            raise DatabaseError("Failed to create company")
        except DatabaseError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error creating company", extra={"company_name": name})
            raise DatabaseError(f"Failed to create company: {e}") from e


# Convenience function for dependency injection
def get_supabase_client() -> Client:
    """Get Supabase client for FastAPI dependency injection.

    Returns:
        Supabase client instance.
    """
    return SupabaseClient.get_client()
