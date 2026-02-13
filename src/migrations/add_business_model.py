"""Add business model tables: subscriptions, consultancy marketplace, referrals.

Creates:
- platform_subscriptions: Platform tier (Free/Pro) management
- feature_definitions: Feature flags controlled by tier
- professional_profiles: Extended marketplace profiles for professionals
- consultancy_listings: Service listings on the marketplace
- consultancy_transactions: Purchase records
- consultancy_reviews: Reviews for consultancy services
- referral_codes: Unique referral codes per user
- referrals: Referral tracking (who invited whom)
- referral_rewards: Rewards granted for referrals
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def _table_exists(conn, table_name: str, is_postgres: bool) -> bool:
    if is_postgres:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                f"  WHERE table_name = '{table_name}'"
                ")"
            )
        )
        return result.scalar()
    else:
        result = await conn.execute(
            text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
            )
        )
        return result.first() is not None


async def migrate(database_url: str) -> None:
    """Create business model tables."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # ── 1. platform_subscriptions ──
        if not await _table_exists(conn, "platform_subscriptions", is_postgres):
            if is_postgres:
                # Create enum types
                for enum_name, values in [
                    ("platform_tier_enum", "'free', 'pro'"),
                    ("subscription_status_enum", "'active', 'cancelled', 'expired', 'trial'"),
                    ("subscription_source_enum", "'direct', 'referral', 'founder', 'promotion', 'trial'"),
                ]:
                    await conn.execute(text(f"""
                        DO $$ BEGIN
                            CREATE TYPE {enum_name} AS ENUM ({values});
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$
                    """))

                await conn.execute(text("""
                    CREATE TABLE platform_subscriptions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        tier VARCHAR(10) NOT NULL DEFAULT 'free',
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        source VARCHAR(20) NOT NULL DEFAULT 'direct',
                        amount_cents INTEGER NOT NULL DEFAULT 0,
                        currency VARCHAR(3) NOT NULL DEFAULT 'BRL',
                        started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        expires_at TIMESTAMP WITH TIME ZONE,
                        cancelled_at TIMESTAMP WITH TIME ZONE,
                        trial_ends_at TIMESTAMP WITH TIME ZONE,
                        external_subscription_id VARCHAR(255),
                        payment_provider VARCHAR(50),
                        is_founder BOOLEAN NOT NULL DEFAULT false,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_platform_subscriptions_user_id ON platform_subscriptions(user_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE platform_subscriptions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        tier TEXT NOT NULL DEFAULT 'free',
                        status TEXT NOT NULL DEFAULT 'active',
                        source TEXT NOT NULL DEFAULT 'direct',
                        amount_cents INTEGER NOT NULL DEFAULT 0,
                        currency TEXT NOT NULL DEFAULT 'BRL',
                        started_at TEXT DEFAULT (datetime('now')),
                        expires_at TEXT,
                        cancelled_at TEXT,
                        trial_ends_at TEXT,
                        external_subscription_id TEXT,
                        payment_provider TEXT,
                        is_founder INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created platform_subscriptions table")
        else:
            logger.info("platform_subscriptions already exists")

        # ── 2. feature_definitions ──
        if not await _table_exists(conn, "feature_definitions", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    CREATE TABLE feature_definitions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        key VARCHAR(100) UNIQUE NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        required_tier VARCHAR(10) NOT NULL DEFAULT 'free',
                        free_tier_limit INTEGER,
                        pro_tier_limit INTEGER,
                        is_enabled BOOLEAN NOT NULL DEFAULT true,
                        category VARCHAR(50)
                    )
                """))
            else:
                await conn.execute(text("""
                    CREATE TABLE feature_definitions (
                        id TEXT PRIMARY KEY,
                        key TEXT UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT,
                        required_tier TEXT NOT NULL DEFAULT 'free',
                        free_tier_limit INTEGER,
                        pro_tier_limit INTEGER,
                        is_enabled INTEGER NOT NULL DEFAULT 1,
                        category TEXT
                    )
                """))
            logger.info("Created feature_definitions table")

            # Seed default features
            features = [
                ("max_active_students", "Active Students", "Maximum number of active students", "free", 5, None, "students"),
                ("advanced_analytics", "Advanced Analytics", "Detailed student analytics", "pro", None, None, "analytics"),
                ("marketplace_highlight", "Marketplace Highlight", "Priority in marketplace search", "pro", None, None, "marketplace"),
                ("ai_workout_generation", "AI Workout Generation", "AI-powered workout plans", "pro", None, None, "ai"),
                ("custom_branding", "Custom Branding", "Personalized branding", "pro", None, None, "branding"),
                ("professional_reports", "Professional Reports", "Generate PDF reports", "pro", None, None, "reports"),
                ("marketplace_sell", "Sell on Marketplace", "List consultancies on marketplace", "free", None, None, "marketplace"),
            ]
            for key, name, desc, tier, free_limit, pro_limit, cat in features:
                free_val = f"{free_limit}" if free_limit else "NULL"
                pro_val = f"{pro_limit}" if pro_limit else "NULL"
                if is_postgres:
                    await conn.execute(text(f"""
                        INSERT INTO feature_definitions (id, key, name, description, required_tier, free_tier_limit, pro_tier_limit, category)
                        VALUES (gen_random_uuid(), '{key}', '{name}', '{desc}', '{tier}', {free_val}, {pro_val}, '{cat}')
                        ON CONFLICT (key) DO NOTHING
                    """))
                else:
                    await conn.execute(text(f"""
                        INSERT OR IGNORE INTO feature_definitions (id, key, name, description, required_tier, free_tier_limit, pro_tier_limit, category)
                        VALUES (lower(hex(randomblob(16))), '{key}', '{name}', '{desc}', '{tier}', {free_val}, {pro_val}, '{cat}')
                    """))
            logger.info("Seeded feature_definitions")
        else:
            logger.info("feature_definitions already exists")

        # ── 3. professional_profiles ──
        if not await _table_exists(conn, "professional_profiles", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    CREATE TABLE professional_profiles (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        headline VARCHAR(200),
                        bio TEXT,
                        specialties JSONB,
                        certifications JSONB,
                        languages JSONB,
                        experience_years INTEGER,
                        city VARCHAR(100),
                        state VARCHAR(50),
                        country VARCHAR(2) NOT NULL DEFAULT 'BR',
                        instagram VARCHAR(100),
                        website VARCHAR(255),
                        portfolio_images JSONB,
                        rating_average NUMERIC(3,2),
                        rating_count INTEGER NOT NULL DEFAULT 0,
                        total_students_served INTEGER NOT NULL DEFAULT 0,
                        total_consultancies_sold INTEGER NOT NULL DEFAULT 0,
                        is_public BOOLEAN NOT NULL DEFAULT true,
                        is_verified BOOLEAN NOT NULL DEFAULT false,
                        is_featured BOOLEAN NOT NULL DEFAULT false,
                        is_accepting_students BOOLEAN NOT NULL DEFAULT true,
                        max_concurrent_students INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_professional_profiles_user_id ON professional_profiles(user_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE professional_profiles (
                        id TEXT PRIMARY KEY,
                        user_id TEXT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        headline TEXT,
                        bio TEXT,
                        specialties TEXT,
                        certifications TEXT,
                        languages TEXT,
                        experience_years INTEGER,
                        city TEXT,
                        state TEXT,
                        country TEXT NOT NULL DEFAULT 'BR',
                        instagram TEXT,
                        website TEXT,
                        portfolio_images TEXT,
                        rating_average REAL,
                        rating_count INTEGER NOT NULL DEFAULT 0,
                        total_students_served INTEGER NOT NULL DEFAULT 0,
                        total_consultancies_sold INTEGER NOT NULL DEFAULT 0,
                        is_public INTEGER NOT NULL DEFAULT 1,
                        is_verified INTEGER NOT NULL DEFAULT 0,
                        is_featured INTEGER NOT NULL DEFAULT 0,
                        is_accepting_students INTEGER NOT NULL DEFAULT 1,
                        max_concurrent_students INTEGER,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created professional_profiles table")
        else:
            logger.info("professional_profiles already exists")

        # ── 4. consultancy_listings ──
        if not await _table_exists(conn, "consultancy_listings", is_postgres):
            if is_postgres:
                for enum_name, values in [
                    ("consultancy_category_enum", "'personal_training', 'online_coaching', 'nutrition', 'sports_nutrition', 'physical_assessment', 'rehabilitation', 'yoga', 'pilates', 'functional', 'bodybuilding', 'crossfit', 'other'"),
                    ("consultancy_format_enum", "'monthly', 'package', 'single'"),
                ]:
                    await conn.execute(text(f"""
                        DO $$ BEGIN
                            CREATE TYPE {enum_name} AS ENUM ({values});
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$
                    """))

                await conn.execute(text("""
                    CREATE TABLE consultancy_listings (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        professional_id UUID NOT NULL REFERENCES professional_profiles(id) ON DELETE CASCADE,
                        title VARCHAR(200) NOT NULL,
                        short_description VARCHAR(500),
                        full_description TEXT,
                        cover_image_url VARCHAR(500),
                        gallery_images JSONB,
                        category VARCHAR(30) NOT NULL,
                        tags JSONB,
                        format VARCHAR(20) NOT NULL,
                        price_cents INTEGER NOT NULL,
                        currency VARCHAR(3) NOT NULL DEFAULT 'BRL',
                        duration_days INTEGER,
                        sessions_included INTEGER,
                        includes JSONB,
                        commission_rate INTEGER NOT NULL DEFAULT 0,
                        purchase_count INTEGER NOT NULL DEFAULT 0,
                        rating_average NUMERIC(3,2),
                        rating_count INTEGER NOT NULL DEFAULT 0,
                        view_count INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        is_featured BOOLEAN NOT NULL DEFAULT false,
                        deleted_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_consultancy_listings_professional_id ON consultancy_listings(professional_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE consultancy_listings (
                        id TEXT PRIMARY KEY,
                        professional_id TEXT NOT NULL REFERENCES professional_profiles(id) ON DELETE CASCADE,
                        title TEXT NOT NULL,
                        short_description TEXT,
                        full_description TEXT,
                        cover_image_url TEXT,
                        gallery_images TEXT,
                        category TEXT NOT NULL,
                        tags TEXT,
                        format TEXT NOT NULL,
                        price_cents INTEGER NOT NULL,
                        currency TEXT NOT NULL DEFAULT 'BRL',
                        duration_days INTEGER,
                        sessions_included INTEGER,
                        includes TEXT,
                        commission_rate INTEGER NOT NULL DEFAULT 0,
                        purchase_count INTEGER NOT NULL DEFAULT 0,
                        rating_average REAL,
                        rating_count INTEGER NOT NULL DEFAULT 0,
                        view_count INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        is_featured INTEGER NOT NULL DEFAULT 0,
                        deleted_at TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created consultancy_listings table")
        else:
            logger.info("consultancy_listings already exists")

        # ── 5. consultancy_transactions ──
        if not await _table_exists(conn, "consultancy_transactions", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    DO $$ BEGIN
                        CREATE TYPE transaction_status_enum AS ENUM (
                            'pending', 'confirmed', 'active', 'completed', 'cancelled', 'refunded', 'disputed'
                        );
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$
                """))

                await conn.execute(text("""
                    CREATE TABLE consultancy_transactions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        listing_id UUID NOT NULL REFERENCES consultancy_listings(id) ON DELETE CASCADE,
                        buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        seller_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        amount_cents INTEGER NOT NULL,
                        commission_cents INTEGER NOT NULL DEFAULT 0,
                        seller_earnings_cents INTEGER NOT NULL,
                        currency VARCHAR(3) NOT NULL DEFAULT 'BRL',
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        confirmed_at TIMESTAMP WITH TIME ZONE,
                        started_at TIMESTAMP WITH TIME ZONE,
                        completed_at TIMESTAMP WITH TIME ZONE,
                        cancelled_at TIMESTAMP WITH TIME ZONE,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        payment_provider VARCHAR(50),
                        external_payment_id VARCHAR(255),
                        organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
                        buyer_notes TEXT,
                        seller_notes TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_consultancy_transactions_listing_id ON consultancy_transactions(listing_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_consultancy_transactions_buyer_id ON consultancy_transactions(buyer_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_consultancy_transactions_seller_id ON consultancy_transactions(seller_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE consultancy_transactions (
                        id TEXT PRIMARY KEY,
                        listing_id TEXT NOT NULL REFERENCES consultancy_listings(id) ON DELETE CASCADE,
                        buyer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        seller_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        amount_cents INTEGER NOT NULL,
                        commission_cents INTEGER NOT NULL DEFAULT 0,
                        seller_earnings_cents INTEGER NOT NULL,
                        currency TEXT NOT NULL DEFAULT 'BRL',
                        status TEXT NOT NULL DEFAULT 'pending',
                        confirmed_at TEXT,
                        started_at TEXT,
                        completed_at TEXT,
                        cancelled_at TEXT,
                        expires_at TEXT,
                        payment_provider TEXT,
                        external_payment_id TEXT,
                        organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
                        buyer_notes TEXT,
                        seller_notes TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created consultancy_transactions table")
        else:
            logger.info("consultancy_transactions already exists")

        # ── 6. consultancy_reviews ──
        if not await _table_exists(conn, "consultancy_reviews", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    CREATE TABLE consultancy_reviews (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        transaction_id UUID UNIQUE NOT NULL REFERENCES consultancy_transactions(id) ON DELETE CASCADE,
                        listing_id UUID NOT NULL REFERENCES consultancy_listings(id) ON DELETE CASCADE,
                        reviewer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        professional_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        rating INTEGER NOT NULL,
                        title VARCHAR(200),
                        comment TEXT,
                        response TEXT,
                        responded_at TIMESTAMP WITH TIME ZONE,
                        is_verified_purchase BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_consultancy_reviews_listing_id ON consultancy_reviews(listing_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_consultancy_reviews_professional_id ON consultancy_reviews(professional_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE consultancy_reviews (
                        id TEXT PRIMARY KEY,
                        transaction_id TEXT UNIQUE NOT NULL REFERENCES consultancy_transactions(id) ON DELETE CASCADE,
                        listing_id TEXT NOT NULL REFERENCES consultancy_listings(id) ON DELETE CASCADE,
                        reviewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        professional_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        rating INTEGER NOT NULL,
                        title TEXT,
                        comment TEXT,
                        response TEXT,
                        responded_at TEXT,
                        is_verified_purchase INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created consultancy_reviews table")
        else:
            logger.info("consultancy_reviews already exists")

        # ── 7. referral_codes ──
        if not await _table_exists(conn, "referral_codes", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    CREATE TABLE referral_codes (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        code VARCHAR(20) UNIQUE NOT NULL,
                        total_referrals INTEGER NOT NULL DEFAULT 0,
                        successful_referrals INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_referral_codes_user_id ON referral_codes(user_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE referral_codes (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        code TEXT UNIQUE NOT NULL,
                        total_referrals INTEGER NOT NULL DEFAULT 0,
                        successful_referrals INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created referral_codes table")
        else:
            logger.info("referral_codes already exists")

        # ── 8. referrals ──
        if not await _table_exists(conn, "referrals", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    CREATE TABLE referrals (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        referral_code_id UUID NOT NULL REFERENCES referral_codes(id) ON DELETE CASCADE,
                        referrer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        referred_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        is_qualified BOOLEAN NOT NULL DEFAULT false,
                        qualified_at TIMESTAMP WITH TIME ZONE,
                        referrer_rewarded BOOLEAN NOT NULL DEFAULT false,
                        referred_rewarded BOOLEAN NOT NULL DEFAULT false,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_referrals_referral_code_id ON referrals(referral_code_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_referrals_referrer_id ON referrals(referrer_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_referrals_referred_id ON referrals(referred_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE referrals (
                        id TEXT PRIMARY KEY,
                        referral_code_id TEXT NOT NULL REFERENCES referral_codes(id) ON DELETE CASCADE,
                        referrer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        referred_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        is_qualified INTEGER NOT NULL DEFAULT 0,
                        qualified_at TEXT,
                        referrer_rewarded INTEGER NOT NULL DEFAULT 0,
                        referred_rewarded INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created referrals table")
        else:
            logger.info("referrals already exists")

        # ── 9. referral_rewards ──
        if not await _table_exists(conn, "referral_rewards", is_postgres):
            if is_postgres:
                for enum_name, values in [
                    ("reward_type_enum", "'pro_trial', 'consultancy_discount', 'free_consultancy'"),
                    ("reward_status_enum", "'pending', 'active', 'used', 'expired'"),
                ]:
                    await conn.execute(text(f"""
                        DO $$ BEGIN
                            CREATE TYPE {enum_name} AS ENUM ({values});
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$
                    """))

                await conn.execute(text("""
                    CREATE TABLE referral_rewards (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        referral_id UUID NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        reward_type VARCHAR(30) NOT NULL,
                        reward_days INTEGER,
                        reward_value_cents INTEGER,
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        activated_at TIMESTAMP WITH TIME ZONE,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_referral_rewards_referral_id ON referral_rewards(referral_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_referral_rewards_user_id ON referral_rewards(user_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE referral_rewards (
                        id TEXT PRIMARY KEY,
                        referral_id TEXT NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        reward_type TEXT NOT NULL,
                        reward_days INTEGER,
                        reward_value_cents INTEGER,
                        status TEXT NOT NULL DEFAULT 'pending',
                        activated_at TEXT,
                        expires_at TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))
            logger.info("Created referral_rewards table")
        else:
            logger.info("referral_rewards already exists")

    await engine.dispose()
    logger.info("Migration add_business_model completed successfully")


async def main():
    """Run migration with default database URL."""
    import os
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./myfit.db"
    )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await migrate(database_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
