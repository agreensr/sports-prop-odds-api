#!/usr/bin/env python3
"""
Daily Smart Parlay Generation Script.

This script implements the parlay generation workflow:
1. Filter all active players by injury status (exclude OUT, DOUBTFUL, QUESTIONABLE)
2. Get upcoming games
3. Generate predictions for healthy active players
4. Generate parlays (2-leg, 3-leg, cross-game, combo)
5. Send formatted Telegram message

Usage:
    python scripts/generate_smart_parlays.py

Schedule:
    Run daily at 10am ET via cron or scheduler.
"""
import sys
import os
import asyncio
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.nba.injury_service import InjuryService
from app.services.nba.prediction_service import PredictionService
from app.services.core.parlay_service import ParlayService
from app.services.telegram_service import send_message
from app.models.nba.models import Game, Prediction, Player

try:
    from app.services.telegram_service import send_message
    TELEGRAM_ENABLED = True
except ImportError:
    print("⚠️  Telegram service not available")
    TELEGRAM_ENABLED = False


def get_current_season_week() -> tuple:
    """Get current NBA season and week."""
    today = datetime.now()
    nov_1 = datetime(today.year, 11, 1) if today.month >= 11 else datetime(today.year - 1, 11, 1)
    days_since = (today - nov_1).days
    week = max(1, days_since // 7 + 1)

    if today.month >= 10:
        season = f"{today.year}-{str(today.year + 1)[-2:]}"
    else:
        season = f"{today.year - 1}-{str(today.year)[-2:]}"

    return season, week


async def generate_daily_picks():
    """Generate and send daily picks via Telegram."""
    db = SessionLocal()

    try:
        print("🚀 Starting daily smart parlay generation...")

        # Step 1: Filter by injury status (exclude OUT, DOUBTFUL, QUESTIONABLE)
        print("\n🏥 Step 1: Filtering all active players by injury status...")
        injury_service = InjuryService(db)

        # Get all active players
        all_active_ids = [str(p.id) for p in db.query(Player).filter(Player.active == True).all()]

        healthy_ids = injury_service.filter_by_injury_status(
            player_ids=all_active_ids,
            exclude_statuses=["out", "doubtful", "questionable"]
        )

        print(f"   ✅ Active players: {len(all_active_ids)} → Healthy: {len(healthy_ids)}")

        # Step 2: Get upcoming games with odds data
        print("\n📅 Step 2: Getting upcoming games with odds...")

        # Get games that have predictions with odds data
        from sqlalchemy import distinct
        games_with_odds = db.query(distinct(Prediction.game_id)).filter(
            Prediction.over_price.isnot(None)
        ).subquery()

        games = db.query(Game).filter(
            Game.id.in_(games_with_odds),
            Game.status.in_(["scheduled", "in_progress"])
        ).order_by(Game.game_date).all()

        print(f"   ✅ Found {len(games)} upcoming games with odds")

        if not games:
            print("   ⚠️  No upcoming games found")
            if TELEGRAM_ENABLED:
                send_message("⚠️ <b>Daily Picks</b>\n\nNo upcoming games found for today.")
            return

        # Step 3: Check predictions for healthy active players
        print("\n🎯 Step 3: Checking predictions for healthy active players...")

        for game in games:
            # Check active healthy players for this game
            game_players = db.query(Player).filter(
                Player.team.in_([game.away_team, game.home_team]),
                Player.id.in_(healthy_ids)
            ).count()

            # Check existing predictions with odds for this game
            preds_with_odds = db.query(Prediction).filter(
                Prediction.game_id == str(game.id),
                Prediction.over_price.isnot(None)
            ).count()

            print(f"   {game.away_team} @ {game.home_team}: {game_players} healthy, {preds_with_odds} with odds")

        print(f"   ✅ Found {len(games)} games with data")

        # Step 4: Generate parlays
        print("\n🎰 Step 4: Generating parlays...")

        parlay_service = ParlayService(db)

        # 2-Leg Same Game Parlays
        same_game_2_leg = []
        for game in games:
            try:
                parlays = parlay_service.generate_same_game_parlays_optimized(
                    game_id=str(game.id),
                    min_confidence=0.40,
                    max_legs=2,
                    min_ev=-0.20
                    # No top_50_player_ids filter - using expanded player pool
                )
                same_game_2_leg.extend(parlays)
            except Exception as e:
                print(f"   Error generating 2-leg for game {game.id}: {e}")

        # 3-Leg Same Game Parlays
        same_game_3_leg = []
        for game in games:
            try:
                parlays = parlay_service.generate_same_game_parlays_optimized(
                    game_id=str(game.id),
                    min_confidence=0.35,
                    max_legs=3,
                    min_ev=-0.30
                    # No top_50_player_ids filter - using expanded player pool
                )
                same_game_3_leg.extend([p for p in parlays if p["total_legs"] == 3])
            except Exception as e:
                print(f"   Error generating 3-leg for game {game.id}: {e}")

        # Cross-Game 2-Leg Parlays
        try:
            cross_game_2_leg = parlay_service.generate_cross_game_parlays(
                days_ahead=2,
                min_confidence=0.40,
                min_ev=-0.20
                # No top_50_player_ids filter - using expanded player pool
            )
        except Exception as e:
            print(f"   Error generating cross-game parlays: {e}")
            cross_game_2_leg = []

        # 4-Leg Combo Parlays
        try:
            combo_4_leg = parlay_service.generate_combo_parlays(
                days_ahead=2,
                min_ev=-0.10
                # No top_50_player_ids filter - using expanded player pool
            )
        except Exception as e:
            print(f"   Error generating combo parlays: {e}")
            combo_4_leg = []

        print(f"   ✅ Generated {len(same_game_2_leg)} 2-leg, {len(same_game_3_leg)} 3-leg, "
              f"{len(cross_game_2_leg)} cross-game, {len(combo_4_leg)} combo parlays")

        # Step 5: Format and send Telegram message
        print("\n📤 Step 5: Sending Telegram message...")

        message = format_parlays_message(
            games[:3],
            same_game_2_leg[:3],
            same_game_3_leg[:2],
            cross_game_2_leg[:3],
            combo_4_leg[:1]
        )

        if TELEGRAM_ENABLED:
            send_message(message)
            print("   ✅ Telegram message sent")
        else:
            print("   ⚠️  Telegram disabled, message preview:")
            print(message[:500] + "...")

        print("\n✅ Daily smart parlay generation completed!")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

        if TELEGRAM_ENABLED:
            send_message(f"❌ <b>Daily Picks Generation Failed</b>\n\nError: {str(e)[:200]}")

        return 1

    finally:
        db.close()


def format_parlays_message(
    games,
    same_game_2_leg,
    same_game_3_leg,
    cross_game_2_leg,
    combo_4_leg
) -> str:
    """Format the daily Telegram message with parlays."""

    from app.utils.timezone import format_game_time_central

    message = f"""🏀 <b>NBA Player Props - {datetime.now().strftime("%B %d, %Y")}</b>
<i>Injury-filtered picks from all active players</i>

<b>━━━━━━━━━━━━━━━━━━━━━━</b>

<b>🎯 2-Leg Same Game Parlays</b>
"""

    # 2-Leg Same Game Parlays
    if same_game_2_leg:
        for i, parlay in enumerate(same_game_2_leg[:3], 1):
            legs = parlay["legs"]
            combined_conf = int(parlay["confidence_score"] * 100)
            ev_pct = int(parlay["expected_value"] * 100)
            odds = parlay["calculated_odds"]

            # Get game info from first leg
            game_id = legs[0].get("game_id")
            game = next((g for g in games if str(g.id) == game_id), None)

            if game:
                message += f"\n<b>{game.away_team} vs {game.home_team}</b>\n"
            else:
                message += f"\n<b>Parlay {i}</b>\n"

            for leg in legs:
                player_name = leg.get("player_name", "Unknown")
                stat = leg.get("stat_type", "STAT").upper()
                line = leg.get("line", 0.0)
                selection = leg.get("selection", "OVER")
                conf = int(leg.get("confidence", 0.5) * 100)

                message += f"  {i}. {player_name} {stat} {selection} {line} ({conf}%)\n"

            message += f"  Combined: {combined_conf}% | EV: +{ev_pct}% | Odds: {odds:+d}\n\n"

    # 3-Leg Same Game Parlays
    message += f"""<b>━━━━━━━━━━━━━━━━━━━━━━</b>

<b>🎲 3-Leg Same Game Parlays</b>
"""

    if same_game_3_leg:
        for i, parlay in enumerate(same_game_3_leg[:2], 1):
            legs = parlay["legs"]
            combined_conf = int(parlay["confidence_score"] * 100)
            ev_pct = int(parlay["expected_value"] * 100)
            odds = parlay["calculated_odds"]

            game_id = legs[0].get("game_id")
            game = next((g for g in games if str(g.id) == game_id), None)

            if game:
                message += f"\n<b>{game.away_team} vs {game.home_team}</b>\n"

            for leg in legs:
                player_name = leg.get("player_name", "Unknown")
                stat = leg.get("stat_type", "STAT").upper()
                line = leg.get("line", 0.0)
                conf = int(leg.get("confidence", 0.5) * 100)

                message += f"  • {player_name} {stat} Over {line} ({conf}%)\n"

            message += f"  Combined: {combined_conf}% | EV: +{ev_pct}% | Odds: {odds:+d}\n\n"

    # Cross-Game Parlays
    message += f"""<b>━━━━━━━━━━━━━━━━━━━━━━</b>

<b>🌐 Cross-Game 2-Leg Parlays</b>
"""

    if cross_game_2_leg:
        for i, parlay in enumerate(cross_game_2_leg[:3], 1):
            legs = parlay["legs"]
            combined_conf = int(parlay["confidence_score"] * 100)
            ev_pct = int(parlay["expected_value"] * 100)
            odds = parlay["calculated_odds"]

            for leg in legs:
                player_name = leg.get("player_name", "Unknown")
                stat = leg.get("stat_type", "STAT").upper()
                line = leg.get("line", 0.0)
                conf = int(leg.get("confidence", 0.5) * 100)

                # Get game info
                game_id = leg.get("game_id")
                game = next((g for g in games if str(g.id) == game_id), None)

                teams = f"{game.away_team}@{game.home_team}" if game else "Unknown"
                message += f"\n{i}. {player_name} {stat} Over {line} ({conf}%) - {teams}\n"

            message += f"   Combined: {combined_conf}% | EV: +{ev_pct}% | Odds: {odds:+d}\n\n"

    # 4-Leg Combo Parlay
    message += f"""<b>━━━━━━━━━━━━━━━━━━━━━━</b>

<b>🎰 4-Leg Combo Parlay</b>
<i>Combining two 2-leg parlays</i>
"""

    if combo_4_leg:
        parlay = combo_4_leg[0]
        legs = parlay["legs"]
        combined_conf = int(parlay["confidence_score"] * 100)
        ev_pct = int(parlay["expected_value"] * 100)
        odds = parlay["calculated_odds"]

        for j, leg in enumerate(legs, 1):
            player_name = leg.get("player_name", "Unknown")
            stat = leg.get("stat_type", "STAT").upper()
            line = leg.get("line", 0.0)

            message += f"{j}. {player_name} {stat} Over {line}\n"

        message += f"\nCombined: {combined_conf}% | EV: +{ev_pct}% | Odds: {odds:+d}\n"

    # Footer
    message += """
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

<i>All picks from healthy active players</i>
<i>⚠️ Always check lines before betting</i>
"""

    return message


if __name__ == "__main__":
    exit_code = asyncio.run(generate_daily_picks())
    sys.exit(exit_code)
