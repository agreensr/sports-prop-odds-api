"""Show high-confidence bets for key NBA players (projected 12+ points).

This script filters out depth/G-league players and focuses on starters
and key rotation players.
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx


async def get_key_player_bets():
    """Get high-confidence bets for key players."""
    # Get games with predictions
    async with httpx.AsyncClient() as client:
        # Get recent predictions to find game IDs
        games_resp = await client.get("http://localhost:8002/api/v1/nba/predictions/recent?hours=48&limit=500")
        games_data = games_resp.json()

        # Get unique game IDs
        game_ids = list(set([p["game"]["id"] for p in games_data.get("predictions", [])]))

        print("=" * 100)
        print("KEY PLAYER PROP BETS (Projected 12+ points, Confidence ≥ 60%)")
        print("=" * 100)
        print()

        for game_id in game_ids:
            # Get enhanced predictions for each game
            enhanced_resp = await client.get(
                f"http://localhost:8002/api/v1/nba/predictions/enhanced/game/{game_id}?bookmaker=fanduel&stat_types=points,rebounds,assists"
            )
            enhanced_data = enhanced_resp.json()

            if "error" in enhanced_data:
                continue

            game_info = enhanced_data.get("game", {})
            print(f"\n{game_info.get('away_team')} @ {game_info.get('home_team')} ({game_info.get('date_display')})")
            print("-" * 80)

            # Filter for key players (projected 12+ points) and high confidence
            key_bets = []
            for pred in enhanced_data.get("predictions", []):
                if pred["confidence"] >= 0.6 and pred["stat_type"] == "points":
                    if pred["projected"] >= 12.0:
                        key_bets.append(pred)

            # Sort by confidence descending
            key_bets.sort(key=lambda x: x["confidence"], reverse=True)

            for bet in key_bets[:15]:  # Top 15 per game
                rec = bet["recommendation"]
                edge_str = f"+{bet['edge']:.1f}" if bet['edge'] > 0 else f"{bet['edge']:.1f}"

                # Convert decimal odds to American for display
                def to_american(decimal):
                    if decimal >= 2.0:
                        return f"+{int((decimal - 1) * 100)}"
                    else:
                        return f"{int(-100 / (decimal - 1))}"

                over_odds = to_american(bet.get("over_price", 1.91))
                under_odds = to_american(bet.get("under_price", 1.91))

                print(f"  {bet['player']:20} ({bet['team']:3}) {bet['stat_type'].upper():6} | "
                      f"Our {bet['projected']:5.1f} vs FD {bet['line']:5.1f} | "
                      f"Edge {edge_str:>5} | {rec:4} {int(bet['confidence']*100):3}% | "
                      f"O {over_odds:>6} / U {under_odds:>6}")

            print(f"  Total key player bets: {len(key_bets)}")


if __name__ == "__main__":
    asyncio.run(get_key_player_bets())
