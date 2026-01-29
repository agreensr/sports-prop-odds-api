-- =============================================================================
-- Rollback Migration 021: Remove Sport-Specific Columns
-- =============================================================================
-- This removes the sport-specific columns added for full unification.

BEGIN;

-- Basketball fields
ALTER TABLE players DROP COLUMN IF EXISTS height;
ALTER TABLE players DROP COLUMN IF EXISTS weight;

-- Football fields
ALTER TABLE players DROP COLUMN IF EXISTS college;
ALTER TABLE players DROP COLUMN IF EXISTS draft_year;
ALTER TABLE players DROP COLUMN IF EXISTS draft_round;
ALTER TABLE players DROP COLUMN IF EXISTS jersey_number;

-- Hockey fields
ALTER TABLE players DROP COLUMN IF EXISTS catches;
ALTER TABLE players DROP COLUMN IF EXISTS birth_date;
ALTER TABLE players DROP COLUMN IF EXISTS shoots;

-- Baseball fields
ALTER TABLE players DROP COLUMN IF EXISTS bats;
ALTER TABLE players DROP COLUMN IF EXISTS throws;

-- Game-specific fields
ALTER TABLE games DROP COLUMN IF EXISTS week;
ALTER TABLE games DROP COLUMN IF EXISTS season_type;
ALTER TABLE games DROP COLUMN IF EXISTS shootout;
ALTER TABLE games DROP COLUMN IF EXISTS double_header;
ALTER TABLE games DROP COLUMN IF EXISTS game_number;
ALTER TABLE games DROP COLUMN IF EXISTS inning;

COMMIT;
