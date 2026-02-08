"""Billing & Subscription Management API Routes (US-928)."""

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.api.deps import AdminUser
from src.services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])
billing_service = BillingService()


# Request/Response Models
class SubscriptionStatusResponse(BaseModel):
    """Subscription status response."""

    status: str
    plan: str
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
    seats_used: int


class CheckoutRequest(BaseModel):
    """Request to create checkout session."""

    success_url: str | None = Field(None, max_length=500)
    cancel_url: str | None = Field(None, max_length=500)


class CheckoutResponse(BaseModel):
    """Response for checkout session creation."""

    url: str


class PortalRequest(BaseModel):
    """Request to create portal session."""

    return_url: str | None = Field(None, max_length=500)


class PortalResponse(BaseModel):
    """Response for portal session creation."""

    url: str


class Invoice(BaseModel):
    """Invoice information."""

    id: str
    amount: float
    currency: str
    status: str
    date: str | None = None
    pdf_url: str | None = None


class InvoicesResponse(BaseModel):
    """Invoices list response."""

    invoices: list[Invoice]


class WebhookResponse(BaseModel):
    """Webhook processing response."""

    received: bool


# Routes
@router.get(
    "/status",
    response_model=SubscriptionStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_billing_status(
    current_user: AdminUser,
) -> dict[str, Any]:
    """Get current subscription status for the company.

    Requires admin role.

    Args:
        current_user: Authenticated admin user.

    Returns:
        Subscription status information including plan, period end, and seats used.
    """
    try:
        # Get user profile to find company_id
        from src.core.exceptions import NotFoundError
        from src.db.supabase import SupabaseClient

        profile_data = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile_data.get("company_id")

        if not company_id:
            return {
                "status": "trial",
                "plan": "ARIA Annual",
                "current_period_end": None,
                "cancel_at_period_end": False,
                "seats_used": 1,
            }

        return await billing_service.get_subscription_status(company_id)

    except NotFoundError:
        return {
            "status": "trial",
            "plan": "ARIA Annual",
            "current_period_end": None,
            "cancel_at_period_end": False,
            "seats_used": 1,
        }
    except Exception as e:
        logger.exception("Error fetching billing status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Billing service temporarily unavailable.",
        ) from e


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_200_OK,
)
async def create_checkout_session(
    request_data: CheckoutRequest,
    current_user: AdminUser,
) -> dict[str, Any]:
    """Create a Stripe Checkout session for subscription.

    Requires admin role.

    Args:
        request_data: Optional success and cancel URLs.
        current_user: Authenticated admin user.

    Returns:
        Checkout URL to redirect user to Stripe.
    """
    try:
        # Get user profile to find company_id
        from src.db.supabase import SupabaseClient

        profile_data = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile_data.get("company_id")

        if not company_id:
            # For users without a company, use user_id as placeholder
            company_id = current_user.id

        checkout_url = await billing_service.create_checkout_session(
            company_id=company_id,
            admin_email=current_user.email,
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url,
        )

        return {"url": checkout_url}

    except Exception as e:
        logger.exception("Error creating checkout session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Billing service temporarily unavailable.",
        ) from e


@router.post(
    "/portal",
    response_model=PortalResponse,
    status_code=status.HTTP_200_OK,
)
async def create_portal_session(
    request_data: PortalRequest,
    current_user: AdminUser,
) -> dict[str, Any]:
    """Create a Stripe Customer Portal session.

    Requires admin role.

    Args:
        request_data: Optional return URL.
        current_user: Authenticated admin user.

    Returns:
        Portal URL to redirect user to Stripe Customer Portal.
    """
    try:
        # Get user profile to find company_id
        from src.db.supabase import SupabaseClient

        profile_data = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile_data.get("company_id")

        if not company_id:
            from src.services.billing_service import BillingError
            raise BillingError("No company found for this user")

        portal_url = await billing_service.create_portal_session(
            company_id=company_id,
            return_url=request_data.return_url,
        )

        return {"url": portal_url}

    except Exception as e:
        logger.exception("Error creating portal session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Billing service temporarily unavailable.",
        ) from e


@router.get(
    "/invoices",
    response_model=InvoicesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_invoices(
    current_user: AdminUser,
    limit: int = 12,
) -> dict[str, Any]:
    """Get invoice history for the company.

    Requires admin role.

    Args:
        limit: Maximum number of invoices to return (default 12).
        current_user: Authenticated admin user.

    Returns:
        List of invoices with amounts, status, and PDF links.
    """
    try:
        # Get user profile to find company_id
        from src.db.supabase import SupabaseClient

        profile_data = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile_data.get("company_id")

        if not company_id:
            return {"invoices": []}

        invoices = await billing_service.get_invoices(company_id, limit)
        return {"invoices": invoices}

    except Exception as e:
        logger.exception("Error fetching invoices")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Billing service temporarily unavailable.",
        ) from e


@router.post(
    "/webhook",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
) -> dict[str, Any]:
    """Handle Stripe webhook events.

    This endpoint requires no authentication - it's verified via Stripe signature.

    Args:
        request: FastAPI request with raw payload.
        stripe_signature: Stripe signature header for verification.

    Returns:
        Confirmation of webhook receipt.
    """
    try:
        payload = await request.body()
        await billing_service.handle_webhook(payload, stripe_signature)
        return {"received": True}
    except Exception:
        logger.exception("Error processing webhook")
        # Always return 200 to Stripe to avoid retries on known errors
        return {"received": True}
