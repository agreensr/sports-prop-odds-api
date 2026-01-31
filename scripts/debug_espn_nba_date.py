"""Debug ESPN NBA API for specific date to understand data mismatch."""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx


async def debug_espn_for_date(target_date: str = None):
    """
    Check ESPN API for a specific date.

    Args:
        target_date: Date string in YYYYMMdd format. If None, uses today.
    """
    if not target_date:
        target_date = datetime.now().strftime('%Y%m%d')

    print(f"Fetching ESPN NBA data for {target_date}...")
    print(f"URL: https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={target_date}")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={target_date}"
        )
        response.raise_for_status()
        data = response.json()

    events = data.get('events', [])
    print(f"Total events: {len(events)}")
    print()

    for event in events:
        name = event.get('name', 'N/A')
        short_name = event.get('shortName', 'N/A')
        date_str = event.get('date', 'N/A')

        # Parse the date
        if date_str and date_str != 'N/A':
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                utc_time = dt.strftime('%Y-%m-%d %H:%M:%S %Z')

                # Convert to EST (UTC-5)
                est_time = (dt - timedelta(hours=5)).strftime('%Y-%m-%d %I:%M %p EST')
            except:
                utc_time = date_str
                est_time = "Parse error"
        else:
            utc_time = 'N/A'
            est_time = 'N/A'

        # Get competition details
        competitions = event.get('competitions', [])
        if competitions:
            comp = competitions[0]
            competitors = comp.get('competitors', [])

            home_team = None
            away_team = None
            for comp_team in competitors:
                team = comp_team.get('team', {})
                abbr = team.get('abbreviation', '???')
                if comp_team.get('homeAway') == 'home':
                    home_team = abbr
                else:
                    away_team = abbr

            print(f"  {away_team} @ {home_team}")
            print(f"    ESPN Name: {name}")
            print(f"    UTC: {utc_time}")
            print(f"    EST: {est_time}")
            print()

    # Also check surrounding dates
    print("\n" + "="*60)
    print("Checking surrounding dates...")
    print("="*60)

    base = datetime.strptime(target_date, '%Y%m%d')

    for offset in [-2, -1, 0, 1, 2]:
        check_date = (base + timedelta(days=offset)).strftime('%Y%m%d')
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={check_date}"
            )
            response.raise_for_status()
            data = response.json()

        events = data.get('events', [])
        print(f"\n{check_date}: {len(events)} games")

        for event in events[:3]:  # Show first 3
            name = event.get('name', 'N/A')
            date_str = event.get('date', 'N/A')
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    est_time = (dt - timedelta(hours=5)).strftime('%I:%M %p EST')
                except:
                    est_time = '???'
            print(f"  - {name} ({est_time})")


if __name__ == '__main__':
    # Check for today (2026-01-31 based on system date)
    asyncio.run(debug_espn_for_date())
