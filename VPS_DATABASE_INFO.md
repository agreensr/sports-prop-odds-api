# VPS Database Configuration

**Last Updated**: 2026-01-26

## PostgreSQL Connection Details

### Docker Container
- **Container Name**: `nba-postgres`
- **Image**: `postgres:15-alpine`
- **Status**: Running (auto-restart on boot)
- **Port Mapping**: `0.0.0.0:5433 → 5432/tcp`
  - External (host): **5433**
  - Internal (container): 5432

### Connection String
```
postgresql://postgres:nba_secure_pass_2026@localhost:5433/nba_props
```

### Environment Variables (.env)
```bash
DATABASE_URL=postgresql://postgres:nba_secure_pass_2026@localhost:5433/nba_props
CURRENT_SEASON=2025-26
THE_ODDS_API_KEY=
LOG_LEVEL=INFO
```

## VPS Access

### SSH Connection
```bash
ssh sean@sean-ubuntu-vps
```

### API Endpoints
- **Root**: http://89.117.150.95:8001
- **Docs**: http://89.117.150.95:8001/docs
- **Health**: http://89.117.150.95:8001/api/health

### Application Path
```
~/sports-bet-ai-api/
```

## Database Management

### Direct PostgreSQL Access
```bash
# Connect via Docker
docker exec -it nba-postgres psql -U postgres nba_props

# List all databases
docker exec nba-postgres psql -U postgres -c "\l"

# List tables in nba_props
docker exec nba-postgres psql -U postgres nba_props -c "\dt"

# Backup database
docker exec nba-postgres pg_dump -U postgres nba_props > backup.sql

# Restore database
docker exec -i nba-postgres psql -U postgres nba_props < backup.sql
```

### Service Management
```bash
# Start API service
cd ~/sports-bet-ai-api
bash start_api.sh

# Stop API service
pkill -9 -f "uvicorn app.main:app"
sudo lsof -ti:8001 | xargs -r sudo kill -9

# View logs
tail -f ~/sports-bet-ai-api/uvicorn.log

# Restart PostgreSQL container
docker restart nba-postgres
```

## Database Schema

### Key Tables
| Table | Purpose | Records (as of 2026-01-26) |
|-------|---------|---------------------------|
| `players` | NBA player data | 768 |
| `games` | NBA games | 2,151 |
| `predictions` | Player prop predictions | 8,002 |
| `player_season_stats` | Per-36 player stats | 768 |
| `player_injuries` | Injury reports | 1 |
| `expected_lineups` | Projected lineups | 687 |
| `odds_snapshots` | Historical odds data | 0 |
| `player_aliases` | Player name matching | 556 |

### Important Fields

#### players Table
- `id` (UUID, PK)
- `nba_api_id` (int) - Links to nba_api PLAYER_ID
- `name`, `team`, `position`, `jersey_number`
- `height`, `weight`, `birth_date`
- `created_at`, `updated_at`

#### player_season_stats Table
- `id` (UUID, PK)
- `player_id` (FK to players)
- `season` (e.g., "2025-26")
- `points_per_36`, `rebounds_per_36`, `assists_per_36`
- `threes_per_36`, `avg_minutes`
- `games_count`
- `fetched_at`, `created_at`, `updated_at`

## Deployment

### Quick Deploy
```bash
./deploy_vps.sh
```

### Manual Deploy Steps
1. Stop existing service
2. Deploy files via rsync
3. Install dependencies
4. Kill processes on port 8001
5. Start service via start_api.sh

## Troubleshooting

### Port Already in Use
```bash
sudo lsof -ti:8001 | xargs -r sudo kill -9
```

### Database Connection Failed
```bash
# Check PostgreSQL is running
docker ps | grep nba-postgres

# Test connection
docker exec nba-postgres psql -U postgres -c "SELECT 1;"

# Check port mapping
docker port nba-postgres
```

### Password Authentication Failed
- Verify `.env` file has correct password: `nba_secure_pass_2026`
- Ensure port is **5433**, not 5432
- Restart service to pick up new environment variables

## Important Notes

1. **Port is 5433**: Due to Docker port mapping, the database is accessible on port 5433 (host), not 5432 (container internal)

2. **Password**: `nba_secure_pass_2026` (NOT `postgres`)

3. **Season**: Always use `2025-26` for current season data. DO NOT fetch 2024-25 data.

4. **Auto-sync**: The system automatically syncs data from:
   - nba_api (player stats, games, lineups)
   - The Odds API (betting odds)

5. **Player Matching**: The `player_aliases` table must be populated for PlayerResolver to work correctly. Use `scripts/populate_player_aliases.py` if needed.
