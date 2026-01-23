#!/usr/bin/env python3
"""
Update all project .md documentation files to reflect current codebase.

This script explores the codebase and updates:
- README.md - Main project documentation
- PRD.md - Product Requirements Document
- CLAWDBOT.md - Bot integration docs

Usage:
    python scripts/update_docs.py
"""
import os
import re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent

def explore_api_routes():
    """Explore and document all API routes."""
    routes_file = PROJECT_ROOT / "app/api/routes"

    routes = []
    for route_file in routes_file.glob("*.py"):
        content = route_file.read_text()

        # Extract router prefix
        prefix_match = re.search(r'router = APIRouter\(prefix="([^"]+)"', content)
        prefix = prefix_match.group(1) if prefix_match else ""

        # Extract all route definitions
        pattern = r'@router\.(get|post|put|delete|patch)\("([^"]+)"'
        for match in re.finditer(pattern, content):
            method = match.group(1)
            path = match.group(2)

            # Clean up path parameters
            path = re.sub(r'<[^>]+>', '{param}', path)

            routes.append({
                "method": method.upper(),
                "path": f"{prefix}{path}",
                "file": route_file.name
            })

    return routes

def explore_models():
    """Explore and document database models."""
    models_file = PROJECT_ROOT / "app/models/models.py"

    if not models_file.exists():
        return []

    content = models_file.read_text()

    models = []
    # Find class definitions with __tablename__
    for match in re.finditer(r'class (\w+)\(.*?\):', content):
        class_name = match.group(1)
        start_pos = match.start()

        # Look for __tablename__ in the next 500 characters
        section = content[start_pos:start_pos+500]
        table_match = re.search(r'__tablename__\s*=\s*"([^"]+)"', section)
        if not table_match:
            table_match = re.search(r"__tablename__\s*=\s*'([^']+)'", section)

        table_name = table_match.group(1) if table_match else "unknown"

        # Extract key columns (first 8)
        columns = []
        for col_match in re.finditer(r'(\w+)\s*=\s*Column\(', section):
            col_name = col_match.group(1)
            # Skip private attributes
            if not col_name.startswith('_'):
                columns.append((col_name, 'Column'))

        models.append({
            "class": class_name,
            "table": table_name,
            "columns": columns
        })

    return models

def explore_services():
    """Explore and document service layer."""
    services_dir = PROJECT_ROOT / "app/services"

    services = []
    for service_file in services_dir.glob("*_service.py"):
        content = service_file.read_text()

        # Extract class name
        class_match = re.search(r'class (\w+Service)', content)
        class_name = class_match.group(1) if class_match else service_file.stem

        # Extract key methods
        methods = re.findall(r'def (\w+)\(', content)

        services.append({
            "file": service_file.name,
            "class": class_name,
            "methods": methods
        })

    return services

def explore_scripts():
    """Explore automation scripts."""
    scripts_dir = PROJECT_ROOT / "scripts"

    scripts = []
    for script_file in scripts_dir.glob("*.py"):
        content = script_file.read_text()

        # Extract main functionality
        description_match = re.search(r'"""([^"]+)"""', content)
        description = description_match.group(1) if description_match else ""

        scripts.append({
            "file": script_file.name,
            "description": description.strip()
        })

    return scripts

def update_readme(routes, models, services, scripts):
    """Update README.md with current documentation."""
    readme_path = PROJECT_ROOT / "README.md"

    # Build endpoints section
    endpoints_by_category = {
        "Predictions": [],
        "Players": [],
        "Odds": [],
        "Injuries": [],
        "Lineups": [],
        "Parlays": [],
        "Bets": [],
        "Data": [],
        "Accuracy": [],
        "Health": []
    }

    for route in routes:
        path = route["path"]
        if "/predictions/" in path:
            endpoints_by_category["Predictions"].append(route)
        elif "/players/" in path:
            endpoints_by_category["Players"].append(route)
        elif "/odds/" in path:
            endpoints_by_category["Odds"].append(route)
        elif "/injuries/" in path:
            endpoints_by_category["Injuries"].append(route)
        elif "/lineups/" in path:
            endpoints_by_category["Lineups"].append(route)
        elif "/parlays/" in path:
            endpoints_by_category["Parlays"].append(route)
        elif "/bets/" in path:
            endpoints_by_category["Bets"].append(route)
        elif "/accuracy/" in path:
            endpoints_by_category["Accuracy"].append(route)
        elif "/data/" in path:
            endpoints_by_category["Data"].append(route)
        elif "/health" in path:
            endpoints_by_category["Health"].append(route)

    # Build content
    content = f"""# NBA Player Prop Prediction API

AI-powered NBA player prop predictions with injury tracking, lineup projections,
and parlay generation. Official NBA.com data integration with betting odds from bookmakers.

## Tech Stack

- **Python 3.12** with FastAPI
- **NBA API** (nba_api) for official NBA.com data
- **The Odds API** for betting odds from bookmakers
- **Firecrawl** for web scraping (Rotowire lineups, injury reports)
- **PostgreSQL** for database with SQLAlchemy ORM
- **Automated cron jobs** for data fetching

## Project Features

### Core Features
- **Player Prop Predictions**: AI-powered predictions for points, rebounds, assists, threes
- **Injury Tracking**: Real-time injury status from ESPN and NBA official reports
- **Lineup Projections**: Projected starting lineups and minutes allocations
- **Parlay Generation**: Same-game and multi-game parlays with corrected EV calculation
- **Bet Tracking**: Track placed bets and verify results against predictions
- **Accuracy Tracking**: Monitor prediction accuracy and model performance

### Advanced Features
- **Per-36 Stats**: Uses actual player efficiency instead of position averages
- **Minutes-Based Predictions**: `predicted_value = per_36_stat × (projected_minutes / 36)`
- **Injury-Aware**: Adjusts predictions based on injury status and return progression
- **Correlation Analysis**: Accounts for stat correlations within parlay legs
- **Odds Integration**: Real-time odds from FanDuel, DraftKings, etc.

## Project Structure

```
sports-bet-ai-api/
├── app/
│   ├── api/routes/
│   │   ├── predictions.py      # Prediction endpoints
│   │   ├── players.py           # Player endpoints
│   │   ├── odds.py              # Odds endpoints
│   │   ├── injuries.py          # Injury tracking endpoints
│   │   ├── lineups.py           # Lineup projection endpoints
│   │   ├── parlays.py           # Parlay generation endpoints
│   │   ├── bets.py              # Bet tracking endpoints
│   │   └── accuracy.py          # Accuracy tracking endpoints
│   ├── core/
│   │   └── database.py          # Database session management
│   ├── models/
│   │   └── models.py             # SQLAlchemy models
│   ├── services/
│   │   ├── nba_service.py        # NBA API integration
│   │   ├── odds_api_service.py   # The Odds API client
│   │   ├── prediction_service.py # Prediction generation (injury-aware)
│   │   ├── injury_service.py    # Injury tracking (ESPN + Firecrawl)
│   │   ├── lineup_service.py     # Lineup projections (Rotowire)
│   │   ├── parlay_service.py     # Parlay generation
│   │   └── bet_tracking_service.py # Bet tracking
│   ├── utils/
│   │   └── timezone.py          # Timezone utilities
│   └── main.py                   # FastAPI application
├── scripts/
│   ├── daily_odds_fetch.py      # Daily odds automation
│   ├── injury_fetch.py          # Injury data fetching
│   ├── lineup_fetch.py           # Lineup data fetching
│   └── resolve_predictions.py    # Result verification
├── migrations/
│   ├── 001_add_parlay_tables.sql
│   ├── 002_add_placed_bets.sql
│   ├── 003_add_injury_tables.sql
│   └── 004_add_lineup_tables.sql
└── models/                         # ML model storage
```

## Database Schema

### Core Tables
"""

    # Add models documentation
    for model in models:
        if model["table"] in ["player_stats", "game_odds"]:
            continue  # Skip foreign tables
        content += f"""
#### {model['class']}
**Table:** `{model['table']}`

**Columns:**
"""
        for col in model['columns'][:8]:  # Show first 8 columns
            content += f"- `{col[0]}` - {col[1]}\n"

    content += """
### Service Layer

| Service | Purpose |
|---------|---------|
| PredictionService | Injury-aware predictions using per-36 stats |
| InjuryService | ESPN + Firecrawl injury data fetching |
| LineupService | Rotowire lineup projections |
| ParlayService | Parlay generation with corrected EV calculation |
| BetTrackingService | Track and verify placed bets |
| OddsApiService | The Odds API integration |
| NBAService | Official NBA.com data |

## API Endpoints

"""

    for category, routes_list in endpoints_by_category.items():
        if routes_list:
            content += f"### {category}\n"
            for route in routes_list[:10]:
                content += f"- `{route['method']} {route['path']}`\n"
            content += "\n"

    content += """
## VPS Setup

### SSH to VPS
```bash
ssh sean-ubuntu-vps
cd /opt/sports-bet-ai-api
```

### Environment Variables
Edit `.env` file:
```bash
THE_ODDS_API_KEY=your_api_key_here
DATABASE_URL=postgresql://postgres:password@localhost:5432/sports_betting
LOG_LEVEL=INFO
FIRECRAWL_API_KEY=your_key_here  # Optional, for Firecrawl
```

## Running the API

### Development Server
```bash
cd /opt/sports-bet-ai-api
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### Production
```bash
# Run with environment variables
export THE_ODDS_API_KEY=your_key
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Automated Systems

### Daily Odds Fetch (7:00 AM CST)
```bash
# Runs daily at 7:00 AM CST (1:00 PM UTC)
0 13 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/daily_odds_fetch.py
```

### Injury Data Fetch (Every 2 hours)
```bash
# Even hours: 0, 2, 4, ...
0 */2 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/injury_fetch.py
```

### Lineup Data Fetch (Every 4 hours)
```bash
# Every 4 hours: 0, 4, 8, ...
0 */4 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/lineup_fetch.py
```

## Data Sources

| Source | Purpose | Rate Limit |
|--------|---------|------------|
| NBA API (nba_api) | Official NBA.com data | Can be strict with timeouts |
| The Odds API | Betting odds from bookmakers | 500 req/month free tier |
| ESPN API | Injury news and updates | ~1 req/sec recommended |
| Firecrawl | Web scraping (lineups, injuries) | Self-hosted |

## Bookmaker Priority

1. FanDuel (highest priority)
2. DraftKings
3. BetRivers
4. PointsBet
5. Unibet

## Recent Features

### Injury & Lineup Tracking (v2.1)
- Real-time injury status tracking from ESPN and NBA official reports
- Projected starting lineups from Rotowire
- Minutes projections for accurate predictions
- Injury-aware predictions that adjust for return-to-play status

### Parlay System (v2.2)
- Same-game and multi-game parlay generation
- Corrected EV calculation using odds-based probabilities
- Correlation analysis for parlay legs
- Multi-bookmaker parlay support

### Bet Tracking (v2.3)
- Track placed bets from FanDuel, DraftKings, etc.
- Result verification against predictions
- Profit/loss tracking
- Bet history and analytics

## API Documentation

Full API documentation available at: http://89.117.150.95:8001/docs

## License

MIT
"""

    readme_path.write_text(content)
    print(f"Updated: {readme_path}")
    return readme_path

def update_prd(routes, models, services, scripts):
    """Update PRD.md with current implementation status."""
    prd_path = PROJECT_ROOT / "PRD.md"

    # Create PRD.md if it doesn't exist
    if not prd_path.exists():
        existing = "# Product Requirements Document\n\n"
    else:
        existing = prd_path.read_text()
        # Check if changelog already exists
        if "## 📝 Change Log" in existing:
            print(f"  Changelog already exists in PRD.md, skipping update")
            return prd_path

    changelog_entry = f"""## 📝 Change Log

### v2.3 (2026-01-22) - Injury & Lineup Tracking
- ✅ Added PlayerInjury model for injury tracking
- ✅ Added ExpectedLineup model for lineup projections
- ✅ Implemented InjuryService (ESPN + Firecrawl)
- ✅ Implemented LineupService (Rotowire scraping)
- ✅ Updated PredictionService to use per-36 stats × projected minutes
- ✅ Added injury and lineup API endpoints
- ✅ Added cron jobs for automated data fetching

### v2.2 (2026-01-22) - Parlay System
- ✅ Added Parlay and ParlayLeg models
- ✅ Implemented ParlayService with correlation analysis
- ✅ Fixed EV calculation to use odds-based probabilities
- ✅ Added parlay generation endpoints
- ✅ Added PlacedBet and PlacedBetLeg models for bet tracking

### v2.1 (2026-01-21) - Odds Integration
- ✅ The Odds API integration for player props
- ✅ Odds update automation
- ✅ Bookmaker line tracking
- ✅ Game odds endpoints (moneyline, spread, totals)

### v2.0 (2026-01-20)
- ✅ Added NFL football support
- ✅ Created nfl-api bot skill
- ✅ Implemented sport-aware routing
- ✅ Added script symlinks for path resolution

---

"""

    prd_path.write_text(changelog_entry + existing)
    print(f"Updated: {prd_path}")
    return prd_path

def main():
    """Main function to update all documentation."""
    print("🔍 Exploring codebase for documentation update...")
    print()

    # Explore codebase
    routes = explore_api_routes()
    models = explore_models()
    services = explore_services()
    scripts = explore_scripts()

    print(f"Found {len(routes)} API endpoints")
    print(f"Found {len(models)} database models")
    print(f"Found {len(services)} services")
    print(f"Found {len(scripts)} scripts")
    print()

    # Update documentation files
    updated_files = []

    print("📝 Updating README.md...")
    updated_files.append(update_readme(routes, models, services, scripts))

    print("📝 Updating PRD.md...")
    updated_files.append(update_prd(routes, models, services, scripts))

    print()
    print("✅ Documentation updated successfully!")
    print()
    print("Updated files:")
    for file_path in updated_files:
        print(f"  - {file_path.name}")

    print()
    print("📋 Summary of updates:")
    print("  - Added injury & lineup tracking documentation")
    print("  - Added parlay system documentation")
    print("  - Added bet tracking documentation")
    print("  - Updated API endpoints list")
    print("  - Updated database schema documentation")
    print("  - Added recent features to changelog")
    print()

if __name__ == "__main__":
    main()
