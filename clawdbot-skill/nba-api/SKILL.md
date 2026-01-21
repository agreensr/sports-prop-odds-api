---
name: nba-api
description: "**NBA ONLY** - Get NBA player prop predictions with official NBA.com data integration"
homepage: http://89.117.150.95:8001/docs
metadata: {"clawdbot":{"emoji":"🏀","requires":{"anyBins":["python3"]},"env":["NBA_API_URL"]}}
---

# NBA API - NBA Player Prop Predictions

Get AI-powered **NBA basketball** player prop predictions via this skill.

## Setup

1. Set API URL in environment:
   ```bash
   export NBA_API_URL="http://89.117.150.95:8001"
   ```

2. Make script executable:
   ```bash
   chmod +x scripts/nba_client.py
   ```

## Commands

### Health Check
```bash
scripts/nba_client.py health
```
Returns API status and database counts.

### Player Predictions by Name
```bash
scripts/nba_client.py player <name>
```
Search for a player by name and get their predictions.
Example: `scripts/nba_client.py player lebron`

### Player Predictions by NBA ID
```bash
scripts/nba_client.py player_nba <nba_id>
```
Get predictions for a player using their NBA.com ID.
Example: `scripts/nba_client.py player_nba 2544`

### Game Predictions
```bash
scripts/nba_client.py game <game_id>
```
Get predictions for a specific game.
Example: `scripts/nba_client.py game 0022400123`

### Top Picks
```bash
scripts/nba_client.py top_picks [min_confidence]
```
Get high-confidence predictions (default 60%).
Example: `scripts/nba_client.py top_picks 0.7`

### Search Players
```bash
scripts/nba_client.py search <name>
```
Search for players by name.
Example: `scripts/nba_client.py search curry`

### Fetch Upcoming Games
```bash
scripts/nba_client.py fetch_upcoming [days]
```
Fetch upcoming games from NBA.com (default 7 days).
Example: `scripts/nba_client.py fetch_upcoming 7`

### Data Status
```bash
scripts/nba_client.py status
```
Get database statistics and counts.

## Data Sources

- **Player Data**: NBA.com (via `nba_api` library)
- **Game Schedule**: NBA.com
- **Betting Odds**: The Odds API (bookmaker lines and pricing)

## Examples

```bash
# Check if LeBron is in database
./scripts/nba_client.py search lebron

# Get LeBron's predictions by NBA ID
./scripts/nba_client.py player_nba 2544

# Get top picks at 70% confidence
./scripts/nba_client.py top_picks 0.7

# Fetch upcoming games
./scripts/nba_client.py fetch_upcoming 7
```
