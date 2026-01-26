-- Migration: Add onboarding profile fields to users table
-- Version: 0.6.4
-- Date: 2026-01-26
-- Description: Adds fields for storing student and trainer onboarding data

-- Run this on PRODUCTION database to sync with dev/staging

-- Check if migration already applied
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'onboarding_completed'
    ) THEN
        RAISE NOTICE 'Migration already applied - onboarding_completed column exists';
    ELSE
        -- Trainer onboarding fields
        ALTER TABLE users ADD COLUMN IF NOT EXISTS specialties VARCHAR(500);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS years_of_experience INTEGER;

        -- Student onboarding fields
        ALTER TABLE users ADD COLUMN IF NOT EXISTS fitness_goal VARCHAR(50);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS fitness_goal_other VARCHAR(200);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_level VARCHAR(20);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS weight_kg FLOAT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_frequency INTEGER;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS injuries VARCHAR(500);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS injuries_other VARCHAR(200);

        -- Onboarding completion tracking
        ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE;

        RAISE NOTICE 'Migration applied successfully - onboarding fields added';
    END IF;
END $$;

-- Verify columns were added
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name IN (
    'specialties', 'years_of_experience',
    'fitness_goal', 'fitness_goal_other', 'experience_level',
    'weight_kg', 'age', 'weekly_frequency',
    'injuries', 'injuries_other',
    'onboarding_completed'
)
ORDER BY column_name;
