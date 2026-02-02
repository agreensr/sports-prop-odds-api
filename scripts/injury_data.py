#!/usr/bin/env python3
"""
NBA Injury Report Parser using ESPN data via web-reader.

Scrapes injury data from ESPN and stores in the database.
This should be run before generating predictions.

Usage:
    python scripts/injury_data.py
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import re

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player, PlayerInjury


def parse_injury_data(markdown: str) -> list:
    """
    Parse injury data from ESPN markdown format.

    Format: ![Image N](blob:... "Team Name")Team Name\n\n| NAME | POS | ... |
    """
    injuries = []

    # Team name to abbreviation mapping
    team_abbr_map = {
        'Atlanta Hawks': 'ATL',
        'Boston Celtics': 'BOS',
        'Brooklyn Nets': 'BKN',
        'Charlotte Hornets': 'CHA',
        'Chicago Bulls': 'CHI',
        'Cleveland Cavaliers': 'CLE',
        'Dallas Mavericks': 'DAL',
        'Denver Nuggets': 'DEN',
        'Detroit Pistons': 'DET',
        'Golden State Warriors': 'GSW',
        'Houston Rockets': 'HOU',
        'Indiana Pacers': 'IND',
        'LA Clippers': 'LAC',
        'Los Angeles Lakers': 'LAL',
        'Memphis Grizzlies': 'MEM',
        'Miami Heat': 'MIA',
        'Milwaukee Bucks': 'MIL',
        'Minnesota Timberwolves': 'MIN',
        'New Orleans Pelicans': 'NOP',
        'New York Knicks': 'NYK',
        'Oklahoma City Thunder': 'OKC',
        'Orlando Magic': 'ORL',
        'Philadelphia 76ers': 'PHI',
        'Phoenix Suns': 'PHX',
        'Portland Trail Blazers': 'POR',
        'Sacramento Kings': 'SAC',
        'San Antonio Spurs': 'SAS',
        'Toronto Raptors': 'TOR',
        'Utah Jazz': 'UTA',
        'Washington Wizards': 'WAS'
    }

    lines = markdown.split('\n')
    current_team = None
    current_team_abbr = None
    in_table = False

    for line in lines:
        # Look for team markers: ![Image N](... "Team Name")Team Name
        if 'Image' in line and '"Atl' in line or '"Bos' in line or '"Bro' in line or '"Cha' in line:
            team_match = re.search(r'"([A-Za-z\s]+?)"', line)
            if team_match:
                current_team = team_match.group(1).strip()
                current_team_abbr = team_abbr_map.get(current_team)
                in_table = False
                continue

        # Look for table header
        if '| NAME |' in line:
            in_table = True
            continue

        # Parse table rows
        if in_table and line.startswith('|') and 'NAME' not in line and '---' not in line:
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]

            if len(cells) >= 5 and current_team_abbr:
                player_name = cells[0]
                position = cells[1] if len(cells) > 1 else ''
                est_return = cells[2] if len(cells) > 2 else ''
                status = cells[3] if len(cells) > 3 else ''
                comment = cells[4] if len(cells) > 4 else ''

                # Clean up status
                status = status.strip()

                # Normalize status (use lowercase to match API filter expectations)
                if 'out' in status.lower() and 'day' not in status.lower():
                    if 'indefinitely' in status.lower():
                        status = "out"
                    else:
                        status = "out"
                elif 'day-to-day' in status.lower():
                    status = "day-to-day"
                elif 'questionable' in status.lower():
                    status = "questionable"

                # Extract injury type from comment
                injury_type = "Unknown"

                # Common injury patterns to look for
                patterns = [
                    (r'(knee|achilles|acl|mcl|foot|ankle|hamstring|groin|hip|wrist|finger|thumb|shoulder|elbow|toe|heel|back|neck|concussion|oblique)', re.I),
                    (r'(torn|sprain|strain|fracture|break|tear)', re.I),
                    (r'(illness|rest|conditioning)', re.I),
                    (r'(surgery|procedure)', re.I)
                ]

                for pattern, flags in patterns:
                    match = re.search(pattern, comment, flags)
                    if match:
                        injury_type = match.group(1).capitalize()
                        break

                injuries.append({
                    'player_name': player_name,
                    'team_abbr': current_team_abbr,
                    'position': position,
                    'est_return': est_return if est_return else None,
                    'status': status,
                    'injury_type': injury_type,
                    'comment': comment
                })

        # End of table
        if in_table and line.strip() == '':
            in_table = False

    return injuries


def store_injuries(db_session, injuries: list) -> dict:
    """Store parsed injuries in database."""
    created = 0
    updated = 0
    errors = 0
    not_found = []

    # Clear old injuries (ESPN is authoritative source)
    db_session.query(PlayerInjury).delete()

    for injury_data in injuries:
        try:
            player_name = injury_data.get('player_name', '')
            team_abbr = injury_data.get('team_abbr', '')

            # Find player in database
            player = db_session.query(Player).filter(
                Player.name == player_name,
                Player.team == team_abbr
            ).first()

            if not player:
                # Try name match only
                player = db_session.query(Player).filter(
                    Player.name == player_name
                ).first()

            if player:
                # Create new injury record (we cleared all at the start)
                injury = PlayerInjury(
                    id=str(uuid4()),
                    player_id=player.id,
                    injury_type=injury_data['injury_type'],
                    status=injury_data['status'],
                    impact_description=injury_data.get('comment', ''),
                    reported_date=datetime.now(timezone.utc).date(),
                    external_source='espn_web_reader',
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db_session.add(injury)
                created += 1
            else:
                not_found.append(player_name)
                errors += 1

        except Exception as e:
            errors += 1
            print(f"Error processing {injury_data}: {e}")

    db_session.commit()

    return {
        'created': created,
        'updated': updated,
        'errors': errors,
        'total': created + updated,
        'not_found': not_found
    }


async def main():
    """Main function to scrape and store injuries."""
    # Read ESPN data from file (fetched via web-reader MCP)
    data_file = Path(__file__).parent / "espn_injuries_data.txt"

    if not data_file.exists():
        print(f"Error: {data_file} not found. Please fetch ESPN data first.")
        return

    with open(data_file, 'r') as f:
        espn_injury_data = f.read()

    db = SessionLocal()
    try:
        print("PARSING ESPN NBA INJURY REPORT")
        print("=" * 70)
        print()

        # Parse injuries
        injuries = parse_injury_data(espn_injury_data)

        if not injuries:
            print("No injuries found")
            return

        print(f"Parsed {len(injuries)} injury entries")
        print()

        # Store in database
        print("Storing in database...")
        result = store_injuries(db, injuries)

        print()
        print("=" * 70)
        print("INJURY UPDATE COMPLETE")
        print("=" * 70)
        print(f"Created: {result['created']}")
        print(f"Updated: {result['updated']}")
        print(f"Total: {result['total']}")
        print()

        if result['not_found']:
            print(f"Players not found in database ({len(result['not_found'])}):")
            for name in result['not_found'][:10]:
                print(f"  - {name}")
            if len(result['not_found']) > 10:
                print(f"  ... and {len(result['not_found']) - 10} more")
            print()

        # Show summary by team
        from collections import defaultdict
        by_team = defaultdict(list)

        for injury in injuries:
            by_team[injury['team_abbr']].append(injury)

        print("INJURY SUMMARY BY TEAM")
        print("-" * 70)

        # Sort by total injuries (descending)
        sorted_teams = sorted(by_team.items(), key=lambda x: len(x[1]), reverse=True)

        for team_abbr, team_injuries in sorted_teams[:15]:
            team_name_map = {
                'ATL': 'Hawks', 'BOS': 'Celtics', 'BKN': 'Nets',
                'CHA': 'Hornets', 'CHI': 'Bulls', 'CLE': 'Cavaliers',
                'DAL': 'Mavericks', 'DEN': 'Nuggets', 'DET': 'Pistons',
                'GSW': 'Warriors', 'HOU': 'Rockets', 'IND': 'Pacers',
                'LAC': 'Clippers', 'LAL': 'Lakers', 'MEM': 'Grizzlies',
                'MIA': 'Heat', 'MIL': 'Bucks', 'MIN': 'Timberwolves',
                'NOP': 'Pelicans', 'NYK': 'Knicks', 'OKC': 'Thunder',
                'ORL': 'Magic', 'PHI': '76ers', 'POR': 'Trail Blazers',
                'SAC': 'Kings', 'SAS': 'Spurs', 'TOR': 'Raptors',
                'UTA': 'Jazz', 'WAS': 'Wizards'
            }

            team_name = team_name_map.get(team_abbr, team_abbr)

            # Count by status
            out_count = len([i for i in team_injuries if 'out' in i['status'].lower() and 'day' not in i['status'].lower()])
            dtd_count = len([i for i in team_injuries if 'day-to-day' in i['status'].lower()])

            print(f"\n{team_abbr} - {team_name}")
            print(f"  Out: {out_count} | Day-To-Day: {dtd_count}")

            # Show key injuries
            key_players = [i for i in team_injuries if 'out' in i['status'].lower() and 'day' not in i['status'].lower()][:5]
            if key_players:
                print(f"  Key injuries:")
                for i in key_players:
                    print(f"    * {i['player_name']}: {i['injury_type']} ({i['status']})")

    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
