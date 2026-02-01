import asyncio
import sys
sys.path.insert(0, '/home/sean/sports-bet-ai-api')

from app.core.database import SessionLocal
from app.models import Game, Prediction, Player
from datetime import datetime, timezone
import httpx

async def resolve():
    db = SessionLocal()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401810552')
            data = resp.json()

        game = db.query(Game).filter(
            Game.away_team.in_(['SAS', 'SA']),
            Game.home_team == 'CHA',
            Game.game_date >= '2026-01-31'
        ).first()

        if not game:
            print('Game not found')
            return

        print('Resolving: SA @ CHA')

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

                pts = int(stats[1])
                reb = int(stats[5])
                ast = int(stats[6])

                threes_str = stats[3]
                if '-' in threes_str:
                    threes = int(threes_str.split('-')[0])
                else:
                    threes = int(threes_str)

                predictions = db.query(Prediction).join(Player).filter(
                    Player.name.ilike(f'%{name.split()[-1]}%'),
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

                        status = 'OK' if was_correct else 'X'
                        rec = p.recommendation[:4] if p.recommendation else 'NONE'
                        print(f'  [{status}] {p.stat_type}: pred={p.predicted_value:.1f} line={line:.1f} actual={actual:.1f} {rec}')

        db.commit()

        print()
        print('=== RESOLVED {} predictions ==='.format(resolved))
        if over_total > 0:
            print('OVER: {}/{} = {:.1f}%'.format(over_wins, over_total, 100*over_wins/over_total))
        if under_total > 0:
            print('UNDER: {}/{} = {:.1f}%'.format(under_wins, under_total, 100*under_wins/under_total))

    except Exception as e:
        print('Error: {}'.format(e))
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

asyncio.run(resolve())
