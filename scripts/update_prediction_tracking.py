"""Update prediction_tracking with actual results from NBA API.

This script:
1. Fetches actual boxscore data from NBA.com API for completed games
2. Updates prediction_tracking table with actual_value
3. Calculates is_correct based on recommendation vs actual
4. Marks predictions as resolved

Features:
- Strict name matching to prevent false positives (e.g., Jalen vs Jaylin)
- Timezone-aware date handling for ESPN/NBA API discrepancies
- DNP (Did Not Play) detection = 0 points
"""
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
from difflib import SequenceMatcher

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nba_api.stats.endpoints import boxscoretraditionalv3
from sqlalchemy import text
from app.core.database import SessionLocal


# Known name conflicts - players with similar names who should NOT be fuzzy matched
# Format: ("similar_name", "correct_name") - prevents matching these pairs
NAME_CONFLICTS = {
    ("jalen", "jaylin"),
    ("jaylin", "jalen"),
    # Add more conflicts as discovered
}


def names_too_similar(name1: str, name2: str) -> bool:
    """Check if two names are too similar but different (false positive risk).

    Returns True if names are similar enough to cause confusion but
    represent different players (e.g., Jalen vs Jaylin).
    """
    n1_lower = name1.lower().strip()
    n2_lower = name2.lower().strip()

    # Direct name conflict check
    for part1 in n1_lower.split():
        for part2 in n2_lower.split():
            if (part1, part2) in NAME_CONFLICTS or (part2, part1) in NAME_CONFLICTS:
                return True

    # Check string similarity ratio
    # If similarity is high (0.8+) but not exact match, flag as potential conflict
    similarity = SequenceMatcher(None, n1_lower, n2_lower).ratio()

    # High similarity but not identical names
    if similarity > 0.75 and n1_lower != n2_lower:
        # Additional check: names share most letters but differ by 1-2
        # This catches Jalen/Jaylin, Marcus/Marquis, etc.
        return True

    return False


def normalize_date_for_comparison(dt: datetime) -> datetime:
    """Normalize datetime to US/Eastern for ESPN comparison.

    ESPN displays boxscores in US/Eastern time, while our database uses UTC.
    This converts UTC to Eastern for accurate date matching.
    """
    if dt.tzinfo is None:
        # Assume UTC if no timezone
        dt = dt.replace(tzinfo=timezone.utc)

    # Convert to US/Eastern
    eastern_tz = timezone(timedelta(hours=-5))  # EST
    return dt.astimezone(eastern_tz)


def fetch_nba_boxscore(game_id: str) -> tuple[Dict[str, int], Dict[str, int]]:
    """Fetch player points from NBA.com boxscore.

    Args:
        game_id: NBA game ID (e.g., '0022500686')

    Returns:
        Tuple of:
        - Dict mapping player names to points (all players who played)
        - Dict mapping person IDs to player names (for exact matching)
    """
    player_points = {}
    id_to_name = {}

    try:
        boxscore = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        data = boxscore.get_dict()

        # Navigate to boxscore data
        box_score_data = data.get('boxScoreTraditional', {})

        # Process both home and away teams
        for team_key in ['homeTeam', 'awayTeam']:
            team_data = box_score_data.get(team_key, {})
            players = team_data.get('players', [])

            for player in players:
                # Get person ID and full name
                person_id = str(player.get('personId', ''))
                first_name = player.get('firstName', '')
                family_name = player.get('familyName', '')
                full_name = f"{first_name} {family_name}".strip()

                # Store ID to name mapping
                id_to_name[person_id] = full_name

                # Get points from statistics (0 if DNP)
                stats = player.get('statistics', {})
                points = stats.get('points', 0) or 0
                minutes = stats.get('minutes', '')

                # Store points (including 0 for players who played but didn't score)
                # Players with no minutes entry are DNP
                if minutes and minutes != '':
                    player_points[full_name] = int(points)

    except Exception as e:
        print(f"  Error fetching NBA boxscore: {e}")

    return player_points, id_to_name


def calculate_is_correct(recommendation: str, predicted_value: float, actual_value: float, line: float) -> Optional[bool]:
    """Calculate if the prediction was correct.

    A bet wins if:
    - OVER and actual > line
    - UNDER and actual < line
    """
    if recommendation == "OVER":
        return actual_value > line
    elif recommendation == "UNDER":
        return actual_value < line
    return None


async def update_prediction_tracking():
    """Update all pending predictions with actual results."""
    db = SessionLocal()
    skipped_matches = []  # Track matches skipped due to name conflicts

    try:
        print("=" * 80)
        print("UPDATING PREDICTION_TRACKING WITH ACTUAL RESULTS")
        print("=" * 80)
        print()

        # Get all pending predictions with game external IDs
        result = db.execute(text("""
            SELECT g.id, g.external_id, g.away_team, g.home_team, g.game_date::date,
                   COUNT(pt.id) as pending_count
            FROM games g
            JOIN prediction_tracking pt ON pt.game_id = g.id
            WHERE pt.actual_resolved_at IS NULL
            GROUP BY g.id, g.external_id, g.away_team, g.home_team, g.game_date
            ORDER BY g.game_date
        """)).fetchall()

        print(f"Found {len(result)} games with pending predictions")
        print()

        total_updated = 0
        total_correct = 0
        total_incorrect = 0

        for game_id, external_id, away, home, game_date, count in result:
            # Display date in both UTC (database) and Eastern (ESPN)
            game_date_et = normalize_date_for_comparison(game_date)
            print(f"{away} @ {home} ({game_date} UTC / {game_date_et.strftime('%Y-%m-%d')} ET) - External ID: {external_id}")
            print("-" * 60)

            # Fetch NBA boxscore using external ID
            player_points, id_to_name = fetch_nba_boxscore(external_id)

            if not player_points:
                print("  No boxscore data found")
                print()
                continue

            print(f"  Found {len(player_points)} players who played")
            for name, pts in sorted(player_points.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"    {name}: {pts} PTS")

            # Get predictions with player external_id for exact matching
            predictions = db.execute(text("""
                SELECT pt.id, pt.player_name, pt.player_id, pt.stat_type, pt.predicted_value,
                       pt.bookmaker_line, pt.recommendation, pt.confidence,
                       p.external_id
                FROM prediction_tracking pt
                LEFT JOIN players p ON pt.player_id = p.id
                WHERE pt.game_id = :game_id
                  AND pt.actual_resolved_at IS NULL
            """), {"game_id": game_id}).fetchall()

            print(f"\n  Updating {len(predictions)} predictions:")
            game_correct = 0
            game_incorrect = 0

            for pred in predictions:
                pred_id, player_name, player_id, stat_type, predicted, line, rec, conf, ext_id = pred

                # Skip if not points
                if stat_type != "points":
                    continue

                actual = None
                matched_via = None

                # First try: match by external_id (most reliable)
                if ext_id:
                    name_from_id = id_to_name.get(str(ext_id))
                    if name_from_id:
                        actual = player_points.get(name_from_id)
                        matched_via = f"ID {ext_id}"

                # Second try: exact name match
                if actual is None:
                    actual = player_points.get(player_name)
                    if actual is not None:
                        matched_via = "name"

                # Third try: fuzzy match - ONLY if names are NOT too similar
                # This prevents false matches like Jalen Williams → Jaylin Williams
                if actual is None:
                    for nba_name, pts in player_points.items():
                        # Skip if names are too similar (potential false positive)
                        if names_too_similar(player_name, nba_name):
                            skipped_matches.append(f"  Skipped: '{player_name}' vs '{nba_name}' (names too similar)")
                            continue

                        # Check full name match with allowance for middle initials
                        pred_parts = player_name.lower().split()
                        nba_parts = nba_name.lower().split()

                        if (pred_parts[0] == nba_parts[0] and  # First name match
                            pred_parts[-1] == nba_parts[-1]):  # Last name match
                            actual = pts
                            matched_via = f"name '{nba_name}'"
                            break

                # If still not found, player DNP (Did Not Play) = 0 points
                if actual is None:
                    actual = 0
                    matched_via = "DNP"

                is_correct = calculate_is_correct(rec, float(predicted), actual, float(line))
                difference = actual - float(predicted)

                # Update prediction
                db.execute(text("""
                    UPDATE prediction_tracking
                    SET actual_value = :actual,
                        is_correct = :is_correct,
                        difference = :difference,
                        actual_resolved_at = NOW()
                    WHERE id = :id
                """), {
                    "id": pred_id,
                    "actual": actual,
                    "is_correct": is_correct,
                    "difference": difference
                })

                status = "✓" if is_correct else "✗"
                dnp_marker = " (DNP)" if matched_via == "DNP" else ""
                print(f"    {status} {player_name}: {actual} vs {rec} {line} (Pred: {predicted:.1f}, Diff: {difference:+.1f}){dnp_marker}")

                total_updated += 1
                if is_correct:
                    game_correct += 1
                    total_correct += 1
                else:
                    game_incorrect += 1
                    total_incorrect += 1

            print(f"  Game results: {game_correct}W - {game_incorrect}L")
            print()

        db.commit()

        print("=" * 80)
        print("UPDATE COMPLETE")
        print("=" * 80)
        print(f"Total predictions updated: {total_updated}")
        print(f"Total correct: {total_correct} ({100*total_correct/total_updated if total_updated > 0 else 0:.1f}%)")
        print(f"Total incorrect: {total_incorrect} ({100*total_incorrect/total_updated if total_updated > 0 else 0:.1f}%)")

        # Show remaining unresolved
        remaining = db.execute(text("""
            SELECT COUNT(*) FROM prediction_tracking WHERE actual_resolved_at IS NULL
        """)).fetchone()[0]

        if remaining > 0:
            print(f"\nStill pending: {remaining} predictions")

        # Show skipped matches due to name conflicts
        if skipped_matches:
            print("\n" + "=" * 80)
            print("NAME CONFLICT DETECTION (skipped fuzzy matches)")
            print("=" * 80)
            for skip in skipped_matches[:10]:  # Show first 10
                print(skip)
            if len(skipped_matches) > 10:
                print(f"  ... and {len(skipped_matches) - 10} more")
            print("\nThese matches were skipped to prevent false positives.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(update_prediction_tracking())
