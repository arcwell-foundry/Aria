-- Billing & Subscription Management (US-928)
-- Add Stripe customer ID and subscription status to companies table

-- Add Stripe customer ID column
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

-- Add subscription status column with default trial
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS subscription_status TEXT
    DEFAULT 'trial'
    CHECK (subscription_status IN ('trial', 'active', 'past_due', 'canceled', 'incomplete'));

-- Add subscription metadata JSONB for additional subscription details
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS subscription_metadata JSONB DEFAULT '{}';

-- Create index for Stripe customer lookups
CREATE INDEX IF NOT EXISTS idx_companies_stripe_customer_id
    ON companies(stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- Create index for subscription status queries
CREATE INDEX IF NOT EXISTS idx_companies_subscription_status
    ON companies(subscription_status);

-- Add comment for documentation
COMMENT ON COLUMN companies.stripe_customer_id IS 'Stripe customer ID for billing';
COMMENT ON COLUMN companies.subscription_status IS 'Current subscription status: trial, active, past_due, canceled, incomplete';
COMMENT ON COLUMN companies.subscription_metadata IS 'Additional subscription details: plan, current_period_end, cancel_at_period_end, etc.';
