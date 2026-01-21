#!/bin/bash
#####################################################################
# NBA Sports API - Database Migration Script
# Adds ESPN external_id column to players table and creates indexes
#####################################################################

set -e

# Configuration
REMOTE_HOST="89.117.150.95"
REMOTE_USER="root"

# Get database connection from environment or prompt
read -p "PostgreSQL host (default: localhost): " DB_HOST
DB_HOST=${DB_HOST:-localhost}

read -p "PostgreSQL port (default: 5432): " DB_PORT
DB_PORT=${DB_PORT:-5432}

read -p "Database name (default: sports_betting): " DB_NAME
DB_NAME=${DB_NAME:-sports_betting}

read -p "Database user (default: postgres): " DB_USER
DB_USER=${DB_USER:-postgres}

read -sp "Database password: " DB_PASS
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Set PGPASSWORD for psql commands
export PGPASSWORD=$DB_PASS

check_db_connection() {
    log_info "Checking database connection..."

    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &> /dev/null; then
        log_info "Database connection successful"
        return 0
    else
        log_error "Cannot connect to database"
        return 1
    fi
}

check_column_exists() {
    local column_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='players' AND column_name='external_id'
        );
    ")

    if [ "$column_exists" = "t" ]; then
        return 0
    else
        return 1
    fi
}

run_migration() {
    log_info "Running database migration..."

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << 'EOF'
        -- Add external_id column if it doesn't exist
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='players' AND column_name='external_id'
            ) THEN
                ALTER TABLE players ADD COLUMN external_id VARCHAR(50);
                ALTER TABLE players ADD CONSTRAINT players_external_id_key UNIQUE (external_id);
                RAISE NOTICE 'Added external_id column to players table';
            ELSE
                RAISE NOTICE 'external_id column already exists';
            END IF;
        END
        $$;

        -- Create index on external_id if it doesn't exist
        CREATE INDEX IF NOT EXISTS idx_players_external_id ON players(external_id);

        -- Create index on name for search if it doesn't exist
        CREATE INDEX IF NOT EXISTS idx_players_name ON players(name);

        -- Add team column if it doesn't exist
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='players' AND column_name='team'
            ) THEN
                ALTER TABLE players ADD COLUMN team VARCHAR(50);
                RAISE NOTICE 'Added team column to players table';
            END IF;
        END
        $$;

        -- Add position column if it doesn't exist
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='players' AND column_name='position'
            ) THEN
                ALTER TABLE players ADD COLUMN position VARCHAR(10);
                RAISE NOTICE 'Added position column to players table';
            END IF;
        END
        $$;

        -- Add created_at and updated_at if they don't exist
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='players' AND column_name='created_at'
            ) THEN
                ALTER TABLE players ADD COLUMN created_at TIMESTAMP DEFAULT NOW();
                RAISE NOTICE 'Added created_at column to players table';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='players' AND column_name='updated_at'
            ) THEN
                ALTER TABLE players ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
                RAISE NOTICE 'Added updated_at column to players table';
            END IF;
        END
        $$;

        -- Ensure games table has external_id
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='games' AND column_name='external_id'
            ) THEN
                ALTER TABLE games ADD COLUMN external_id VARCHAR(50);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_games_external_id ON games(external_id);
                RAISE NOTICE 'Added external_id column to games table';
            END IF;
        END
        $$;

        -- Add indexes for games if they don't exist
        CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);

        -- Add indexes for predictions if they don't exist
        CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_id);
        CREATE INDEX IF NOT EXISTS idx_predictions_game ON predictions(game_id);
        CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);

        -- Show current table structures
        SELECT 'Migration completed!' as status;

        -- Display player count
        SELECT 'Players in database: ' || COUNT(*) as info FROM players;

        -- Display game count
        UNION ALL
        SELECT 'Games in database: ' || COUNT(*) FROM games;

        -- Display prediction count
        UNION ALL
        SELECT 'Predictions in database: ' || COUNT(*) FROM predictions;
EOF

    log_info "Migration completed successfully!"
}

import_espn_ids() {
    log_warn ""
    log_warn "Do you want to import ESPN IDs for existing players?"
    log_warn "This requires running the data fetch script first."
    echo ""
    read -p "Import ESPN IDs now? (y/N): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Triggering ESPN player import..."

        curl -X POST "http://${REMOTE_HOST}:8001/api/data/fetch/players?limit=1000" 2>/dev/null || {
            log_warn "Could not trigger import. Make sure the API is running."
        }
    fi
}

#####################################################################
# Main
#####################################################################

main() {
    log_info "Database Migration for NBA Sports API"
    echo ""
    log_info "Database: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
    echo ""

    if ! check_db_connection; then
        log_error "Migration aborted: Cannot connect to database"
        exit 1
    fi

    if check_column_exists; then
        log_warn "external_id column already exists in players table"
        echo ""
        read -p "Continue with migration anyway? (y/N): " -n 1 -r
        echo ""

        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Migration cancelled"
            exit 0
        fi
    fi

    # Confirm migration
    echo ""
    read -p "Run migration now? (y/N): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Migration cancelled"
        exit 0
    fi

    run_migration
    import_espn_ids

    echo ""
    log_info "Done! You can now use the new endpoints:"
    echo "  GET  /api/players/search?name=<name>"
    echo "  GET  /api/predictions/player/espn/{espn_id}"
}

main
