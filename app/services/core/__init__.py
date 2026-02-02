"""
Core services that work across all sports.

⚠️  IMPORTANT: Only add services here that work for ALL sports.

This module contains generic business logic that is not sport-specific:
- base_prediction_service: Base class for all sport-specific prediction services
- base_api_adapter: Base class for all sport-specific API adapters
- accuracy_service: Accuracy metrics calculation
- bet_tracking_service: Bet placement and tracking
- parlay_service: Parlay construction and management
- odds_api_service: Odds API client (sport-agnostic)
- multi_sport_service: Multi-sport prediction coordinator
- single_bet_service: Single bet generation (multi-sport)
- enhanced_parlay_service: 2-leg parlay generation (multi-sport)

For SPORT-SPECIFIC services, use:
- app/services/nba/     → NBA-specific services
- app/services/nfl/     → NFL-specific services
- app/services/mlb/     → MLB-specific services
- app/services/nhl/     → NHL-specific services

Examples:
- ✅ CORRECT: app/services/core/accuracy_service.py (works for any sport)
- ✅ CORRECT: app/services/nba/prediction_service.py (NBA-specific logic)
- ❌ WRONG: app/services/core/nba_prediction_service.py (redundant "nba" in core)
"""
from app.services.core.base_prediction_service import BasePredictionService
from app.services.core.base_api_adapter import (
    BaseAPIAdapter,
    SportAdapter,
    SPORT_CONFIG,
    get_sport_adapter
)
from app.services.core.multi_sport_service import (
    MultiSportPredictionService,
    get_multi_sport_service
)

__all__ = [
    "BasePredictionService",
    "BaseAPIAdapter",
    "SportAdapter",
    "SPORT_CONFIG",
    "get_sport_adapter",
    "MultiSportPredictionService",
    "get_multi_sport_service",
]
