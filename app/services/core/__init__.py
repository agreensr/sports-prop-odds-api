"""
Core services that work across all sports.

⚠️  IMPORTANT: Only add services here that work for ALL sports.

This module contains generic business logic that is not sport-specific:
- accuracy_service: Accuracy metrics calculation
- bet_tracking_service: Bet placement and tracking
- parlay_service: Parlay construction and management
- odds_api_service: Odds API client (sport-agnostic)

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
