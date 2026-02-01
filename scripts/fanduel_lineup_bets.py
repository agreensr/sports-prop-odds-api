"""Show ONLY players with actual FanDuel odds - no inactive/depth players.

This ensures we only show bets for players who are actually in the
FanDuel lineup by checking if they have odds available.
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx


async def get_fanduel_lineup_bets():
    """Get bets ONLY for players with actual FanDuel odds."""
    async with httpx.AsyncClient(timeout=60) as client:
        # Get upcoming games
        games_resp = await client.get("http://localhost:8002/api/v1/nba/predictions/recent?hours=48&limit=500")
        games_data = games_resp.json()

        # Get unique game IDs
        game_ids = list(set([p["game"]["id"] for p in games_data.get("predictions", [])]))

        print("=" * 100)
        print("FANDUEL LINEUP BETS - Only players with actual FanDuel odds")
        print("=" * 100)
        print()

        total_bets = 0

        for game_id in game_ids:
            # Get enhanced predictions
            enhanced_resp = await client.get(
                f"http://localhost:8002/api/v1/nba/predictions/enhanced/game/{game_id}?bookmaker=fanduel&stat_types=points,rebounds,assists"
            )

            if enhanced_resp.status_code != 200:
                continue

            enhanced_data = enhanced_resp.json()

            if "error" in enhanced_data:
                continue

            game_info = enhanced_data.get("game", {})
            print(f"\n{game_info.get('away_team')} @ {game_info.get('home_team')} ({game_info.get('date_display')})")
            print("-" * 80)

            # Filter to ONLY players with actual odds (bookmaker line is not null)
            # AND high confidence (>= 0.6)
            # AND projected 12+ points (key players)
            active_bets = []
            for pred in enhanced_data.get("predictions", []):
                # Only include players who have actual FanDuel odds
                if pred.get("line") is not None and pred["confidence"] >= 0.6:
                    if pred["stat_type"] == "points" and pred["projected"] >= 10.0:
                        active_bets.append(pred)

            # Sort by confidence descending
            active_bets.sort(key=lambda x: x["confidence"], reverse=True)

            if not active_bets:
                print("  No qualifying bets")
                continue

            def to_american(decimal):
                if decimal is None or decimal == 0:
                    return "N/A"
                if decimal >= 2.0:
                    return f"+{int((decimal - 1) * 100)}"
                else:
                    return f"{int(-100 / (decimal - 1))}"

            for bet in active_bets:
                rec = bet["recommendation"]
                edge_str = f"+{bet['edge']:.1f}" if bet['edge'] > 0 else f"{bet['edge']:.1f}"
                over_odds = to_american(bet.get("over_price"))
                under_odds = to_american(bet.get("under_price"))

                print(f"  {bet['player']:20} ({bet['team']:3}) POINTS | "
                      f"Our {bet['projected']:5.1f} vs FD {bet['line']:5.1f} | "
                      f"Edge {edge_str:>5} | {rec:4} {int(bet['confidence']*100):3}% | "
                      f"O {over_odds:>6} / U {under_odds:>6}")
                total_bets += 1

        print(f"\n{'=' * 100}")
        print(f"Total active FanDuel bets: {total_bets}")


if __name__ == "__main__":
    asyncio.run(get_fanduel_lineup_bets())
