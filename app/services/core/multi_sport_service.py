"""
Multi-Sport Prediction Coordinator Service.

This service provides a unified interface for generating predictions
across all supported sports (NBA, NFL, MLB, NHL).

It delegates to sport-specific prediction services while providing:
- Consistent API across all sports
- Sport-specific prediction logic
- Unified error handling and logging
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models import Prediction as NBAPrediction
from app.models.nfl.models import Prediction as NFLPrediction
from app.models.mlb.models import Prediction as MLBPrediction
from app.models.nhl.models import Prediction as NHLPrediction

logger = logging.getLogger(__name__)


class MultiSportPredictionService:
    """
    Unified prediction service for all sports.

    Delegates to sport-specific services:
    - NBA: app/services/nba/prediction_service.py
    - NFL: app/services/nfl/prediction_service.py
    - MLB: app/services/mlb/prediction_service.py
    - NHL: app/services/nhl/prediction_service.py
    """

    # Sport model mappings
    SPORT_MODELS = {
        "nba": {
            "prediction": NBAPrediction,
            "service": "app.services.nba.prediction_service.PredictionService",
        },
        "nfl": {
            "prediction": NFLPrediction,
            "service": "app.services.nfl.prediction_service.PredictionService",
        },
        "mlb": {
            "prediction": MLBPrediction,
            "service": "app.services.mlb.prediction_service.PredictionService",
        },
        "nhl": {
            "prediction": NHLPrediction,
            "service": "app.services.nhl.prediction_service.PredictionService",
        },
    }

    def __init__(self, db: Session):
        """
        Initialize the multi-sport prediction service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self._services = {}  # Cache for sport-specific services

    def get_sport_service(self, sport_id: str):
        """
        Get the prediction service for a specific sport.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')

        Returns:
            Sport-specific prediction service instance

        Raises:
            ValueError: If sport_id is not supported
        """
        if sport_id not in self.SPORT_MODELS:
            raise ValueError(
                f"Unsupported sport: {sport_id}. "
                f"Supported sports: {list(self.SPORT_MODELS.keys())}"
            )

        # Return cached service if available
        if sport_id in self._services:
            return self._services[sport_id]

        # Import and instantiate the sport-specific service
        service_path = self.SPORT_MODELS[sport_id]["service"]
        module_path, class_name = service_path.rsplit(".", 1)

        try:
            module = __import__(module_path, fromlist=[class_name])
            service_class = getattr(module, class_name)
            self._services[sport_id] = service_class(self.db)
            return self._services[sport_id]
        except ImportError as e:
            logger.error(f"Failed to import service for {sport_id}: {e}")
            raise

    def generate_predictions_for_game(
        self,
        sport_id: str,
        game_id: str,
        stat_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate predictions for a specific game.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            game_id: Database UUID of the game
            stat_types: List of stat types to predict (default: sport-specific defaults)

        Returns:
            List of generated prediction dictionaries
        """
        service = self.get_sport_service(sport_id)
        return service.generate_predictions_for_game(game_id, stat_types)

    def generate_predictions_for_date(
        self,
        sport_id: str,
        target_date,
        stat_types: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Generate predictions for all games on a specific date.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            target_date: Date to generate predictions for
            stat_types: List of stat types to predict

        Returns:
            Dictionary mapping game_id to list of predictions
        """
        from datetime import date

        if isinstance(target_date, date):
            from datetime import datetime
            start_date = datetime.combine(target_date, datetime.min.time())
            end_date = datetime.combine(target_date, datetime.max.time())
        else:
            start_date = target_date
            end_date = target_date

        # Get games for the sport and date
        game_model = self._get_game_model(sport_id)
        games = self.db.query(game_model).filter(
            game_model.game_date >= start_date,
            game_model.game_date <= end_date,
            game_model.status == 'scheduled'
        ).all()

        if not games:
            logger.info(f"No games found for {sport_id} on {target_date}")
            return {}

        # Generate predictions for each game
        all_predictions = {}
        for game in games:
            try:
                predictions = self.generate_predictions_for_game(
                    sport_id, str(game.id), stat_types
                )
                if predictions:
                    all_predictions[str(game.id)] = predictions
            except Exception as e:
                logger.error(f"Failed to generate predictions for game {game.id}: {e}")
                continue

        logger.info(
            f"Generated predictions for {len(all_predictions)} {sport_id.upper()} games "
            f"on {target_date}"
        )

        return all_predictions

    def generate_all_sport_predictions(
        self,
        target_date,
        stat_types: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, List[Dict]]]:
        """
        Generate predictions for all sports on a specific date.

        Args:
            target_date: Date to generate predictions for
            stat_types: List of stat types to predict (default: sport-specific defaults)

        Returns:
            Dictionary mapping sport_id to game_id to predictions
        """
        all_sport_predictions = {}

        for sport_id in self.SPORT_MODELS.keys():
            try:
                sport_predictions = self.generate_predictions_for_date(
                    sport_id, target_date, stat_types
                )
                if sport_predictions:
                    all_sport_predictions[sport_id] = sport_predictions
            except Exception as e:
                logger.error(f"Failed to generate predictions for {sport_id}: {e}")
                continue

        return all_sport_predictions

    def get_supported_sports(self) -> List[str]:
        """Get list of supported sport identifiers."""
        return list(self.SPORT_MODELS.keys())

    def _get_game_model(self, sport_id: str):
        """Get the Game model for a specific sport."""
        sport_models = {
            "nba": "app.models.nba.models.Game",
            "nfl": "app.models.nfl.models.Game",
            "mlb": "app.models.mlb.models.Game",
            "nhl": "app.models.nhl.models.Game",
        }

        if sport_id not in sport_models:
            raise ValueError(f"Unsupported sport: {sport_id}")

        module_path, class_name = sport_models[sport_id].rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)


def get_multi_sport_service(db: Session) -> MultiSportPredictionService:
    """Get a MultiSportPredictionService instance."""
    return MultiSportPredictionService(db)
