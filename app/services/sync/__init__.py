"""
NBA Data Sync Service

Provides synchronization layer between nba_api (stats) and The Odds API (betting lines).

Key components:
- Matchers: Correlate games, players, and teams across APIs
- Adapters: Normalize data from existing API services
- Orchestrator: Coordinate sync jobs and monitoring
"""
