#!/usr/bin/env python3
"""
NBA Injury Report Scraper using Firecrawl.

Scrapes injury data from ESPN and stores in the database.
This should be run before generating predictions.

Usage:
    python scripts/scrape_nba_injuries.py
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player, PlayerInjury
import httpx
import re
import json


class NBAInjuryScraper:
    """Scrape NBA injury data from ESPN using Firecrawl."""

    FIRECRAWL_URL = "http://localhost:3002/v1/scrape"
    ESPN_INJURIES_URL = "https://www.espn.com/nba/injuries"

    def __init__(self, db_session):
        self.db = db_session

    async def scrape_with_firecrawl(self, url: str) -> str:
        """Scrape a URL using self-hosted Firecrawl."""
        payload = {
            "url": url,
            "formats": ["markdown"]
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.FIRECRAWL_URL,
                json=payload,
                timeout=60.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('data', {}).get('markdown', '')
                else:
                    error = data.get('error', 'Unknown error')
                    raise Exception(f"Firecrawl error: {error}")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

    def parse_espn_injuries(self, markdown: str) -> list:
        """Parse injury data from ESPN markdown."""
        injuries = []

        # Split by lines
        lines = markdown.split('\n')

        current_section = None
        current_injuries = []

        for i, line in enumerate(lines):
            # Look for team sections (e.g., "### Boston Celtics")
            team_match = re.match(r'###\s+(.+?)\s+\((\w+)\)', line)
            if team_match:
                # Save previous team's injuries
                if current_section and current_injuries:
                    injuries.extend(current_injuries)
                    current_injuries = []

                current_section = {
                    'team_name': team_match.group(1).strip(),
                    'team_abbr': team_match.group(2),
                    'injuries': []
                }
                continue

            # Look for player names (bold text pattern)
            # ESPN markdown often uses **Player Name** format
            player_match = re.match(r'\*\*(.+?)\*\*', line)
            if player_match and current_section:
                player_name = player_match.group(1).strip()

                # Look ahead for injury details
                injury_details = ""
                status = "Questionable"  # default

                # Check next few lines for injury info
                for j in range(i+1, min(i+5, len(lines))):
                    next_line = lines[j].strip()
                    if next_line:
                        # Look for status keywords
                        if any(word in next_line.lower() for word in ['out', 'injury', 'day-to-day', 'questionable', 'week-to-week', 'month-to-month']):
                            injury_details = next_line

                            # Determine status
                            if 'out' in next_line.lower() and 'indefinitely' in next_line.lower():
                                status = "Out Indefinitely"
                            elif 'out' in next_line.lower():
                                status = "Out"
                            elif 'day-to-day' in next_line.lower():
                                status = "Day-To-Day"
                            elif 'questionable' in next_line.lower():
                                status = "Questionable"
                            elif 'week-to-week' in next_line.lower():
                                status = "Week-To-Week"
                            elif 'month-to-month' in next_line.lower():
                                status = "Month-To-Month"

                            break

                # Try to extract injury type from details
                injury_type = "Unknown"
                if injury_details:
                    # Common injury patterns
                    patterns = [
                        (r'(ankle|foot|knee|hamstring|quad|groin|hip|wrist|finger|thumb|shoulder|elbow|concussion|back|neck)', 'lower'),
                        (r'(Achilles|ACL|MCL|sprain|strain|fracture|break|tear)', 'lower'),
                    ]

                    for pattern, _ in patterns:
                        match = re.search(pattern, injury_details, re.IGNORECASE)
                        if match:
                            injury_type = match.group(1).capitalize()
                            break

                current_injuries.append({
                    'player_name': player_name,
                    'team_abbr': current_section['team_abbr'],
                    'injury_type': injury_type,
                    'status': status,
                    'details': injury_details
                })

        # Add last team's injuries
        if current_section and current_injuries:
            injuries.extend(current_injuries)

        return injuries

    def store_injuries(self, injuries: list) -> dict:
        """Store parsed injuries in database."""
        created = 0
        updated = 0
        errors = 0

        for injury_data in injuries:
            try:
                player_name = injury_data.get('player_name', '')
                team_abbr = injury_data.get('team_abbr', '')

                # Find player in database
                player = self.db.query(Player).filter(
                    Player.name == player_name,
                    Player.team == team_abbr
                ).first()

                if not player:
                    # Try name match without team
                    player = self.db.query(Player).filter(
                        Player.name == player_name
                    ).first()

                if player:
                    # Check if injury already exists
                    existing = self.db.query(PlayerInjury).filter(
                        PlayerInjury.player_id == player.id,
                        PlayerInjury.status == injury_data['status']
                    ).first()

                    injury_data['impact_description'] = injury_data.get('details', '')

                    if existing:
                        # Update existing
                        existing.injury_type = injury_data['injury_type']
                        existing.impact_description = injury_data['impact_description']
                        existing.updated_at = datetime.now(timezone.utc)
                        updated += 1
                    else:
                        # Create new injury record
                        injury = PlayerInjury(
                            id=str(uuid4()),
                            player_id=player.id,
                            injury_type=injury_data['injury_type'],
                            status=injury_data['status'],
                            impact_description=injury_data['impact_description'],
                            reported_date=datetime.now(timezone.utc).date(),
                            external_source='espn_firecrawl',
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        self.db.add(injury)
                        created += 1

            except Exception as e:
                errors += 1
                print(f"Error processing {injury_data}: {e}")

        self.db.commit()

        return {
            'created': created,
            'updated': updated,
            'errors': errors,
            'total': created + updated
        }


async def main():
    """Main scraping function."""
    print("🏥 NBA INJURY REPORT SCRAPER")
    print("=" * 70)
    print()

    db = SessionLocal()
    try:
        scraper = NBAInjuryScraper(db)

        # Scrape ESPN injuries page
        print(f"📡 Scraping {scraper.ESPN_INJURIES_URL}...")
        markdown = await scraper.scrape_with_firecrawl(scraper.ESPN_INJURIES_URL)

        if not markdown:
            print("❌ No content scraped")
            return

        print(f"✅ Scraped {len(markdown)} characters")

        # Save raw markdown for debugging
        with open('/tmp/espn_injuries_raw.md', 'w') as f:
            f.write(markdown)
        print("💾 Saved raw markdown to /tmp/espn_injuries_raw.md")

        # Parse injuries
        print()
        print("🔍 Parsing injury data...")
        injuries = scraper.parse_espn_injuries(markdown)

        if injuries:
            print(f"✅ Found {len(injuries)} potential injuries")
            print()

            # Show preview
            print("📋 INJURY DATA PREVIEW:")
            print("-" * 70)
            for injury in injuries[:10]:
                print(f"  {injury['player_name']:<20s} ({injury['team_abbr']:3s}) "
                      f"- {injury['injury_type']:<20s} [{injury['status']}]")

            if len(injuries) > 10:
                print(f"  ... and {len(injuries) - 10} more")

            print()
            print("💾 Storing in database...")
            result = scraper.store_injuries(injuries)

            print()
            print("=" * 70)
            print("✅ INJURY SCRAPE COMPLETE")
            print("=" * 70)
            print(f"Created: {result['created']}")
            print(f"Updated: {result['updated']}")
            print(f"Errors: {result['errors']}")
            print(f"Total processed: {result['total']}")
        else:
            print("❌ No injuries found in scraped data")

            # Show sample of scraped content
            print()
            print("📋 SCRAPED CONTENT PREVIEW:")
            print("-" * 70)
            print(markdown[:1000])
            print("...")

    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
