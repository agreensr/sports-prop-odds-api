"""Regenerate predictions with real Odds API lines."""
import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Game, Prediction
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.services.core.odds_api_service import OddsApiService

async def regenerate_with_odds():
    db = SessionLocal()

    # Get games with Odds API event IDs
    games = db.query(Game).filter(
        Game.odds_api_event_id.isnot(None),
        Game.game_date >= datetime.now()
    ).limit(5).all()

    print(f'Found {len(games)} games with Odds API IDs')

    # Initialize service with Odds API
    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds_service = OddsApiService(api_key)
    service = EnhancedPredictionService(db, odds_api_service=odds_service)

    for game in games:
        print(f'\n{game.away_team} @ {game.home_team}')
        print('-' * 40)

        # Delete old predictions for this game
        old = db.query(Prediction).filter(Prediction.game_id == game.id).delete()
        print(f'Deleted {old} old predictions')

        # Generate predictions with real odds
        predictions = service.generate_prop_predictions(
            game_id=game.id,
            stat_types=['points'],
            bookmaker='fanduel'
        )

        print(f'Generated {len(predictions)} new predictions:')
        for p in predictions:
            player = p.get('player', 'Unknown')
            proj = p.get('projected', 0)
            line = p.get('line', 0)
            rec = p.get('recommendation', 'PASS')
            conf = int(p.get('confidence', 0) * 100)
            edge = p.get('edge', 0)
            line_source = p.get('line_source', 'odds_api')
            print(f'  {player:20} | {proj:5.1f} vs {line:5.1f} | {rec:4} | {conf}% | Edge: {edge:+5.1f} | [{line_source}]')

            # Save to database
            new_pred = Prediction(
                id=str(uuid.uuid4()),
                sport_id='nba',
                game_id=game.id,
                player_id=p.get('player_id'),
                stat_type='points',
                predicted_value=proj,
                bookmaker_line=line,
                bookmaker_name='fanduel',
                recommendation=rec,
                confidence=conf / 100,
                model_version='2.2.0-odds-api',
                created_at=datetime.now()
            )
            db.add(new_pred)

        db.commit()

    db.close()
    await odds_service.close()

    print('\nDone!')

if __name__ == '__main__':
    asyncio.run(regenerate_with_odds())
