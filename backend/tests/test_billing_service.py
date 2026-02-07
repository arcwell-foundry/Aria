"""Tests for Billing & Subscription Management Service (US-928)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.services.billing_service import BillingService, BillingError
from src.core.exceptions import NotFoundError


@pytest.fixture
def billing_service():
    """Create a BillingService instance."""
    service = BillingService()
    service._stripe_key = "sk_test_test_key"  # Set mock key for tests
    return service


@pytest.fixture
def mock_stripe():
    """Mock Stripe module."""
    with patch("src.services.billing_service.stripe") as mock:
        yield mock


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    with patch("src.services.billing_service.SupabaseClient") as mock:
        yield mock


class TestBillingService:
    """Test suite for BillingService."""

    def test_is_configured_with_key(self, billing_service):
        """Test service checks configuration correctly when key is set."""
        billing_service._stripe_key = "sk_test_test_key"
        assert billing_service._is_configured() is True

    def test_is_configured_without_key(self, billing_service):
        """Test service checks configuration correctly when key is not set."""
        billing_service._stripe_key = ""
        assert billing_service._is_configured() is False

    @pytest.mark.asyncio
    async def test_get_or_create_customer_existing(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test getting existing Stripe customer."""
        company_id = "company-123"
        admin_email = "admin@example.com"
        customer_id = "cus_existing123"

        # Mock Supabase response - company already has stripe_customer_id
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": company_id,
                "stripe_customer_id": customer_id,
                "name": "Test Company",
            }
        )

        result = await billing_service.get_or_create_customer(
            company_id, admin_email
        )

        assert result == customer_id
        # Should not create new customer
        mock_stripe.Customer.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_customer_new(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test creating new Stripe customer."""
        company_id = "company-456"
        admin_email = "admin@example.com"
        company_name = "New Company"
        customer_id = "cus_new123"

        # Mock Supabase response - company has no stripe_customer_id
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": company_id, "stripe_customer_id": None, "name": company_name}
        )

        # Mock Stripe customer creation
        mock_customer = MagicMock()
        mock_customer.id = customer_id
        mock_stripe.Customer.create.return_value = mock_customer

        # Mock Supabase update
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock()
        )

        result = await billing_service.get_or_create_customer(
            company_id, admin_email, company_name
        )

        assert result == customer_id
        mock_stripe.Customer.create.assert_called_once_with(
            email=admin_email,
            name=company_name,
            metadata={"company_id": company_id},
        )
        mock_client.table.return_value.update.assert_called_once()
        mock_client.table.return_value.update.return_value.eq.assert_called_once_with(
            "id", company_id
        )

    @pytest.mark.asyncio
    async def test_get_or_create_customer_not_found(
        self, billing_service, mock_supabase
    ):
        """Test error when company not found."""
        company_id = "company-missing"
        admin_email = "admin@example.com"

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        with pytest.raises(NotFoundError):
            await billing_service.get_or_create_customer(company_id, admin_email)

    @pytest.mark.asyncio
    async def test_create_checkout_session(
        self, billing_service, mock_stripe
    ):
        """Test creating checkout session."""
        company_id = "company-123"
        admin_email = "admin@example.com"
        checkout_url = "https://checkout.stripe.com/session"

        # Mock get_or_create_customer
        billing_service.get_or_create_customer = AsyncMock(return_value="cus_123")

        # Mock Stripe checkout session creation
        mock_session = MagicMock()
        mock_session.url = checkout_url
        mock_session.id = "cs_test_123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        result = await billing_service.create_checkout_session(
            company_id, admin_email
        )

        assert result == checkout_url
        mock_stripe.checkout.Session.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_portal_session(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test creating portal session."""
        company_id = "company-123"
        portal_url = "https://portal.stripe.com/session"

        # Mock Supabase response
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": company_id, "stripe_customer_id": "cus_123"}
        )

        # Mock Stripe portal session creation
        mock_session = MagicMock()
        mock_session.url = portal_url
        mock_stripe.billing_portal.Session.create.return_value = mock_session

        result = await billing_service.create_portal_session(company_id)

        assert result == portal_url
        mock_stripe.billing_portal.Session.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_subscription_status(
        self, billing_service, mock_supabase
    ):
        """Test getting subscription status."""
        company_id = "company-123"

        # Mock Supabase responses
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        # Company response
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": company_id,
                "stripe_customer_id": "cus_123",
                "subscription_status": "active",
                "subscription_metadata": {
                    "plan": "ARIA Annual",
                    "current_period_end": "2024-12-31T23:59:59+00:00",
                    "cancel_at_period_end": False,
                },
            }
        )

        # Seats count response
        mock_seats_response = MagicMock()
        mock_seats_response.count = 5
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_seats_response

        result = await billing_service.get_subscription_status(company_id)

        assert result["status"] == "active"
        assert result["plan"] == "ARIA Annual"
        assert result["seats_used"] == 5
        assert result["cancel_at_period_end"] is False

    @pytest.mark.asyncio
    async def test_get_subscription_status_no_company(
        self, billing_service, mock_supabase
    ):
        """Test getting subscription status for non-existent company."""
        company_id = "company-missing"

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        with pytest.raises(NotFoundError):
            await billing_service.get_subscription_status(company_id)

    @pytest.mark.asyncio
    async def test_get_invoices(self, billing_service, mock_supabase, mock_stripe):
        """Test getting invoice history."""
        company_id = "company-123"

        # Mock Supabase response
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": company_id,
                "stripe_customer_id": "cus_123",
            }
        )

        # Mock Stripe invoice list
        mock_invoice1 = MagicMock()
        mock_invoice1.id = "in_123"
        mock_invoice1.total = 200000  # $2000.00 in cents
        mock_invoice1.currency = "usd"
        mock_invoice1.status = "paid"
        mock_invoice1.created = 1704067200  # Timestamp
        mock_invoice1.invoice_pdf = "https://example.com/invoice.pdf"

        mock_invoice2 = MagicMock()
        mock_invoice2.id = "in_456"
        mock_invoice2.total = 10000  # $100.00 in cents
        mock_invoice2.currency = "usd"
        mock_invoice2.status = "paid"
        mock_invoice2.created = 1701388800
        mock_invoice2.invoice_pdf = "https://example.com/invoice2.pdf"

        mock_stripe.Invoice.list.return_value = MagicMock(data=[mock_invoice1, mock_invoice2])

        result = await billing_service.get_invoices(company_id, limit=12)

        assert len(result) == 2
        assert result[0]["id"] == "in_123"
        assert result[0]["amount"] == 2000.00  # Converted to dollars
        assert result[0]["currency"] == "usd"
        assert result[0]["status"] == "paid"
        assert result[1]["amount"] == 100.00  # Converted to dollars

    @pytest.mark.asyncio
    async def test_get_invoices_no_customer(self, billing_service, mock_supabase):
        """Test getting invoices when company has no Stripe customer."""
        company_id = "company-123"

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": company_id, "stripe_customer_id": None}
        )

        result = await billing_service.get_invoices(company_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_handle_webhook_payment_succeeded(
        self, billing_service, mock_stripe
    ):
        """Test handling payment succeeded webhook."""
        payload = b"test_payload"
        sig_header = "t=123,v1=abc123"

        # Mock settings to provide webhook secret
        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_WEBHOOK_SECRET.get_secret_value.return_value = "whsec_test"

            mock_event = MagicMock()
            mock_event.type = "invoice.payment_succeeded"
            mock_invoice = MagicMock()
            mock_invoice.customer = "cus_123"
            mock_event.data.object = mock_invoice

            mock_stripe.Webhook.construct_event.return_value = mock_event

            # Mock the internal update method
            billing_service._update_subscription_status = AsyncMock()

            await billing_service.handle_webhook(payload, sig_header)

        mock_stripe.Webhook.construct_event.assert_called_once()
        billing_service._update_subscription_status.assert_called_once_with(
            "cus_123", "active", mock_invoice
        )

    @pytest.mark.asyncio
    async def test_handle_webhook_payment_failed(
        self, billing_service, mock_stripe
    ):
        """Test handling payment failed webhook."""
        payload = b"test_payload"
        sig_header = "t=123,v1=abc123"

        # Mock settings to provide webhook secret
        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_WEBHOOK_SECRET.get_secret_value.return_value = "whsec_test"

            mock_event = MagicMock()
            mock_event.type = "invoice.payment_failed"
            mock_invoice = MagicMock()
            mock_invoice.customer = "cus_123"
            mock_event.data.object = mock_invoice

            mock_stripe.Webhook.construct_event.return_value = mock_event
            billing_service._update_subscription_status = AsyncMock()

            await billing_service.handle_webhook(payload, sig_header)

            billing_service._update_subscription_status.assert_called_once_with(
                "cus_123", "past_due", mock_invoice
            )

    @pytest.mark.asyncio
    async def test_handle_webhook_subscription_deleted(
        self, billing_service, mock_stripe
    ):
        """Test handling subscription deleted webhook."""
        payload = b"test_payload"
        sig_header = "t=123,v1=abc123"

        # Mock settings to provide webhook secret
        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_WEBHOOK_SECRET.get_secret_value.return_value = "whsec_test"

            mock_event = MagicMock()
            mock_event.type = "customer.subscription.deleted"
            mock_subscription = MagicMock()
            mock_subscription.customer = "cus_123"
            mock_event.data.object = mock_subscription

            mock_stripe.Webhook.construct_event.return_value = mock_event
            billing_service._update_subscription_status = AsyncMock()

            await billing_service.handle_webhook(payload, sig_header)

            billing_service._update_subscription_status.assert_called_once_with(
                "cus_123", "canceled", mock_subscription
            )

    @pytest.mark.asyncio
    async def test_handle_webhook_invalid_signature(self, billing_service, mock_stripe):
        """Test webhook with invalid signature."""
        payload = b"test_payload"
        sig_header = "invalid_sig"

        mock_stripe.Webhook.construct_event.side_effect = Exception("Invalid signature")
        mock_stripe.error.SignatureVerificationError = Exception

        with pytest.raises(BillingError):
            await billing_service.handle_webhook(payload, sig_header)


class TestInvoiceFormatting:
    """Test invoice data formatting."""

    @pytest.mark.asyncio
    async def test_invoice_cents_to_dollars_conversion(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test that invoice amounts are converted from cents to dollars."""
        company_id = "company-123"

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": company_id, "stripe_customer_id": "cus_123"}
        )

        # Create invoice with various amounts
        mock_invoice = MagicMock()
        mock_invoice.id = "in_test"
        mock_invoice.total = 19999  # Should become $199.99
        mock_invoice.currency = "usd"
        mock_invoice.status = "paid"
        mock_invoice.created = 1704067200
        mock_invoice.invoice_pdf = "https://example.com/invoice.pdf"

        mock_stripe.Invoice.list.return_value = MagicMock(data=[mock_invoice])

        result = await billing_service.get_invoices(company_id)

        assert result[0]["amount"] == 199.99


class TestSubscriptionStatusParsing:
    """Test subscription status parsing from Stripe."""

    @pytest.mark.asyncio
    async def test_status_parsing_active_subscription(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test parsing active subscription from Stripe."""
        company_id = "company-123"

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": company_id,
                "stripe_customer_id": "cus_123",
                "subscription_status": "trial",  # Will be overridden by Stripe data
                "subscription_metadata": {},
            }
        )

        # Mock seats response
        mock_seats_response = MagicMock()
        mock_seats_response.count = 3
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_seats_response

        # Mock active subscription from Stripe
        mock_subscription = MagicMock()
        mock_subscription.status = "active"
        mock_subscription.current_period_end = 1735689600  # 2025-01-01
        mock_subscription.cancel_at_period_end = False

        mock_price = MagicMock()
        mock_price.nickname = "ARIA Annual"

        mock_item = MagicMock()
        mock_item.price = mock_price
        mock_subscription.items = MagicMock()
        mock_subscription.items.data = [mock_item]

        mock_stripe.Subscription.list.return_value = MagicMock(data=[mock_subscription])

        result = await billing_service.get_subscription_status(company_id)

        # Should use live Stripe data instead of database
        assert result["status"] == "active"
        assert result["plan"] == "ARIA Annual"
        assert result["cancel_at_period_end"] is False
        assert result["seats_used"] == 3


class TestBillingEmailNotifications:
    """Test suite for email notifications on billing events."""

    @pytest.mark.asyncio
    async def test_payment_success_sends_email(self, billing_service, mock_supabase):
        """Test that payment success sends an email receipt."""
        mock_client = MagicMock()

        # Mock _update_subscription_status to avoid database calls
        billing_service._update_subscription_status = AsyncMock()

        # Create separate mock chains for companies and user_profiles queries
        # Companies query
        mock_companies_table = MagicMock()
        mock_companies_execute = MagicMock()
        mock_companies_execute.data = {"id": "company-123", "name": "Test Company"}
        mock_companies_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_companies_execute

        # User profiles query
        mock_user_profiles_table = MagicMock()
        mock_user_execute = MagicMock()
        mock_user_execute.data = [{"id": "admin-123", "full_name": "Admin User"}]
        mock_user_profiles_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = mock_user_execute

        # Make table() return different mocks based on argument
        def table_side_effect(table_name):
            if table_name == "companies":
                return mock_companies_table
            elif table_name == "user_profiles":
                return mock_user_profiles_table
            return MagicMock()

        mock_client.table.side_effect = table_side_effect

        # Mock auth admin for getting user email
        mock_auth_admin = MagicMock()
        mock_user_data = MagicMock()
        mock_user_data.user.email = "admin@example.com"
        mock_auth_admin.get_user_by_id.return_value = mock_user_data
        mock_client.auth.admin = mock_auth_admin

        mock_supabase.get_client.return_value = mock_client

        # Create mock invoice
        mock_invoice = MagicMock()
        mock_invoice.customer = "cus_123"
        mock_invoice.total = 200000  # $2000.00 in cents
        mock_invoice.created = 1704067200  # Timestamp

        with patch("src.services.email_service.EmailService") as mock_email_service_class:
            mock_email_instance = MagicMock()
            mock_email_instance.send_payment_receipt = AsyncMock(return_value="email_id")
            mock_email_service_class.return_value = mock_email_instance

            await billing_service._handle_payment_succeeded(mock_invoice)

            # Verify email was sent
            mock_email_instance.send_payment_receipt.assert_called_once()
            call_args = mock_email_instance.send_payment_receipt.call_args
            assert call_args[0][0] == "admin@example.com"  # to
            assert call_args[0][1] == 200000  # amount in cents

    @pytest.mark.asyncio
    async def test_payment_failed_sends_email(self, billing_service, mock_supabase):
        """Test that payment failure sends an email notification."""
        mock_client = MagicMock()

        # Mock _update_subscription_status to avoid database calls
        billing_service._update_subscription_status = AsyncMock()

        # Create separate mock chains for companies and user_profiles queries
        mock_companies_table = MagicMock()
        mock_companies_execute = MagicMock()
        mock_companies_execute.data = {"id": "company-123", "name": "Test Company"}
        mock_companies_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_companies_execute

        mock_user_profiles_table = MagicMock()
        mock_user_execute = MagicMock()
        mock_user_execute.data = [{"id": "admin-123", "full_name": "Admin User"}]
        mock_user_profiles_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = mock_user_execute

        def table_side_effect(table_name):
            if table_name == "companies":
                return mock_companies_table
            elif table_name == "user_profiles":
                return mock_user_profiles_table
            return MagicMock()

        mock_client.table.side_effect = table_side_effect

        # Mock auth admin for getting user email
        mock_auth_admin = MagicMock()
        mock_user_data = MagicMock()
        mock_user_data.user.email = "admin@example.com"
        mock_auth_admin.get_user_by_id.return_value = mock_user_data
        mock_client.auth.admin = mock_auth_admin

        mock_supabase.get_client.return_value = mock_client

        # Create mock invoice
        mock_invoice = MagicMock()
        mock_invoice.customer = "cus_123"

        with patch("src.services.email_service.EmailService") as mock_email_service_class:
            mock_email_instance = MagicMock()
            mock_email_instance.send_payment_failed = AsyncMock(return_value="email_id")
            mock_email_service_class.return_value = mock_email_instance

            await billing_service._handle_payment_failed(mock_invoice)

            # Verify email was sent
            mock_email_instance.send_payment_failed.assert_called_once()
            call_args = mock_email_instance.send_payment_failed.call_args
            assert call_args[0][0] == "admin@example.com"  # to
            assert call_args[0][1] == "Admin User"  # name

    @pytest.mark.asyncio
    async def test_payment_email_failure_logs_warning(
        self, billing_service, mock_supabase, caplog
    ):
        """Test that email sending failures are logged but don't break payment handling."""
        mock_client = MagicMock()

        # Mock _update_subscription_status to avoid database calls
        billing_service._update_subscription_status = AsyncMock()

        mock_companies_table = MagicMock()
        mock_companies_execute = MagicMock()
        mock_companies_execute.data = {"id": "company-123", "name": "Test Company"}
        mock_companies_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_companies_execute

        mock_user_profiles_table = MagicMock()
        mock_user_execute = MagicMock()
        mock_user_execute.data = [{"id": "admin-123", "full_name": "Admin User"}]
        mock_user_profiles_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = mock_user_execute

        def table_side_effect(table_name):
            if table_name == "companies":
                return mock_companies_table
            elif table_name == "user_profiles":
                return mock_user_profiles_table
            return MagicMock()

        mock_client.table.side_effect = table_side_effect

        # Mock auth admin for getting user email
        mock_auth_admin = MagicMock()
        mock_user_data = MagicMock()
        mock_user_data.user.email = "admin@example.com"
        mock_auth_admin.get_user_by_id.return_value = mock_user_data
        mock_client.auth.admin = mock_auth_admin

        mock_supabase.get_client.return_value = mock_client

        mock_invoice = MagicMock()
        mock_invoice.customer = "cus_123"
        mock_invoice.total = 200000
        mock_invoice.created = 1704067200

        with patch("src.services.email_service.EmailService") as mock_email_service_class:
            mock_email_instance = MagicMock()
            mock_email_instance.send_payment_receipt = AsyncMock(
                side_effect=Exception("Email service down")
            )
            mock_email_service_class.return_value = mock_email_instance

            # Should not raise even if email fails
            await billing_service._handle_payment_succeeded(mock_invoice)

            # Email was attempted
            mock_email_instance.send_payment_receipt.assert_called_once()


class TestBillingServiceNotConfigured:
    """Test BillingService behavior when Stripe is not configured."""

    @pytest.mark.asyncio
    async def test_get_or_create_customer_raises_when_not_configured(
        self, billing_service
    ):
        """Test that creating a customer raises BillingError when Stripe is not configured."""
        billing_service._stripe_key = ""
        with pytest.raises(BillingError, match="Stripe is not configured"):
            await billing_service.get_or_create_customer("company-123", "admin@example.com")

    @pytest.mark.asyncio
    async def test_create_checkout_session_raises_when_not_configured(
        self, billing_service
    ):
        """Test that creating a checkout session raises when Stripe is not configured."""
        billing_service._stripe_key = ""
        with pytest.raises(BillingError, match="Stripe is not configured"):
            await billing_service.create_checkout_session("company-123", "admin@example.com")

    @pytest.mark.asyncio
    async def test_create_portal_session_raises_when_not_configured(
        self, billing_service
    ):
        """Test that creating a portal session raises when Stripe is not configured."""
        billing_service._stripe_key = ""
        with pytest.raises(BillingError, match="Stripe is not configured"):
            await billing_service.create_portal_session("company-123")

    @pytest.mark.asyncio
    async def test_get_invoices_returns_empty_when_not_configured(
        self, billing_service
    ):
        """Test that get_invoices returns empty list when Stripe is not configured."""
        billing_service._stripe_key = ""
        result = await billing_service.get_invoices("company-123")
        assert result == []

    @pytest.mark.asyncio
    async def test_handle_webhook_raises_when_not_configured(
        self, billing_service
    ):
        """Test that handling webhooks raises when Stripe is not configured."""
        billing_service._stripe_key = ""
        with pytest.raises(BillingError, match="Stripe is not configured"):
            await billing_service.handle_webhook(b"payload", "sig_header")


class TestWebhookEdgeCases:
    """Test webhook handling edge cases."""

    @pytest.mark.asyncio
    async def test_webhook_secret_not_configured(
        self, billing_service, mock_stripe
    ):
        """Test that webhook raises when webhook secret is not configured."""
        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_WEBHOOK_SECRET.get_secret_value.return_value = ""
            with pytest.raises(BillingError, match="Webhook secret not configured"):
                await billing_service.handle_webhook(b"payload", "sig_header")

    @pytest.mark.asyncio
    async def test_unhandled_webhook_event_type(
        self, billing_service, mock_stripe
    ):
        """Test that unhandled event types are logged but don't raise."""
        payload = b"test_payload"
        sig_header = "t=123,v1=abc123"

        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_WEBHOOK_SECRET.get_secret_value.return_value = "whsec_test"

            mock_event = MagicMock()
            mock_event.type = "customer.updated"
            mock_event.data.object = MagicMock()

            mock_stripe.Webhook.construct_event.return_value = mock_event

            # Should not raise
            await billing_service.handle_webhook(payload, sig_header)

    @pytest.mark.asyncio
    async def test_checkout_completed_without_subscription(
        self, billing_service, mock_stripe
    ):
        """Test checkout completed event when session has no subscription."""
        billing_service._update_subscription_status = AsyncMock()

        mock_session = MagicMock()
        mock_session.customer = "cus_123"
        mock_session.subscription = None

        await billing_service._handle_checkout_completed(mock_session)

        billing_service._update_subscription_status.assert_not_called()


class TestUpdateSubscriptionStatus:
    """Test internal subscription status update logic."""

    @pytest.mark.asyncio
    async def test_update_status_no_company_found(
        self, billing_service, mock_supabase
    ):
        """Test status update when no company found for customer ID."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        mock_source = MagicMock()
        mock_source.customer = "cus_unknown"

        await billing_service._update_subscription_status(
            "cus_unknown", "active", mock_source
        )

        mock_client.table.return_value.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_status_builds_metadata_from_subscription(
        self, billing_service, mock_supabase
    ):
        """Test that metadata is correctly extracted from subscription source."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "company-123"}
        )

        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        mock_source = MagicMock()
        mock_source.current_period_end = 1735689600
        mock_source.cancel_at_period_end = True
        mock_price = MagicMock()
        mock_price.nickname = "ARIA Annual"
        mock_item = MagicMock()
        mock_item.price = mock_price
        mock_source.items = MagicMock()
        mock_source.items.data = [mock_item]

        await billing_service._update_subscription_status(
            "cus_123", "active", mock_source
        )

        mock_client.table.return_value.update.assert_called_once()
        call_args = mock_client.table.return_value.update.call_args[0][0]
        assert call_args["subscription_status"] == "active"
        assert call_args["subscription_metadata"]["cancel_at_period_end"] is True
        assert call_args["subscription_metadata"]["plan"] == "ARIA Annual"

    @pytest.mark.asyncio
    async def test_update_status_handles_database_error(
        self, billing_service, mock_supabase, caplog
    ):
        """Test that database errors are caught and logged."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.side_effect = Exception("Database connection failed")

        mock_source = MagicMock()

        await billing_service._update_subscription_status(
            "cus_123", "active", mock_source
        )


class TestGetCompanyAdminEmail:
    """Test admin email lookup for billing notifications."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_company(
        self, billing_service, mock_supabase
    ):
        """Test that None is returned when company not found."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        result = await billing_service._get_company_admin_email("cus_unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_admin_users(
        self, billing_service, mock_supabase
    ):
        """Test that None is returned when company has no admin users."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        mock_companies_table = MagicMock()
        mock_companies_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "company-123"}
        )

        mock_user_profiles_table = MagicMock()
        mock_user_profiles_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        def table_side_effect(table_name):
            if table_name == "companies":
                return mock_companies_table
            elif table_name == "user_profiles":
                return mock_user_profiles_table
            return MagicMock()

        mock_client.table.side_effect = table_side_effect

        result = await billing_service._get_company_admin_email("cus_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(
        self, billing_service, mock_supabase
    ):
        """Test that None is returned on database exceptions."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.side_effect = Exception("Database error")

        result = await billing_service._get_company_admin_email("cus_123")
        assert result is None


class TestCheckoutSessionCreation:
    """Test checkout session creation edge cases."""

    @pytest.mark.asyncio
    async def test_creates_setup_mode_without_price_id(
        self, billing_service, mock_stripe
    ):
        """Test that checkout creates setup mode when STRIPE_PRICE_ID is not set."""
        billing_service.get_or_create_customer = AsyncMock(return_value="cus_123")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/session"
        mock_session.id = "cs_test_123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_PRICE_ID = ""
            mock_settings.APP_URL = "http://localhost:3000"

            result = await billing_service.create_checkout_session(
                "company-123", "admin@example.com"
            )

            assert result == "https://checkout.stripe.com/session"
            call_args = mock_stripe.checkout.Session.create.call_args
            assert call_args.kwargs.get("mode") == "setup" or call_args[1].get("mode") == "setup"

    @pytest.mark.asyncio
    async def test_uses_custom_urls_when_provided(
        self, billing_service, mock_stripe
    ):
        """Test that custom success and cancel URLs are used when provided."""
        billing_service.get_or_create_customer = AsyncMock(return_value="cus_123")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/session"
        mock_session.id = "cs_test_123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        with patch("src.services.billing_service.settings") as mock_settings:
            mock_settings.STRIPE_PRICE_ID = "price_123"
            mock_settings.APP_URL = "http://localhost:3000"

            await billing_service.create_checkout_session(
                "company-123",
                "admin@example.com",
                success_url="https://custom.com/success",
                cancel_url="https://custom.com/cancel",
            )

            call_args = mock_stripe.checkout.Session.create.call_args
            assert "https://custom.com/success" in str(call_args)
            assert "https://custom.com/cancel" in str(call_args)

    @pytest.mark.asyncio
    async def test_portal_session_no_stripe_customer(
        self, billing_service, mock_supabase
    ):
        """Test portal session creation when company has no Stripe customer."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "company-123", "stripe_customer_id": None}
        )

        with pytest.raises(BillingError, match="No Stripe customer"):
            await billing_service.create_portal_session("company-123")


class TestInvoiceEdgeCases:
    """Test invoice retrieval edge cases."""

    @pytest.mark.asyncio
    async def test_invoice_with_null_fields(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test handling invoices with null total, created, or pdf fields."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "company-123", "stripe_customer_id": "cus_123"}
        )

        mock_invoice = MagicMock()
        mock_invoice.id = "in_null"
        mock_invoice.total = None
        mock_invoice.currency = "usd"
        mock_invoice.status = "draft"
        mock_invoice.created = None
        mock_invoice.invoice_pdf = None

        mock_stripe.Invoice.list.return_value = MagicMock(data=[mock_invoice])

        result = await billing_service.get_invoices("company-123")

        assert len(result) == 1
        assert result[0]["amount"] == 0
        assert result[0]["date"] is None
        assert result[0]["pdf_url"] is None

    @pytest.mark.asyncio
    async def test_invoice_zero_amount(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test handling zero-amount invoices."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "company-123", "stripe_customer_id": "cus_123"}
        )

        mock_invoice = MagicMock()
        mock_invoice.id = "in_zero"
        mock_invoice.total = 0
        mock_invoice.currency = "usd"
        mock_invoice.status = "paid"
        mock_invoice.created = 1704067200
        mock_invoice.invoice_pdf = "https://example.com/invoice.pdf"

        mock_stripe.Invoice.list.return_value = MagicMock(data=[mock_invoice])

        result = await billing_service.get_invoices("company-123")

        assert result[0]["amount"] == 0.0


class TestSubscriptionStatusEdgeCases:
    """Test subscription status parsing edge cases."""

    @pytest.mark.asyncio
    async def test_status_with_no_stripe_customer(
        self, billing_service, mock_supabase
    ):
        """Test status falls back to database when no Stripe customer."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "company-123",
                "stripe_customer_id": None,
                "subscription_status": "trial",
                "subscription_metadata": {},
            }
        )

        mock_seats = MagicMock()
        mock_seats.count = 1
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_seats

        result = await billing_service.get_subscription_status("company-123")

        assert result["status"] == "trial"
        assert result["seats_used"] == 1

    @pytest.mark.asyncio
    async def test_status_stripe_api_failure_falls_back(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test that Stripe API failure falls back to database data."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "company-123",
                "stripe_customer_id": "cus_123",
                "subscription_status": "active",
                "subscription_metadata": {"plan": "ARIA Annual"},
            }
        )

        mock_seats = MagicMock()
        mock_seats.count = 2
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_seats

        mock_stripe.Subscription.list.side_effect = Exception("Stripe API error")

        result = await billing_service.get_subscription_status("company-123")

        assert result["status"] == "active"
        assert result["plan"] == "ARIA Annual"

    @pytest.mark.asyncio
    async def test_status_subscription_no_price_nickname(
        self, billing_service, mock_supabase, mock_stripe
    ):
        """Test status parsing when subscription price has no nickname."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "company-123",
                "stripe_customer_id": "cus_123",
                "subscription_status": "trial",
                "subscription_metadata": {},
            }
        )

        mock_seats = MagicMock()
        mock_seats.count = 1
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_seats

        mock_subscription = MagicMock()
        mock_subscription.status = "active"
        mock_subscription.current_period_end = 1735689600
        mock_subscription.cancel_at_period_end = False

        mock_price = MagicMock()
        mock_price.nickname = None
        mock_price.id = "price_abc123"

        mock_item = MagicMock()
        mock_item.price = mock_price
        mock_subscription.items = MagicMock()
        mock_subscription.items.data = [mock_item]

        mock_stripe.Subscription.list.return_value = MagicMock(data=[mock_subscription])

        result = await billing_service.get_subscription_status("company-123")

        # nickname is None so plan resolves to None (no fallback in get_subscription_status)
        assert result["plan"] is None

    @pytest.mark.asyncio
    async def test_status_seats_count_none(
        self, billing_service, mock_supabase
    ):
        """Test status when seats count returns None."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "company-123",
                "stripe_customer_id": None,
                "subscription_status": "trial",
                "subscription_metadata": {},
            }
        )

        mock_seats = MagicMock()
        mock_seats.count = None
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_seats

        result = await billing_service.get_subscription_status("company-123")

        assert result["seats_used"] == 0
