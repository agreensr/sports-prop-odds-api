"""Show high-confidence bets for key NBA players using direct database access."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.services.core.odds_api_service import get_odds_service
from app.core.config import settings


async def get_key_player_bets():
    """Get high-confidence bets for key players."""
    db = SessionLocal()

    try:
        # Get all upcoming games
        games_result = db.execute(text("""
            SELECT g.id, g.away_team, g.home_team, g.game_date
            FROM games g
            WHERE g.game_date >= CURRENT_DATE
            ORDER BY g.game_date
        """))

        games = games_result.fetchall()

        print("=" * 100)
        print("KEY PLAYER PROP BETS (Projected 12+ points, Confidence ≥ 60%)")
        print("=" * 100)

        # Initialize odds service
        odds_service = None
        if settings.THE_ODDS_API_KEY:
            try:
                odds_service = get_odds_service(settings.THE_ODDS_API_KEY)
            except Exception as e:
                print(f"Odds service not available: {e}")

        # Initialize prediction service
        prediction_service = EnhancedPredictionService(db=db, odds_api_service=odds_service)

        for game in games:
            game_id, away_team, home_team, game_date = game

            print(f"\n{away_team} @ {home_team} ({game_date.date()})")
            print("-" * 80)

            # Generate predictions for this game
            predictions = prediction_service.generate_prop_predictions(
                game_id=str(game_id),
                stat_types=["points", "rebounds", "assists"],
                bookmaker="fanduel"
            )

            # Filter for key players (projected 12+ points) and high confidence
            key_bets = []
            for pred in predictions:
                if pred["confidence"] >= 0.6 and pred["stat_type"] == "points":
                    if pred["projected"] >= 12.0:
                        key_bets.append(pred)

            # Sort by confidence descending
            key_bets.sort(key=lambda x: x["confidence"], reverse=True)

            if not key_bets:
                print("  No high-confidence key player bets")
                continue

            for bet in key_bets[:15]:  # Top 15 per game
                rec = bet["recommendation"]
                edge_str = f"+{bet['edge']:.1f}" if bet['edge'] > 0 else f"{bet['edge']:.1f}"

                # Convert decimal odds to American
                def to_american(decimal):
                    if decimal is None or decimal == 0:
                        return "N/A"
                    if decimal >= 2.0:
                        return f"+{int((decimal - 1) * 100)}"
                    else:
                        return f"{int(-100 / (decimal - 1))}"

                over_odds = to_american(bet.get("over_price"))
                under_odds = to_american(bet.get("under_price"))

                print(f"  {bet['player']:20} ({bet['team']:3}) POINTS | "
                      f"Our {bet['projected']:5.1f} vs FD {bet['line']:5.1f} | "
                      f"Edge {edge_str:>5} | {rec:4} {int(bet['confidence']*100):3}% | "
                      f"O {over_odds:>6} / U {under_odds:>6}")

            print(f"  Total key player bets: {len(key_bets)}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(get_key_player_bets())
