-- Add phone column to user_profiles (P2-3)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS phone TEXT;
