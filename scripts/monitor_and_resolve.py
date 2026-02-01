"""Monitor and resolve completed NBA games with predictions.

This script:
1. Checks for games that have finished (ESPN status = final)
2. Fetches boxscores from ESPN
3. Resolves predictions with actual values
4. Reports cumulative accuracy with bookmaker lines

Usage:
    python scripts/monitor_and_resolve.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Game, Prediction, Player
import httpx


async def get_espn_game_status(espn_id: str) -> dict:
    """Get game status from ESPN."""
    async with httpx.AsyncClient() as client:
        url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={espn_id}'
        try:
            resp = await client.get(url, timeout=30.0)
            data = resp.json()

            header = data.get('header', {})
            competitions = header.get('competitions', [])
            if competitions:
                status = competitions[0].get('status', {})
                return {
                    'state': status.get('type', {}).get('state', 'unknown'),
                    'detail': status.get('type', {}).get('detail', 'unknown'),
                    'id': espn_id
                }
        except Exception as e:
            print(f"Error fetching ESPN data: {e}")

    return {'state': 'unknown', 'id': espn_id}


async def resolve_game(game_id: str, espn_id: str) -> dict:
    """Resolve predictions for a single game using ESPN boxscore."""
    db = SessionLocal()

    try:
        async with httpx.AsyncClient() as client:
            url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={espn_id}'
            resp = await client.get(url, timeout=30.0)
            data = resp.json()

        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            return {'error': 'Game not found'}

        # Update game status
        game.status = 'final'

        boxscore = data.get('boxscore', {})
        players = boxscore.get('players', [])

        resolved = 0
        over_wins, over_total = 0, 0
        under_wins, under_total = 0, 0

        for team_data in players:
            statistics = team_data.get('statistics', [])
            if not statistics:
                continue

            first = statistics[0]
            athletes = first.get('athletes', [])

            for ath in athletes:
                athlete = ath.get('athlete', {})
                name = athlete.get('displayName')
                stats = ath.get('stats', [])

                if len(stats) < 7:
                    continue

                try:
                    pts = int(stats[1])
                    reb = int(stats[5])
                    ast = int(stats[6])

                    threes_str = stats[3]
                    if '-' in threes_str:
                        threes = int(threes_str.split('-')[0])
                    else:
                        threes = int(threes_str)

                    # Find matching predictions
                    predictions = db.query(Prediction).join(Player).filter(
                        Player.name.ilike(f'%{name.split()[-1]}%'),
                        Prediction.game_id == game_id,
                        Prediction.actual_value.is_(None)
                    ).all()

                    for p in predictions:
                        actual = None
                        if p.stat_type == 'points':
                            actual = pts
                        elif p.stat_type == 'rebounds':
                            actual = reb
                        elif p.stat_type == 'assists':
                            actual = ast
                        elif p.stat_type == 'threes':
                            actual = threes

                        if actual is not None:
                            line = p.bookmaker_line or p.predicted_value

                            # Calculate was_correct using NEW logic (actual vs line)
                            was_correct = None
                            if p.recommendation == 'OVER':
                                was_correct = actual > line
                                over_total += 1
                                if was_correct:
                                    over_wins += 1
                            elif p.recommendation == 'UNDER':
                                was_correct = actual < line
                                under_total += 1
                                if was_correct:
                                    under_wins += 1

                            p.actual_value = actual
                            p.difference = abs(p.predicted_value - actual)
                            p.was_correct = was_correct
                            p.actuals_resolved_at = datetime.now(timezone.utc)
                            resolved += 1
                except Exception as e:
                    pass  # Skip players with parsing errors

        db.commit()

        return {
            'game': f'{game.away_team} @ {game.home_team}',
            'resolved': resolved,
            'over': f'{over_wins}/{over_total}',
            'under': f'{under_wins}/{under_total}'
        }

    except Exception as e:
        return {'error': str(e)}
    finally:
        db.close()


async def monitor_and_resolve(max_iterations: int = 30, interval: int = 120):
    """Monitor for completed games and resolve predictions."""
    db = SessionLocal()

    try:
        print("=" * 70)
        print("MONITORING NBA GAMES FOR COMPLETION")
        print("=" * 70)
        print(f"Checking every {interval} seconds, max {max_iterations} iterations")
        print()

        for i in range(max_iterations):
            # Get games with predictions that have bookmaker lines
            games = db.query(Game).join(Prediction).filter(
                Prediction.bookmaker_line.isnot(None),
                Prediction.actual_value.is_(None),
                Game.game_date >= datetime.now() - timedelta(hours=48),
                Game.game_date < datetime.now() + timedelta(days=2)
            ).distinct().order_by(Game.game_date).all()

            print(f"Iteration {i+1}/{max_iterations} - Checking {len(games)} games...")

            completed = []

            for game in games:
                # Check ESPN status
                espn_id = game.espn_game_id
                if not espn_id:
                    continue

                status = await get_espn_game_status(espn_id)

                if status['state'] == 'post':
                    print(f"  ✓ {game.away_team} @ {game.home_team}: FINAL - Resolving...")
                    result = await resolve_game(game.id, espn_id)

                    if 'error' not in result:
                        completed.append(result)
                        print(f"    Resolved {result.get('resolved', 0)} predictions: OVER {result.get('over', 'N/A')}, UNDER {result.get('under', 'N/A')}")
                    else:
                        print(f"    Error: {result['error']}")

            if completed:
                # Show cumulative stats
                print()
                await show_cumulative_accuracy()
                print()
            else:
                print("  No newly completed games")

            if i < max_iterations - 1:
                print(f"  Waiting {interval} seconds...")
                print()
                await asyncio.sleep(interval)

        print()
        print("=" * 70)
        print("MONITORING COMPLETE")
        print("=" * 70)
        await show_cumulative_accuracy()

    finally:
        db.close()


async def show_cumulative_accuracy():
    """Show cumulative accuracy for all resolved predictions with bookmaker lines."""
    db = SessionLocal()

    try:
        predictions = db.query(Prediction).filter(
            Prediction.bookmaker_line.isnot(None),
            Prediction.actual_value.isnot(None)
        ).all()

        if not predictions:
            print("No resolved predictions with bookmaker lines yet.")
            return

        stats = {'OVER': {'total': 0, 'wins': 0}, 'UNDER': {'total': 0, 'wins': 0}}

        for p in predictions:
            rec = p.recommendation
            if rec in ['OVER', 'UNDER'] and p.was_correct is not None:
                stats[rec]['total'] += 1
                if p.was_correct:
                    stats[rec]['wins'] += 1

        print("CUMULATIVE ACCURACY (with bookmaker lines):")
        print(f"  Total predictions: {len(predictions)}")

        for rec in ['OVER', 'UNDER']:
            total = stats[rec]['total']
            wins = stats[rec]['wins']
            rate = 100 * wins / total if total > 0 else 0
            print(f"  {rec}: {wins}/{total} = {rate:.1f}%")

        # Breakdown by stat type
        print()
        print("By stat type:")
        for stat in ['points', 'rebounds', 'assists', 'threes']:
            stat_preds = [p for p in predictions if p.stat_type == stat and p.recommendation in ['OVER', 'UNDER']]
            if stat_preds:
                over = [p for p in stat_preds if p.recommendation == 'OVER']
                under = [p for p in stat_preds if p.recommendation == 'UNDER']

                over_wins = sum(1 for p in over if p.was_correct)
                under_wins = sum(1 for p in under if p.was_correct)
                over_total = len(over)
                under_total = len(under)

                over_rate = 100 * over_wins / over_total if over_total > 0 else 0
                under_rate = 100 * under_wins / under_total if under_total > 0 else 0

                print(f"  {stat.upper()}: OVER {over_wins}/{over_total} ({over_rate:.1f}%) | UNDER {under_wins}/{under_total} ({under_rate:.1f}%)")

    finally:
        db.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Monitor and resolve NBA games")
    parser.add_argument('--iterations', type=int, default=30, help='Max iterations')
    parser.add_argument('--interval', type=int, default=120, help='Check interval in seconds')

    args = parser.parse_args()

    asyncio.run(monitor_and_resolve(args.iterations, args.interval))
