#!/usr/bin/env python3
"""
Add sample NHL players for testing predictions.

This creates placeholder players for each team so the prediction service
can generate predictions.
"""
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.nhl.models import Player, Team, Game, PlayerSeasonStats

# Sample players for each team (key: goals, assists, points, shots)
SAMPLE_PLAYERS = {
    "ANA": [
        {"name": "Terry Terry", "position": "C", "goals": 0.3, "assists": 0.4, "points": 0.7, "shots": 3.2},
        {"name": "Alex Killorn", "position": "LW", "goals": 0.25, "assists": 0.3, "points": 0.55, "shots": 2.8},
    ],
    "BOS": [
        {"name": "David Pastrnak", "position": "RW", "goals": 0.55, "assists": 0.45, "points": 1.0, "shots": 6.5},
        {"name": "Brad Marchand", "position": "C", "goals": 0.35, "assists": 0.5, "points": 0.85, "shots": 4.2},
    ],
    "CBJ": [
        {"name": "Johnny Gaudreau", "position": "C", "goals": 0.28, "assists": 0.42, "points": 0.7, "shots": 3.5},
    ],
    "COL": [
        {"name": "Nathan MacKinnon", "position": "C", "goals": 0.45, "assists": 0.45, "points": 0.9, "shots": 5.0},
        {"name": "Mikko Rantanen", "position": "C", "goals": 0.38, "assists": 0.52, "points": 0.9, "shots": 4.8},
    ],
    "DET": [
        {"name": "Dylan Larkin", "position": "C", "goals": 0.32, "assists": 0.38, "points": 0.7, "shots": 3.8},
    ],
    "EDM": [
        {"name": "Connor McDavid", "position": "C", "goals": 0.50, "assists": 0.60, "points": 1.1, "shots": 6.0},
        {"name": "Leon Draisaitl", "position": "C", "goals": 0.42, "assists": 0.55, "points": 0.97, "shots": 5.2},
    ],
    "FLA": [
        {"name": "Matthew Tkachuk", "position": "LW", "goals": 0.40, "assists": 0.35, "points": 0.75, "shots": 4.5},
        {"name": "Sam Reinhart", "position": "C", "goals": 0.35, "assists": 0.40, "points": 0.75, "shots": 4.0},
    ],
    "LA": [
        {"name": "Kevin Fiala", "position": "C", "goals": 0.25, "assists": 0.35, "points": 0.6, "shots": 3.5},
        {"name": "Adrian Kempe", "position": "C", "goals": 0.30, "assists": 0.30, "points": 0.6, "shots": 3.2},
    ],
    "MIN": [
        {"name": "Kirill Kaprizov", "position": "RW", "goals": 0.42, "assists": 0.38, "points": 0.8, "shots": 4.8},
        {"name": "Mats Zuccarello", "position": "LW", "goals": 0.30, "assists": 0.40, "points": 0.7, "shots": 3.8},
    ],
    "MTL": [
        {"name": "Nick Suzuki", "position": "C", "goals": 0.32, "assists": 0.38, "points": 0.7, "shots": 3.8},
        {"name": "Cole Caufield", "position": "RW", "goals": 0.35, "assists": 0.25, "points": 0.6, "shots": 4.2},
    ],
    "NJD": [
        {"name": "Nico Hischier", "position": "C", "goals": 0.28, "assists": 0.35, "points": 0.63, "shots": 3.6},
    ],
    "NYI": [
        {"name": "Mathew Barzal", "position": "C", "goals": 0.30, "assists": 0.40, "points": 0.7, "shots": 3.8},
    ],
    "NYR": [
        {"name": "Artemi Panarin", "position": "RW", "goals": 0.38, "assists": 0.42, "points": 0.8, "shots": 4.5},
        {"name": "Mika Zibanejad", "position": "C", "goals": 0.32, "assists": 0.40, "points": 0.72, "shots": 4.0},
    ],
    "OTT": [
        {"name": "Tim Stutzle", "position": "C", "goals": 0.35, "assists": 0.40, "points": 0.75, "shots": 4.0},
    ],
    "PHI": [
        {"name": "Travis Konecny", "position": "RW", "goals": 0.40, "assists": 0.35, "points": 0.75, "shots": 4.2},
        {"name": "Sean Couturier", "position": "C", "goals": 0.28, "assists": 0.32, "points": 0.6, "shots": 3.5},
    ],
    "PIT": [
        {"name": "Sidney Crosby", "position": "C", "goals": 0.32, "assists": 0.40, "points": 0.72, "shots": 3.8},
    ],
    "TOR": [
        {"name": "Auston Matthews", "position": "C", "goals": 0.60, "assists": 0.35, "points": 0.95, "shots": 6.0},
        {"name": "Mitch Marner", "position": "C", "goals": 0.28, "assists": 0.50, "points": 0.78, "shots": 4.2},
    ],
    "VAN": [
        {"name": "Quinn Hughes", "position": "D", "goals": 0.15, "assists": 0.55, "points": 0.7, "shots": 3.0},
        {"name": "Elias Pettersson", "position": "C", "goals": 0.32, "assists": 0.40, "points": 0.72, "shots": 4.0},
    ],
    "VGK": [
        {"name": "Jack Eichel", "position": "C", "goals": 0.38, "assists": 0.42, "points": 0.8, "shots": 4.5},
        {"name": "Jonathan Marchessault", "position": "C", "goals": 0.30, "assists": 0.35, "points": 0.65, "shots": 3.8},
    ],
    "WSH": [
        {"name": "Alex Ovechkin", "position": "LW", "goals": 0.50, "assists": 0.25, "points": 0.75, "shots": 6.0},
        {"name": "Nicklas Backstrom", "position": "C", "goals": 0.22, "assists": 0.45, "points": 0.67, "shots": 3.6},
    ],
    "WPG": [
        {"name": "Kyle Connor", "position": "RW", "goals": 0.38, "assists": 0.35, "points": 0.73, "shots": 4.6},
        {"name": "Mark Scheifele", "position": "C", "goals": 0.32, "assists": 0.38, "points": 0.70, "shots": 4.0},
    ],
    # Add basic players for other teams
    "BUF": [{"name": "Tage Thompson", "position": "C", "goals": 0.32, "assists": 0.38, "points": 0.7, "shots": 3.8}],
    "CAR": [{"name": "Sebastian Aho", "position": "C", "goals": 0.30, "assists": 0.42, "points": 0.72, "shots": 4.0}],
    "CHI": [{"name": "Connor Bedard", "position": "C", "goals": 0.28, "assists": 0.35, "points": 0.63, "shots": 3.5}],
    "DAL": [{"name": "Jason Robertson", "position": "C", "goals": 0.32, "assists": 0.38, "points": 0.7, "shots": 3.8}],
    "NSH": [{"name": "Filip Forsberg", "position": "C", "goals": 0.30, "assists": 0.35, "points": 0.65, "shots": 3.6}],
    "SJS": [{"name": "Tomas Hertl", "position": "C", "goals": 0.35, "assists": 0.35, "points": 0.70, "shots": 3.8}],
    "STL": [{"name": "Brayden Schenn", "position": "C", "goals": 0.28, "assists": 0.32, "points": 0.60, "shots": 3.6}],
    "TBL": [{"name": "Nikita Kucherov", "position": "RW", "goals": 0.42, "assists": 0.35, "points": 0.77, "shots": 4.8}],
    "CBJ": [  # Re-add to fix
        {"name": "Johnny Gaudreau", "position": "C", "goals": 0.28, "assists": 0.42, "points": 0.7, "shots": 3.5},
        {"name": "Zach Werenski", "position": "D", "goals": 0.12, "assists": 0.28, "points": 0.4, "shots": 2.5},
    ],
    "NYR": [  # Add more
        {"name": "Artemi Panarin", "position": "RW", "goals": 0.38, "assists": 0.42, "points": 0.8, "shots": 4.5},
        {"name": "Mika Zibanejad", "position": "C", "goals": 0.32, "assists": 0.40, "points": 0.72, "shots": 4.0},
        {"name": "Adam Fox", "position": "D", "goals": 0.10, "assists": 0.40, "points": 0.5, "shots": 2.2},
    ],
    "SJS": [  # Add more
        {"name": "Tomas Hertl", "position": "C", "goals": 0.35, "assists": 0.35, "points": 0.70, "shots": 3.8},
        {"name": "Erik Karlsson", "position": "D", "goals": 0.12, "assists": 0.45, "points": 0.57, "shots": 2.8},
    ],
}

def add_sample_players():
    """Add sample players for testing."""
    db = next(get_db())

    # Current season
    current_season = 2025

    # Get all teams
    teams = db.query(Team).all()

    added_count = 0
    stats_count = 0
    for team in teams:
        abbr = team.abbreviation

        # Skip if team already has players
        existing = db.query(Player).filter(Player.team == abbr).count()
        if existing > 0:
            # Check for existing season stats
            existing_players = db.query(Player).filter(Player.team == abbr).all()
            for p in existing_players:
                has_stats = db.query(PlayerSeasonStats).filter(
                    PlayerSeasonStats.player_id == p.id
                ).first()
                if not has_stats:
                    # Add stats for existing player
                    player_data = next((pd for team_data in SAMPLE_PLAYERS.values() for pd in team_data if pd["name"] == p.name), None)
                    if player_data:
                        games_played = 45  # Mid-season
                        stats = PlayerSeasonStats(
                            player_id=p.id,
                            season=current_season,
                            season_type="REG",
                            team=abbr,
                            games_played=games_played,
                            goals=int(player_data["goals"] * games_played),
                            assists=int(player_data["assists"] * games_played),
                            points=int(player_data["points"] * games_played),
                            shots=int(player_data["shots"] * games_played),
                            shooting_percentage=player_data["goals"] / max(player_data["shots"], 0.01) * 100,
                        )
                        db.add(stats)
                        stats_count += 1
            continue

        # Get sample players for this team
        players_data = SAMPLE_PLAYERS.get(abbr, [])

        # If no specific data, add a generic player
        if not players_data:
            players_data = [
                {"name": f"{abbr} Player 1", "position": "C", "goals": 0.3, "assists": 0.3, "points": 0.6, "shots": 3.5}
            ]

        for player_data in players_data:
            games_played = 45  # Mid-season
            player = Player(
                id=uuid.uuid4(),
                name=player_data["name"],
                full_name=player_data["name"],
                position=player_data["position"],
                team_id=team.id,
                team=abbr,
                status="active"
            )
            db.add(player)
            added_count += 1

            # Add season stats
            stats = PlayerSeasonStats(
                player_id=player.id,
                season=current_season,
                season_type="REG",
                team=abbr,
                games_played=games_played,
                goals=int(player_data["goals"] * games_played),
                assists=int(player_data["assists"] * games_played),
                points=int(player_data["points"] * games_played),
                shots=int(player_data["shots"] * games_played),
                shooting_percentage=player_data["goals"] / max(player_data["shots"], 0.01) * 100,
            )
            db.add(stats)
            stats_count += 1

        if added_count % 10 == 0:
            db.commit()

    db.commit()
    print(f"Added {added_count} sample players")
    print(f"Added {stats_count} season stats records")


if __name__ == "__main__":
    add_sample_players()
