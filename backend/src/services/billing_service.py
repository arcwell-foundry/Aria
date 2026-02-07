"""Billing & Subscription Management Service (US-928).

Provides functionality for:
- Stripe customer management
- Checkout session creation
- Customer portal access
- Subscription status tracking
- Invoice retrieval
- Webhook handling
"""

import logging
from datetime import UTC, datetime
from typing import Any

import stripe

from src.core.config import settings
from src.core.exceptions import ARIAException, NotFoundError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class BillingError(ARIAException):
    """Billing operation error."""

    def __init__(self, message: str = "Billing operation failed") -> None:
        """Initialize billing error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=message,
            code="BILLING_ERROR",
            status_code=500,
        )


class BillingService:
    """Service for billing and subscription operations using Stripe."""

    # Subscription status constants
    STATUS_TRIAL = "trial"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_INCOMPLETE = "incomplete"

    # All valid statuses
    VALID_STATUSES = {
        STATUS_TRIAL,
        STATUS_ACTIVE,
        STATUS_PAST_DUE,
        STATUS_CANCELED,
        STATUS_INCOMPLETE,
    }

    def __init__(self) -> None:
        """Initialize BillingService with Stripe configuration."""
        self._stripe_key = settings.STRIPE_SECRET_KEY.get_secret_value()
        if not self._stripe_key:
            logger.warning("STRIPE_SECRET_KEY not configured")
        else:
            stripe.api_key = self._stripe_key

    def _is_configured(self) -> bool:
        """Check if Stripe is properly configured.

        Returns:
            True if Stripe key is configured.
        """
        return bool(self._stripe_key)

    async def get_or_create_customer(
        self, company_id: str, admin_email: str, company_name: str | None = None
    ) -> str:
        """Get or create a Stripe customer for the company.

        Args:
            company_id: The company's UUID.
            admin_email: Email of the company admin.
            company_name: Optional company name for Stripe customer.

        Returns:
            Stripe customer ID.

        Raises:
            BillingError: If Stripe operation fails.
            NotFoundError: If company not found.
        """
        if not self._is_configured():
            raise BillingError("Stripe is not configured")

        try:
            # First, check if company already has a Stripe customer ID
            client = SupabaseClient.get_client()
            company_response = (
                client.table("companies").select("*").eq("id", company_id).single().execute()
            )

            if not company_response.data:
                raise NotFoundError("Company", company_id)

            company = company_response.data
            existing_customer_id = company.get("stripe_customer_id")

            if existing_customer_id:
                logger.info(f"Found existing Stripe customer: {existing_customer_id}")
                return existing_customer_id

            # Create new Stripe customer
            customer_params: dict[str, Any] = {
                "email": admin_email,
                "metadata": {"company_id": company_id},
            }

            if company_name:
                customer_params["name"] = company_name

            customer = stripe.Customer.create(**customer_params)
            customer_id = customer.id

            # Store customer ID in companies table
            (
                client.table("companies")
                .update({"stripe_customer_id": customer_id})
                .eq("id", company_id)
                .execute()
            )

            logger.info(f"Created Stripe customer {customer_id} for company {company_id}")
            return customer_id

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error creating Stripe customer", extra={"company_id": company_id})
            raise BillingError(f"Failed to create Stripe customer: {e}") from e

    async def create_checkout_session(
        self,
        company_id: str,
        admin_email: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> str:
        """Create a Stripe Checkout session for subscription.

        Args:
            company_id: The company's UUID.
            admin_email: Email of the company admin.
            success_url: Optional URL to redirect to after success.
            cancel_url: Optional URL to redirect to after cancellation.

        Returns:
            Stripe Checkout URL.

        Raises:
            BillingError: If checkout session creation fails.
        """
        if not self._is_configured():
            raise BillingError("Stripe is not configured")

        try:
            customer_id = await self.get_or_create_customer(company_id, admin_email)

            # Use configured URLs or defaults
            base_url = settings.APP_URL.rstrip("/")
            success_url = success_url or f"{base_url}/admin/billing?success=true"
            cancel_url = cancel_url or f"{base_url}/admin/billing?canceled=true"

            # Get price ID from settings or use a test price
            price_id = settings.STRIPE_PRICE_ID
            if not price_id:
                logger.warning("STRIPE_PRICE_ID not configured, using mode setup")
                # Create a setup session without immediate payment
                session = stripe.checkout.Session.create(
                    customer=customer_id,
                    mode="setup",
                    success_url=success_url,
                    cancel_url=cancel_url,
                    metadata={"company_id": company_id},
                )
            else:
                session = stripe.checkout.Session.create(
                    customer=customer_id,
                    mode="subscription",
                    payment_method_types=["card"],
                    line_items=[{"price": price_id, "quantity": 1}],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    metadata={"company_id": company_id},
                )

            logger.info(f"Created checkout session {session.id} for company {company_id}")
            return session.url

        except Exception as e:
            logger.exception("Error creating checkout session", extra={"company_id": company_id})
            raise BillingError(f"Failed to create checkout session: {e}") from e

    async def create_portal_session(
        self,
        company_id: str,
        return_url: str | None = None,
    ) -> str:
        """Create a Stripe Customer Portal session.

        Args:
            company_id: The company's UUID.
            return_url: Optional URL to redirect to after portal session.

        Returns:
            Stripe Customer Portal URL.

        Raises:
            BillingError: If portal session creation fails.
        """
        if not self._is_configured():
            raise BillingError("Stripe is not configured")

        try:
            # Get company's Stripe customer ID
            client = SupabaseClient.get_client()
            company_response = (
                client.table("companies").select("*").eq("id", company_id).single().execute()
            )

            if not company_response.data:
                raise NotFoundError("Company", company_id)

            company = company_response.data
            customer_id = company.get("stripe_customer_id")

            if not customer_id:
                raise BillingError("No Stripe customer found for this company")

            # Use configured return URL or default
            base_url = settings.APP_URL.rstrip("/")
            return_url = return_url or f"{base_url}/admin/billing"

            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            logger.info(f"Created portal session for company {company_id}")
            return session.url

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error creating portal session", extra={"company_id": company_id})
            raise BillingError(f"Failed to create portal session: {e}") from e

    async def get_subscription_status(self, company_id: str) -> dict[str, Any]:
        """Get subscription status for a company.

        Args:
            company_id: The company's UUID.

        Returns:
            Dictionary with subscription details:
                - status: Current subscription status
                - plan: Plan name/ID
                - current_period_end: ISO timestamp of period end
                - cancel_at_period_end: Boolean
                - seats_used: Number of active seats

        Raises:
            NotFoundError: If company not found.
            BillingError: If status retrieval fails.
        """
        try:
            client = SupabaseClient.get_client()
            company_response = (
                client.table("companies").select("*").eq("id", company_id).single().execute()
            )

            if not company_response.data:
                raise NotFoundError("Company", company_id)

            company = company_response.data
            customer_id = company.get("stripe_customer_id")
            subscription_status = company.get("subscription_status", self.STATUS_TRIAL)
            metadata = company.get("subscription_metadata", {})

            # Get seats count from user_profiles
            seats_response = (
                client.table("user_profiles")
                .select("id", count="exact")
                .eq("company_id", company_id)
                .execute()
            )
            seats_used = seats_response.count if seats_response.count else 0

            result: dict[str, Any] = {
                "status": subscription_status,
                "plan": metadata.get("plan", "ARIA Annual"),
                "current_period_end": metadata.get("current_period_end"),
                "cancel_at_period_end": metadata.get("cancel_at_period_end", False),
                "seats_used": seats_used,
            }

            # If we have a Stripe customer and are configured, fetch live data
            if customer_id and self._is_configured():
                try:
                    subscriptions = stripe.Subscription.list(
                        customer=customer_id, status="active", limit=1
                    )
                    if subscriptions.data:
                        sub = subscriptions.data[0]
                        result.update({
                            "status": sub.status,
                            "plan": sub.items.data[0].price.nickname if sub.items.data else "ARIA Annual",
                            "current_period_end": datetime.fromtimestamp(
                                sub.current_period_end, tz=UTC
                            ).isoformat(),
                            "cancel_at_period_end": sub.cancel_at_period_end,
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch live subscription data: {e}")

            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error fetching subscription status", extra={"company_id": company_id})
            raise BillingError(f"Failed to fetch subscription status: {e}") from e

    async def get_invoices(
        self, company_id: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        """Get invoice history for a company.

        Args:
            company_id: The company's UUID.
            limit: Maximum number of invoices to return.

        Returns:
            List of invoice dictionaries with:
                - id: Invoice ID
                - amount: Amount in dollars (not cents)
                - currency: Currency code (e.g., "usd")
                - status: Invoice status
                - date: ISO date string
                - pdf_url: URL to download PDF

        Raises:
            NotFoundError: If company not found.
            BillingError: If invoice retrieval fails.
        """
        if not self._is_configured():
            # Return empty list if Stripe not configured
            return []

        try:
            # Get company's Stripe customer ID
            client = SupabaseClient.get_client()
            company_response = (
                client.table("companies").select("*").eq("id", company_id).single().execute()
            )

            if not company_response.data:
                raise NotFoundError("Company", company_id)

            company = company_response.data
            customer_id = company.get("stripe_customer_id")

            if not customer_id:
                return []

            invoices = stripe.Invoice.list(customer=customer_id, limit=limit)

            result = []
            for invoice in invoices.data:
                result.append({
                    "id": invoice.id,
                    "amount": (invoice.total or 0) / 100,  # Convert cents to dollars
                    "currency": invoice.currency,
                    "status": invoice.status,
                    "date": datetime.fromtimestamp(
                        invoice.created, tz=UTC
                    ).isoformat()
                    if invoice.created
                    else None,
                    "pdf_url": invoice.invoice_pdf,
                })

            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error fetching invoices", extra={"company_id": company_id})
            raise BillingError(f"Failed to fetch invoices: {e}") from e

    async def handle_webhook(self, payload: bytes, sig_header: str) -> None:
        """Handle Stripe webhook events.

        Args:
            payload: Raw webhook payload.
            sig_header: Stripe signature header.

        Raises:
            BillingError: If webhook verification or handling fails.
        """
        if not self._is_configured():
            raise BillingError("Stripe is not configured")

        webhook_secret = settings.STRIPE_WEBHOOK_SECRET.get_secret_value()
        if not webhook_secret:
            logger.warning("STRIPE_WEBHOOK_SECRET not configured")
            raise BillingError("Webhook secret not configured")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError as e:
            raise BillingError(f"Invalid webhook payload: {e}") from e
        except stripe.error.SignatureVerificationError as e:
            raise BillingError(f"Invalid webhook signature: {e}") from e

        try:
            await self._process_webhook_event(event)
        except Exception as e:
            logger.exception("Error processing webhook event", extra={"event_type": event.type})
            raise BillingError(f"Failed to process webhook: {e}") from e

    async def _process_webhook_event(self, event: stripe.Event) -> None:
        """Process a verified webhook event.

        Args:
            event: Stripe event object.
        """
        event_type = event.type
        data = event.data.object

        logger.info(f"Processing webhook event: {event_type}")

        if event_type == "invoice.payment_succeeded":
            await self._handle_payment_succeeded(data)
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(data)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(data)
        elif event_type == "checkout.session.completed":
            await self._handle_checkout_completed(data)
        else:
            logger.debug(f"Unhandled webhook event type: {event_type}")

    async def _handle_payment_succeeded(self, invoice: stripe.Invoice) -> None:
        """Handle successful payment webhook.

        Args:
            invoice: Stripe invoice object.
        """
        customer_id = invoice.customer
        await self._update_subscription_status(customer_id, self.STATUS_ACTIVE, invoice)

        # Send payment receipt email
        try:
            from src.services.email_service import EmailService
            email_service = EmailService()

            # Fetch company admin email
            admin_email = await self._get_company_admin_email(customer_id)
            if admin_email:
                # Get amount and date from invoice
                amount = invoice.total or 0
                date = datetime.fromtimestamp(invoice.created, tz=UTC).isoformat() if invoice.created else ""
                await email_service.send_payment_receipt(admin_email, amount, date)
        except Exception as email_error:
            logger.warning(
                "Failed to send payment receipt email",
                extra={"customer_id": customer_id, "error": str(email_error)},
            )

    async def _handle_payment_failed(self, invoice: stripe.Invoice) -> None:
        """Handle failed payment webhook.

        Args:
            invoice: Stripe invoice object.
        """
        customer_id = invoice.customer
        await self._update_subscription_status(customer_id, self.STATUS_PAST_DUE, invoice)

        # Send payment failed email
        try:
            from src.services.email_service import EmailService
            email_service = EmailService()

            # Fetch company admin email and name
            admin_info = await self._get_company_admin_info(customer_id)
            if admin_info:
                await email_service.send_payment_failed(
                    admin_info["email"], admin_info["full_name"]
                )
        except Exception as email_error:
            logger.warning(
                "Failed to send payment failed email",
                extra={"customer_id": customer_id, "error": str(email_error)},
            )

    async def _handle_subscription_deleted(self, subscription: stripe.Subscription) -> None:
        """Handle subscription deletion webhook.

        Args:
            subscription: Stripe subscription object.
        """
        customer_id = subscription.customer
        await self._update_subscription_status(
            customer_id, self.STATUS_CANCELED, subscription
        )

    async def _handle_checkout_completed(self, session: stripe.checkout.Session) -> None:
        """Handle checkout completion webhook.

        Args:
            session: Stripe checkout session object.
        """
        customer_id = session.customer
        if session.subscription:
            # Fetch subscription details
            subscription = stripe.Subscription.retrieve(session.subscription)
            await self._update_subscription_status(
                customer_id, self.STATUS_ACTIVE, subscription
            )

    async def _update_subscription_status(
        self,
        customer_id: str,
        status: str,
        source: stripe.Invoice | stripe.Subscription,
    ) -> None:
        """Update subscription status in database.

        Args:
            customer_id: Stripe customer ID.
            status: New subscription status.
            source: Stripe object with additional details.
        """
        try:
            client = SupabaseClient.get_client()

            # Find company by stripe_customer_id
            company_response = (
                client.table("companies")
                .select("id")
                .eq("stripe_customer_id", customer_id)
                .single()
                .execute()
            )

            if not company_response.data:
                logger.warning(f"No company found for Stripe customer {customer_id}")
                return

            company_id = company_response.data["id"]

            # Build metadata
            metadata = {}
            if hasattr(source, "current_period_end") and source.current_period_end:
                metadata["current_period_end"] = datetime.fromtimestamp(
                    source.current_period_end, tz=UTC
                ).isoformat()

            if hasattr(source, "cancel_at_period_end"):
                metadata["cancel_at_period_end"] = source.cancel_at_period_end

            if hasattr(source, "items") and source.items.data:
                price = source.items.data[0].price
                metadata["plan"] = price.nickname or price.id

            update_data: dict[str, Any] = {
                "subscription_status": status,
                "subscription_metadata": metadata,
            }

            (
                client.table("companies")
                .update(update_data)
                .eq("stripe_customer_id", customer_id)
                .execute()
            )

            logger.info(
                f"Updated subscription status to {status} for company {company_id}",
                extra={"company_id": company_id, "status": status},
            )

        except Exception:
            logger.exception(
                "Error updating subscription status",
                extra={"customer_id": customer_id, "status": status},
            )

    async def _get_company_admin_email(self, customer_id: str) -> str | None:
        """Get the email of a company admin for billing notifications.

        Args:
            customer_id: Stripe customer ID.

        Returns:
            Admin email address or None if not found.
        """
        try:
            client = SupabaseClient.get_client()

            # Find company by stripe_customer_id
            company_response = (
                client.table("companies")
                .select("id")
                .eq("stripe_customer_id", customer_id)
                .single()
                .execute()
            )

            if not company_response.data:
                logger.warning(f"No company found for Stripe customer {customer_id}")
                return None

            company_id = company_response.data["id"]

            # Get first admin user for the company
            user_response = (
                client.table("user_profiles")
                .select("id", "full_name")
                .eq("company_id", company_id)
                .eq("role", "admin")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )

            if user_response.data and len(user_response.data) > 0:
                # Get email from auth.users via admin API
                user_id = user_response.data[0]["id"]
                user_data = client.auth.admin.get_user_by_id(user_id)
                if user_data and user_data.user and user_data.user.email:
                    return user_data.user.email

            return None

        except Exception:
            logger.exception(
                "Error fetching company admin email",
                extra={"customer_id": customer_id},
            )
            return None

    async def _get_company_admin_info(self, customer_id: str) -> dict[str, str] | None:
        """Get info of a company admin for billing notifications.

        Args:
            customer_id: Stripe customer ID.

        Returns:
            Dictionary with email and full_name or None if not found.
        """
        try:
            client = SupabaseClient.get_client()

            # Find company by stripe_customer_id
            company_response = (
                client.table("companies")
                .select("id")
                .eq("stripe_customer_id", customer_id)
                .single()
                .execute()
            )

            if not company_response.data:
                logger.warning(f"No company found for Stripe customer {customer_id}")
                return None

            company_id = company_response.data["id"]

            # Get first admin user for the company
            user_response = (
                client.table("user_profiles")
                .select("id", "full_name")
                .eq("company_id", company_id)
                .eq("role", "admin")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )

            if user_response.data and len(user_response.data) > 0:
                user_profile = user_response.data[0]
                user_id = user_profile["id"]

                # Get email from auth.users via admin API
                user_data = client.auth.admin.get_user_by_id(user_id)
                if user_data and user_data.user and user_data.user.email:
                    return {
                        "email": user_data.user.email,
                        "full_name": user_profile.get("full_name", "Admin"),
                    }

            return None

        except Exception:
            logger.exception(
                "Error fetching company admin info",
                extra={"customer_id": customer_id},
            )
            return None
