"""Apollo.io API client with dual-mode support (BYOK vs LuminOne-provided).

This client handles:
- API key resolution (customer's encrypted key or LuminOne master key)
- Credit checking and consumption
- Dual-write to apollo_credit_log (customer credits) and api_usage_tracking (internal COGS)
"""

import logging
from datetime import date, datetime
from typing import Any, Optional

from src.core.config import settings
from src.db.supabase import SupabaseClient
from src.utils.encryption import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/api/v1"


class ApolloCreditLimitExceeded(Exception):
    """Raised when a company exceeds their Apollo credit limit."""

    def __init__(self, company_id: str, credits_needed: int, credits_remaining: int):
        self.company_id = company_id
        self.credits_needed = credits_needed
        self.credits_remaining = credits_remaining
        super().__init__(
            f"Apollo credit limit exceeded for company {company_id}. "
            f"Needed: {credits_needed}, Remaining: {credits_remaining}"
        )


class ApolloClient:
    """
    Apollo.io API client with dual-mode support.

    Mode 1 (BYOK): Uses customer's own API key from apollo_config (encrypted)
    Mode 2 (LuminOne): Uses LuminOne's master key with credit metering
    """

    def __init__(self, supabase_client: Optional[Any] = None):
        """Initialize Apollo client.

        Args:
            supabase_client: Supabase client instance. If None, gets default.
        """
        if supabase_client:
            self._db = supabase_client
        else:
            from src.db.supabase import SupabaseClient

            self._db = SupabaseClient.get_client()

        # Master key for LuminOne-provided mode
        self._master_key: Optional[str] = None
        if settings.APOLLO_API_KEY:
            self._master_key = settings.APOLLO_API_KEY.get_secret_value()

    async def get_config(self, company_id: str) -> Optional[dict]:
        """Get Apollo configuration for a company.

        Args:
            company_id: The company's UUID.

        Returns:
            Configuration dict or None if not configured.
        """
        try:
            result = (
                self._db.table("apollo_config")
                .select("*")
                .eq("company_id", company_id)
                .maybe_single()
                .execute()
            )
            return result.data if result else None
        except Exception as e:
            logger.error(f"Failed to get Apollo config for company {company_id}: {e}")
            return None

    async def resolve_api_key(self, company_id: str) -> tuple[Optional[str], str]:
        """
        Resolve the API key to use for a company.

        Returns (api_key, mode) where mode is one of:
        - 'byok': Customer's encrypted key decrypted
        - 'luminone_provided': LuminOne master key
        - 'credit_limit_reached': Company has no credits left
        - 'unconfigured': No Apollo configured for this company

        Args:
            company_id: The company's UUID.

        Returns:
            Tuple of (api_key or None, mode string).
        """
        config = await self.get_config(company_id)

        if not config or not config.get("is_active"):
            return None, "unconfigured"

        # BYOK mode: decrypt customer's key
        if config["mode"] == "byok":
            encrypted_key = config.get("encrypted_api_key")
            if encrypted_key:
                decrypted = decrypt_api_key(encrypted_key)
                if decrypted:
                    return decrypted, "byok"
            # Fallback to legacy plaintext key during migration
            legacy_key = config.get("customer_api_key")
            if legacy_key:
                logger.warning(
                    f"Company {company_id} using legacy plaintext API key - should migrate to encrypted"
                )
                return legacy_key, "byok"
            return None, "unconfigured"

        # LuminOne-provided mode
        if config["mode"] == "luminone_provided":
            # Check credit limit
            credits_used = config.get("credits_used_this_cycle", 0)
            credit_limit = config.get("monthly_credit_limit", 500)

            if credits_used >= credit_limit:
                logger.warning(f"Apollo credit limit reached for company {company_id}")
                return None, "credit_limit_reached"

            if not self._master_key:
                logger.error("APOLLO_API_KEY not configured in environment")
                return None, "unconfigured"

            return self._master_key, "luminone_provided"

        return None, "unconfigured"

    async def get_pricing(self, action: str) -> tuple[int, float]:
        """
        Get credit cost and cost per credit for an action.

        Args:
            action: The Apollo action type (e.g., 'people_enrich_email').

        Returns:
            Tuple of (credits_per_call, cost_cents_per_credit).
        """
        try:
            result = (
                self._db.table("vendor_api_pricing")
                .select("credits_per_call, cost_cents_per_credit")
                .eq("vendor", "apollo")
                .eq("action", action)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                return (
                    result.data.get("credits_per_call", 0),
                    float(result.data.get("cost_cents_per_credit", 0)),
                )
        except Exception as e:
            logger.warning(f"Failed to get Apollo pricing for {action}: {e}")

        # Default: no credits, no cost
        return 0, 0.0

    async def check_credits(self, company_id: str, credits_needed: int = 1) -> bool:
        """
        Check if company has enough credits.

        Args:
            company_id: The company's UUID.
            credits_needed: Number of credits required.

        Returns:
            True if credits are available, False otherwise.
        """
        config = await self.get_config(company_id)
        if not config:
            return False

        # BYOK customers manage their own credits
        if config["mode"] == "byok":
            return True

        # LuminOne-provided: check allocation
        credits_used = config.get("credits_used_this_cycle", 0)
        credit_limit = config.get("monthly_credit_limit", 500)
        remaining = credit_limit - credits_used

        return remaining >= credits_needed

    async def consume_credits(
        self,
        company_id: str,
        user_id: str,
        action_type: str,
        credits: int,
        target_company: Optional[str] = None,
        target_person: Optional[str] = None,
        mode: str = "luminone_provided",
        status: str = "success",
    ) -> bool:
        """
        Log credit consumption with dual-write to both credit log and usage tracking.

        Args:
            company_id: The company's UUID.
            user_id: The user's UUID.
            action_type: The Apollo action (e.g., 'people_enrich_email').
            credits: Number of credits consumed.
            target_company: Company being researched (optional).
            target_person: Person being enriched (optional).
            mode: 'byok' or 'luminone_provided'.
            status: 'success', 'not_found', or 'error'.

        Returns:
            True if logging succeeded, False otherwise.
        """
        try:
            # Get pricing snapshot at call time
            _, cost_cents_per_credit = await self.get_pricing(action_type)
            cost_cents = credits * cost_cents_per_credit

            # Get full pricing snapshot for audit
            pricing_result = (
                self._db.table("vendor_api_pricing")
                .select("*")
                .eq("vendor", "apollo")
                .eq("action", action_type)
                .maybe_single()
                .execute()
            )
            pricing_snapshot = pricing_result.data if pricing_result else {}

            # 1. Write to apollo_credit_log (customer-facing credits)
            (
                self._db.table("apollo_credit_log")
                .insert(
                    {
                        "company_id": company_id,
                        "user_id": user_id,
                        "action_type": action_type,
                        "credits_consumed": credits,
                        "cost_cents": cost_cents,
                        "target_company": target_company,
                        "target_person": target_person,
                        "apollo_response_status": status,
                        "mode": mode,
                        "pricing_snapshot": pricing_snapshot,
                    }
                )
                .execute()
            )

            # 2. Write to api_usage_tracking (internal COGS tracking)
            self._db.rpc(
                "increment_api_usage",
                {
                    "p_user_id": user_id,
                    "p_date": date.today().isoformat(),
                    "p_api_type": "apollo",
                    "p_calls": 1,
                    "p_errors": 0 if status == "success" else 1,
                    "p_cost_cents": cost_cents,
                },
            ).execute()

            # 3. Update credit counter (only for luminone_provided mode)
            if mode == "luminone_provided" and credits > 0:
                self._db.rpc(
                    "increment_apollo_credits",
                    {"p_company_id": company_id, "p_credits": credits},
                ).execute()

            logger.debug(
                f"Apollo credits consumed: company={company_id}, action={action_type}, "
                f"credits={credits}, cost_cents={cost_cents}, mode={mode}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to log Apollo credits: {e}")
            return False

    async def get_usage_summary(
        self, company_id: str
    ) -> dict[str, Any]:
        """
        Get credit usage summary for a company.

        Credits used is derived from apollo_credit_log (source of truth),
        NOT from the credits_used_this_cycle cache on apollo_config.

        Args:
            company_id: The company's UUID.

        Returns:
            Dict with limit, used, remaining, reset_date, mode.
        """
        config = await self.get_config(company_id)
        if not config:
            return {
                "configured": False,
                "limit": 0,
                "used": 0,
                "remaining": 0,
                "reset_date": None,
                "mode": "unconfigured",
            }

        limit = config.get("monthly_credit_limit", 0)
        reset_date = config.get("cycle_reset_date")
        mode = config.get("mode", "luminone_provided")

        # Derive credits_used from apollo_credit_log (source of truth)
        actual_used = await self._sum_credits_from_log(company_id, reset_date)

        return {
            "configured": True,
            "limit": limit,
            "used": actual_used,
            "remaining": max(0, limit - actual_used),
            "reset_date": reset_date,
            "mode": mode,
            "is_active": config.get("is_active", True),
        }

    async def _sum_credits_from_log(
        self, company_id: str, cycle_reset_date: str | None
    ) -> int:
        """
        Sum credits consumed from apollo_credit_log for the current billing cycle.

        This is the source of truth for credit usage. The credits_used_this_cycle
        column on apollo_config is just a cache.

        Args:
            company_id: The company's UUID.
            cycle_reset_date: The end/reset date of the current cycle.

        Returns:
            Total credits consumed in the current billing cycle.
        """
        try:
            from dateutil.relativedelta import relativedelta

            # Calculate cycle start from reset date
            if cycle_reset_date:
                if isinstance(cycle_reset_date, str):
                    reset_dt = datetime.fromisoformat(cycle_reset_date.replace("Z", "+00:00"))
                else:
                    reset_dt = cycle_reset_date
                # cycle_reset_date is the NEXT reset (1st of next month)
                # so cycle_start is 1st of current month
                cycle_start = (reset_dt - relativedelta(months=1)).date()
            else:
                # Default: 1st of current month
                cycle_start = date.today().replace(day=1)

            result = (
                self._db.table("apollo_credit_log")
                .select("credits_consumed")
                .eq("company_id", company_id)
                .gte("created_at", cycle_start.isoformat())
                .execute()
            )

            if result.data:
                return sum(row.get("credits_consumed", 0) for row in result.data)
            return 0

        except Exception as e:
            logger.warning(
                "Failed to sum credits from log for company %s, falling back to cache: %s",
                company_id, e,
            )
            # Fallback to cache if log query fails
            config = await self.get_config(company_id)
            return config.get("credits_used_this_cycle", 0) if config else 0

    async def update_config(
        self,
        company_id: str,
        mode: Optional[str] = None,
        api_key: Optional[str] = None,
        monthly_credit_limit: Optional[int] = None,
        is_active: Optional[bool] = None,
        auto_enrich_on_approval: Optional[bool] = None,
        default_reveal_emails: Optional[bool] = None,
        default_reveal_phones: Optional[bool] = None,
    ) -> bool:
        """
        Update Apollo configuration for a company.

        Args:
            company_id: The company's UUID.
            mode: 'byok' or 'luminone_provided'.
            api_key: Customer's API key (will be encrypted for BYOK mode).
            monthly_credit_limit: Credit limit for LuminOne-provided mode.
            is_active: Whether Apollo is enabled.
            auto_enrich_on_approval: Auto-enrich leads on approval.
            default_reveal_emails: Default to revealing emails.
            default_reveal_phones: Default to revealing phones.

        Returns:
            True if update succeeded, False otherwise.
        """
        try:
            updates: dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}

            if mode is not None:
                updates["mode"] = mode

            if api_key is not None:
                encrypted = encrypt_api_key(api_key)
                if encrypted:
                    updates["encrypted_api_key"] = encrypted
                    updates["customer_api_key"] = None  # Clear legacy field
                else:
                    logger.error("Failed to encrypt API key - encryption not configured")
                    return False

            if monthly_credit_limit is not None:
                updates["monthly_credit_limit"] = monthly_credit_limit

            if is_active is not None:
                updates["is_active"] = is_active

            if auto_enrich_on_approval is not None:
                updates["auto_enrich_on_approval"] = auto_enrich_on_approval

            if default_reveal_emails is not None:
                updates["default_reveal_emails"] = default_reveal_emails

            if default_reveal_phones is not None:
                updates["default_reveal_phones"] = default_reveal_phones

            result = (
                self._db.table("apollo_config")
                .update(updates)
                .eq("company_id", company_id)
                .execute()
            )

            return bool(result.data)
        except Exception as e:
            logger.error(f"Failed to update Apollo config: {e}")
            return False

    async def reset_monthly_credits(self) -> int:
        """
        Reset monthly credits for all LuminOne-provided accounts.

        Called by scheduler on 1st of each month.

        Returns:
            Number of accounts reset.
        """
        try:
            # Calculate next reset date (1st of next month)
            today = date.today()
            if today.month == 12:
                next_reset = date(today.year + 1, 1, 1)
            else:
                next_reset = date(today.year, today.month + 1, 1)

            result = (
                self._db.table("apollo_config")
                .update(
                    {
                        "credits_used_this_cycle": 0,
                        "cycle_reset_date": next_reset.isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("mode", "luminone_provided")
                .execute()
            )

            count = len(result.data) if result.data else 0
            logger.info(f"Reset Apollo credits for {count} LuminOne-provided accounts")
            return count

        except Exception as e:
            logger.error(f"Failed to reset Apollo monthly credits: {e}")
            return 0
