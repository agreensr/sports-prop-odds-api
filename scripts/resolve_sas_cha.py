"""Manually resolve SAS @ CHA game predictions using ESPN data."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Game, Prediction, Player
import httpx


async def resolve_sas_cha():
    """Resolve SAS @ CHA predictions using ESPN boxscore."""
    db = SessionLocal()

    try:
        espn_id = '401810552'

        # Get boxscore from ESPN
        async with httpx.AsyncClient() as client:
            url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={espn_id}'
            resp = await client.get(url)
            data = resp.json()

        # Get game from database
        game = db.query(Game).filter(
            Game.away_team.in_(['SAS', 'SA']),
            Game.home_team == 'CHA',
            Game.game_date >= '2026-01-31'
        ).first()

        if not game:
            print("Game not found in database")
            return

        print(f"Resolving: {game.away_team} @ {game.home_team}")
        print(f"ESPN ID: {espn_id}")

        # Update game status
        game.status = 'final'

        # Get player stats from ESPN boxscore
        boxscore = data.get('boxscore', {})
        players = boxscore.get('players', [])  # List of team data

        print(f"Teams in boxscore: {len(players)}")

        # Map keys to indices
        for team_data in players:
            team = team_data.get('team', {})
            abbr = team.get('abbreviation', '?')
            print(f"\n{abbr}:")

            statistics = team_data.get('statistics', [])
            if not statistics or len(statistics) == 0:
                print(f"  No statistics available")
                continue

            first_stat = statistics[0]
            keys = first_stat.get('keys', [])
            athletes = first_stat.get('athletes', [])

            # Find key indices
            key_indices = {}
            for key in ['points', 'rebounds', 'assists']:
                if key in keys:
                    key_indices[key] = keys.index(key)
                else:
                    # Try combined keys
                    for k in keys:
                        if k.startswith(key):
                            key_indices[key] = keys.index(k)
                            break

            print(f"  Key indices: {key_indices}")
            print(f"  Players: {len(athletes)}")

            # Process each player
            for ath in athletes:
                athlete = ath.get('athlete', {})
                name = athlete.get('displayName', 'Unknown')
                stats = ath.get('stats', [])

                # Extract stats (values may be like "4-6" for made-attempted)
                def parse_stat(idx):
                    if idx >= len(stats):
                        return 0
                    val = stats[idx]
                    if isinstance(val, int):
                        return val
                    if isinstance(val, str):
                        # Handle "4-6" format (made-attempted) - we want made
                        if '-' in val:
                            return int(val.split('-')[0])
                        return int(val)
                    return 0

                pts = parse_stat(key_indices.get('points', 0))
                reb = parse_stat(key_indices.get('rebounds', 0))
                ast = parse_stat(key_indices.get('assists', 0))

                # For threes, need to parse differently
                threes = 0
                for k_idx, k in enumerate(keys):
                    if 'threePointFieldGoalsMade' in k or k.startswith('3PT'):
                        val = stats[k_idx]
                        if isinstance(val, str) and '-' in val:
                            threes = int(val.split('-')[0])
                        elif isinstance(val, int):
                            threes = val
                        break

                print(f"    {name}: PTS={pts}, REB={reb}, AST={ast}, 3PM={threes}")

                # Find and resolve predictions
                # Try by full name first
                predictions = db.query(Prediction).join(Player).filter(
                    Player.name == name,
                    Prediction.game_id == game.id,
                    Prediction.actual_value.is_(None)
                ).all()

                # If not found, try by last name
                if not predictions:
                    last_name = name.split()[-1]
                    predictions = db.query(Prediction).join(Player).filter(
                        Player.name.ilike(f'%{last_name}%'),
                        Prediction.game_id == game.id,
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
                        elif p.recommendation == 'UNDER':
                            was_correct = actual < line

                        p.actual_value = actual
                        p.difference = abs(p.predicted_value - actual)
                        p.was_correct = was_correct
                        p.actuals_resolved_at = datetime.now(timezone.utc)

                        print(f"      ✓ {p.stat_type}: pred={p.predicted_value:.1f}, line={line:.1f}, actual={actual}, rec={p.recommendation}, correct={was_correct}")

        db.commit()

        # Show summary
        print("\n" + "="*60)
        print("ACCURACY SUMMARY (SAS @ CHA) - WITH BOOKIE LINES")
        print("="*60)

        final_preds = db.query(Prediction).filter(
            Prediction.game_id == game.id,
            Prediction.actual_value.isnot(None),
            Prediction.bookmaker_line.isnot(None)
        ).all()

        stats = {'OVER': {'total': 0, 'wins': 0}, 'UNDER': {'total': 0, 'wins': 0}}
        results = []

        for p in final_preds:
            if p.recommendation in ['OVER', 'UNDER']:
                stats[p.recommendation']]['total'] += 1
                if p.was_correct:
                    stats[p.recommendation]['wins'] += 1

                player_name = p.player.name if hasattr(p, 'player') else 'Unknown'
                results.append({
                    'player': player_name,
                    'stat': p.stat_type,
                    'rec': p.recommendation,
                    'pred': p.predicted_value,
                    'line': p.bookmaker_line,
                    'actual': p.actual_value,
                    'correct': p.was_correct
                })

        for rec in ['OVER', 'UNDER']:
            total = stats[rec]['total']
            wins = stats[rec]['wins']
            rate = 100 * wins / total if total > 0 else 0
            print(f'{rec}: {wins}/{total} = {rate:.1f}%')

        print("\nIndividual predictions:")
        for r in results:
            status = '✓' if r['correct'] else '✗'
            print(f"  {status} {r['player'][:15]:15} {r['stat']:8}: pred={r['pred']:5.1f}, line={r['line']:5.1f}, actual={r['actual']:5.1f}, {r['rec']:4}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    asyncio.run(resolve_sas_cha())
