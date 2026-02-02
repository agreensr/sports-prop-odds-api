"""API adapters for normalizing data from external sources.

This module provides adapters that transform data from external sports APIs
into a consistent format for the sync orchestrator.

Available adapters:
- nba_api_adapter: NBA.com API adapter
- odds_api_adapter: TheOddsApi.com adapter

Base classes:
- BaseAPIAdapter: Shared retry logic and common patterns
- SportAdapter: Config-driven generic adapter
"""
from app.services.core.base_api_adapter import (
    BaseAPIAdapter,
    SportAdapter,
    SPORT_CONFIG,
    get_sport_adapter
)
from app.services.sync.adapters.nba_api_adapter import NbaApiAdapter
from app.services.sync.adapters.odds_api_adapter import OddsApiAdapter

__all__ = [
    "BaseAPIAdapter",
    "SportAdapter",
    "SPORT_CONFIG",
    "get_sport_adapter",
    "NbaApiAdapter",
    "OddsApiAdapter",
]
