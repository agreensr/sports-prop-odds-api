#!/usr/bin/env python3
"""
Consolidated High-Confidence Player Prop Bets

This script generates a consolidated list of high-confidence player prop bets
for all upcoming games, filtered to only include players with actual FanDuel odds.

Requirements:
- Only include players with actual FanDuel odds (line_source = "fanduel")
- Confidence >= 60%
- Projected 12+ points

Output:
1. Total count of qualifying bets
2. Top 20 bets by confidence
3. For each bet: player name, teams, our projection vs FD line, edge, recommendation, confidence %

Usage:
    python scripts/consolidated_high_confidence_bets.py
    python scripts/consolidated_high_confidence_bets.py --min-confidence 70
    python scripts/consolidated_high_confidence_bets.py --min-projection 15
"""
import asyncio
import argparse
import httpx
from datetime import datetime


async def get_consolidated_bets(min_confidence=0.6, min_projection=12.0, sport="nba"):
    """Get consolidated high-confidence player prop bets for all upcoming games."""
    base_url = "http://localhost:8002"

    async with httpx.AsyncClient(timeout=60) as client:
        # Get upcoming games
        games_resp = await client.get(
            f"{base_url}/api/v1/{sport}/predictions/recent?hours=48&limit=200"
        )
        games_data = games_resp.json()

        # Get unique game IDs
        game_ids = list(set([p["game"]["id"] for p in games_data.get("predictions", [])]))

        all_bets = []

        for game_id in game_ids:
            # Get enhanced predictions
            enhanced_resp = await client.get(
                f"{base_url}/api/v1/{sport}/predictions/enhanced/game/{game_id}?bookmaker=fanduel&stat_types=points,rebounds,assists"
            )

            if enhanced_resp.status_code != 200:
                continue

            enhanced_data = enhanced_resp.json()

            if "error" in enhanced_data:
                continue

            game_info = enhanced_data.get("game", {})

            # Filter to ONLY players with actual FanDuel odds
            # Requirements:
            # - line_source = "fanduel"
            # - confidence >= min_confidence
            # - projected >= min_projection points
            for pred in enhanced_data.get("predictions", []):
                if (pred.get("line_source") == "fanduel" and
                    pred.get("confidence", 0) >= min_confidence and
                    pred.get("stat_type") == "points" and
                    pred.get("projected", 0) >= min_projection):

                    all_bets.append({
                        "player": pred.get("player"),
                        "player_id": pred.get("player_id"),
                        "team": pred.get("team"),
                        "opponent": pred.get("opponent"),
                        "position": pred.get("position"),
                        "stat_type": pred.get("stat_type"),
                        "projected": pred.get("projected"),
                        "line": pred.get("line"),
                        "edge": pred.get("edge"),
                        "recommendation": pred.get("recommendation"),
                        "confidence": pred.get("confidence"),
                        "bookmaker": pred.get("bookmaker"),
                        "line_source": pred.get("line_source"),
                        "over_price": pred.get("over_price"),
                        "under_price": pred.get("under_price"),
                        "away_team": game_info.get("away_team"),
                        "home_team": game_info.get("home_team"),
                        "game_date": game_info.get("date_display")
                    })

        # Sort by confidence descending, then by edge descending
        all_bets.sort(key=lambda x: (x["confidence"], x.get("edge", 0)), reverse=True)

        return all_bets


def to_american(decimal):
    """Convert decimal odds to American odds format."""
    if decimal is None or decimal == 0:
        return "N/A"
    if decimal >= 2.0:
        return f"+{int((decimal - 1) * 100)}"
    else:
        return f"{int(-100 / (decimal - 1))}"


def format_confidence_color(confidence):
    """Return ANSI color code based on confidence level."""
    if confidence >= 0.8:
        return "\033[92m"  # Green
    elif confidence >= 0.7:
        return "\033[93m"  # Yellow
    else:
        return "\033[0m"   # Reset


def reset_color():
    """Reset ANSI color."""
    return "\033[0m"


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate consolidated high-confidence player prop bets"
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.6,
        help='Minimum confidence threshold (default: 0.6 = 60%%)'
    )
    parser.add_argument(
        '--min-projection',
        type=float,
        default=12.0,
        help='Minimum projected points (default: 12.0)'
    )
    parser.add_argument(
        '--sport',
        type=str,
        default='nba',
        choices=['nba', 'nfl', 'mlb', 'nhl'],
        help='Sport to query (default: nba)'
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )

    args = parser.parse_args()

    bets = await get_consolidated_bets(
        min_confidence=args.min_confidence,
        min_projection=args.min_projection,
        sport=args.sport
    )

    print("=" * 115)
    print(f"HIGH-CONFIDENCE PLAYER PROP BETS - FanDuel Only ({args.sport.upper()})")
    print(f"Criteria: Confidence >= {int(args.min_confidence*100)}%% | Projected >= {args.min_projection} Points | line_source = fanduel")
    print("=" * 115)
    print()

    # 1. Total count of qualifying bets
    print(f"1. TOTAL QUALIFYING BETS: {len(bets)}")
    print()

    if not bets:
        print("No qualifying bets found.")
        return

    # 2. Top bets by confidence
    display_count = min(len(bets), 20)
    print(f"2. TOP {display_count} BETS BY CONFIDENCE")
    print("-" * 115)
    print(f"{'Player':<22} {'Teams':<12} {'Our Proj':<10} {'FD Line':<9} {'Edge':<6} {'Rec':<7} {'Conf':<10} {'Odds (O/U)':<15}")
    print("-" * 115)

    for bet in bets[:display_count]:
        teams = f"{bet['team']}@{bet['opponent']}"
        edge_str = f"+{bet['edge']:.1f}" if bet['edge'] > 0 else f"{bet['edge']:.1f}"
        over_odds = to_american(bet.get("over_price"))
        under_odds = to_american(bet.get("under_price"))
        odds_str = f"O {over_odds} / U {under_odds}"
        conf_pct = f"{int(bet['confidence']*100)}%"

        if not args.no_color:
            color = format_confidence_color(bet['confidence'])
            reset = reset_color()
            conf_colored = f"{color}{conf_pct}{reset}"
        else:
            conf_colored = conf_pct

        print(f"{bet['player']:<22} {teams:<12} {bet['projected']:<10.1f} {bet['line']:<9.1f} "
              f"{edge_str:<6} {bet['recommendation']:<7} {conf_colored:<15} {odds_str:<15}")

    print("-" * 115)
    print()

    # Summary by recommendation type
    overs = [b for b in bets if b['recommendation'] == 'OVER']
    unders = [b for b in bets if b['recommendation'] == 'UNDER']

    print("SUMMARY BY RECOMMENDATION:")
    print(f"  OVER bets:  {len(overs)}")
    print(f"  UNDER bets: {len(unders)}")
    print()

    # Best edge bets
    print("BEST EDGE BETS:")
    best_over = max([b for b in bets if b['recommendation'] == 'OVER'], key=lambda x: x['edge'], default=None)
    best_under = max([b for b in bets if b['recommendation'] == 'UNDER'], key=lambda x: -x['edge'], default=None)

    if best_over:
        print(f"  Best OVER edge:  {best_over['player']} ({best_over['team']}@{best_over['opponent']}) - +{best_over['edge']:.1f} points")
    if best_under:
        print(f"  Best UNDER edge: {best_under['player']} ({best_under['team']}@{best_under['opponent']}) - {best_under['edge']:.1f} points")


if __name__ == "__main__":
    asyncio.run(main())
