"""
Database models for NBA Player Prop Prediction API.
Models are designed to match the existing database schema exactly.
"""
from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, DateTime, Date, ForeignKey, Boolean, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Player(Base):
    """NBA Player model with support for multiple external ID sources (ESPN, NBA)."""
    __tablename__ = "players"

    id = Column(String(36), primary_key=True)  # character varying(36)
    external_id = Column(String(100), unique=True, nullable=False, index=True)  # NBA or ESPN ID
    id_source = Column(String(10), nullable=False, index=True, default='nba')  # 'nba' or 'espn'
    nba_api_id = Column(Integer, nullable=True, index=True)  # nba_api numeric ID (for nba_api package)
    name = Column(String(255), nullable=False, index=True)
    team = Column(String(3), nullable=False, index=True)  # Team abbreviation (3 chars)
    position = Column(String(10))
    active = Column(Boolean, nullable=False, index=True)
    last_roster_check = Column(DateTime, nullable=True, index=True)  # Last validated against nba_api
    data_source = Column(String(50), nullable=True, index=True)  # nba_api, espn, manual, etc.
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    predictions = relationship("Prediction", back_populates="player", cascade="all, delete-orphan")
    stats = relationship("PlayerStats", back_populates="player", cascade="all, delete-orphan")
    injuries = relationship("PlayerInjury", backref="player", cascade="all, delete-orphan")
    lineup_entries = relationship("ExpectedLineup", backref="player", cascade="all, delete-orphan")
    season_stats = relationship("PlayerSeasonStats", back_populates="player", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_players_external_id', 'external_id'),
        Index('ix_players_id_source', 'id_source'),
    )


class Game(Base):
    """NBA Game model with support for multiple external ID sources (ESPN, NBA)."""
    __tablename__ = "games"

    id = Column(String(36), primary_key=True)
    external_id = Column(String(100), unique=True, nullable=False, index=True)  # NBA or ESPN game ID
    id_source = Column(String(10), nullable=False, index=True, default='nba')  # 'nba' or 'espn'
    game_date = Column(DateTime, nullable=False, index=True)  # timestamp, not date
    away_team = Column(String(3), nullable=False)  # Team abbreviation (3 chars)
    home_team = Column(String(3), nullable=False)  # Team abbreviation (3 chars)
    season = Column(Integer, nullable=False, index=True)  # Season year
    status = Column(String(50), nullable=False, index=True)  # scheduled, in_progress, final
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    predictions = relationship("Prediction", back_populates="game", cascade="all, delete-orphan")
    odds = relationship("GameOdds", back_populates="game", cascade="all, delete-orphan")
    injuries = relationship("PlayerInjury", foreign_keys="PlayerInjury.game_id", cascade="all, delete-orphan")
    expected_lineups = relationship("ExpectedLineup", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_games_external_id', 'external_id'),
        Index('ix_games_id_source', 'id_source'),
    )


class Prediction(Base):
    """AI-generated player prop predictions with odds pricing from bookmakers."""
    __tablename__ = "predictions"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    stat_type = Column(String(50), nullable=False)  # points, rebounds, assists, threes, etc.
    predicted_value = Column(Float, nullable=False)
    bookmaker_line = Column(Float, nullable=True)
    bookmaker_name = Column(String(100), nullable=True)
    recommendation = Column(String(10), nullable=False)  # OVER, UNDER
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    model_version = Column(String(50), nullable=True)
    # Odds pricing fields
    over_price = Column(Float, nullable=True)  # American odds for OVER bet (e.g., -110, +150)
    under_price = Column(Float, nullable=True)  # American odds for UNDER bet
    odds_fetched_at = Column(DateTime, nullable=True)  # When odds were first fetched
    odds_last_updated = Column(DateTime, nullable=True, index=True)  # Last odds update
    created_at = Column(DateTime, nullable=False, index=True)

    # Accuracy tracking fields
    actual_value = Column(Float, nullable=True)  # Actual stat value from game
    difference = Column(Float, nullable=True)  # |predicted - actual|
    was_correct = Column(Boolean, nullable=True)  # Was recommendation correct?
    actuals_resolved_at = Column(DateTime, nullable=True, index=True)  # When actuals were populated

    # Relationships
    player = relationship("Player", back_populates="predictions")
    game = relationship("Game", back_populates="predictions")

    __table_args__ = (
        Index('ix_predictions_odds_last_updated', 'odds_last_updated'),
        Index('ix_predictions_actuals_resolved', 'actuals_resolved_at'),
        Index('ix_predictions_accuracy_lookup', 'game_id', 'stat_type', 'actuals_resolved_at'),
    )


class PlayerStats(Base):
    """Player statistics for games."""
    __tablename__ = "player_stats"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    points = Column(Integer, nullable=True)
    rebounds = Column(Integer, nullable=True)
    assists = Column(Integer, nullable=True)
    threes = Column(Integer, nullable=True)
    minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    # Note: Additional columns exist in DB (field_goals_made, field_goals_attempted, etc.)
    # but are not currently modeled here

    # Relationships
    player = relationship("Player", back_populates="stats")
    game = relationship("Game")


class GameOdds(Base):
    """Game-level betting odds from bookmakers via The Odds API."""
    __tablename__ = "game_odds"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    bookmaker_key = Column(String(50), nullable=False, index=True)  # Internal bookmaker identifier
    bookmaker_title = Column(String(100), nullable=False)  # Display name

    # Moneyline odds
    home_moneyline = Column(Float, nullable=True)  # American odds for home team
    away_moneyline = Column(Float, nullable=True)  # American odds for away team

    # Spread odds
    home_spread_point = Column(Float, nullable=True)  # Home team spread
    home_spread_price = Column(Float, nullable=True)  # American odds for home spread
    away_spread_point = Column(Float, nullable=True)  # Away team spread
    away_spread_price = Column(Float, nullable=True)  # American odds for away spread

    # Totals (over/under)
    totals_point = Column(Float, nullable=True)  # The totals line
    over_price = Column(Float, nullable=True)  # American odds for over
    under_price = Column(Float, nullable=True)  # American odds for under

    last_update = Column(DateTime, nullable=False, index=True)  # When odds were last updated
    created_at = Column(DateTime, nullable=False)

    # Relationships
    game = relationship("Game", back_populates="odds")

    __table_args__ = (
        Index('ix_game_odds_bookmaker', 'bookmaker_key'),
        Index('ix_game_odds_last_update', 'last_update'),
    )


class NewsEvent(Base):
    """NBA news and injury updates."""
    __tablename__ = "news_events"

    id = Column(String(36), primary_key=True)
    external_id = Column(String(100), unique=True, nullable=True)
    headline = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(String(50), nullable=False, index=True)  # injury, trade, news, etc.
    source = Column(String(100), nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_news_published', 'published_at'),
        Index('ix_news_type', 'event_type'),
    )


class Parlay(Base):
    """Generated parlay bets combining multiple player prop predictions."""
    __tablename__ = "parlays"

    id = Column(String(36), primary_key=True)
    parlay_type = Column(String(20), nullable=False, index=True)  # 'same_game' or 'multi_game'

    # Odds and pricing
    calculated_odds = Column(Float, nullable=False)  # American odds (e.g., +350)
    implied_probability = Column(Float, nullable=False)
    expected_value = Column(Float, nullable=False, index=True)  # EV as decimal (0.05 = +5%)
    confidence_score = Column(Float, nullable=False)

    # Metadata
    total_legs = Column(Integer, nullable=False)
    correlation_score = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)

    # Relationships
    legs = relationship("ParlayLeg", back_populates="parlay", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_parlays_type', 'parlay_type'),
        Index('ix_parlays_ev', 'expected_value'),
        Index('ix_parlays_created', 'created_at'),
    )


class ParlayLeg(Base):
    """Individual leg within a parlay bet."""
    __tablename__ = "parlay_legs"

    id = Column(String(36), primary_key=True)
    parlay_id = Column(String(36), ForeignKey("parlays.id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_id = Column(String(36), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, index=True)

    leg_order = Column(Integer, nullable=False)
    selection = Column(String(10), nullable=False)  # 'OVER' or 'UNDER'
    leg_odds = Column(Float, nullable=False)
    leg_confidence = Column(Float, nullable=False)
    correlation_with_parlay = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False)

    # Relationships
    parlay = relationship("Parlay", back_populates="legs")
    prediction = relationship("Prediction")

    __table_args__ = (
        Index('ix_parlay_legs_parlay_id', 'parlay_id'),
        Index('ix_parlay_legs_prediction_id', 'prediction_id'),
    )


class PlacedBet(Base):
    """Actual bets placed on sportsbook platforms (FanDuel, DraftKings, etc.)."""
    __tablename__ = "placed_bets"

    id = Column(String(36), primary_key=True)
    sportsbook = Column(String(50), nullable=False, index=True)  # 'FanDuel', 'DraftKings', etc.
    bet_id = Column(String(100), nullable=False, index=True)  # Sportsbook's bet ID
    bet_type = Column(String(20), nullable=False, index=True)  # 'same_game_parlay', 'multi_game_parlay', 'straight'

    # Game info
    game_id = Column(String(36), ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True)
    matchup = Column(String(100), nullable=False)  # "IND @ BOS"
    game_date = Column(DateTime, nullable=False, index=True)

    # Bet details
    wager_amount = Column(Float, nullable=False)  # Amount bet
    total_charged = Column(Float, nullable=False)  # Including fees
    odds = Column(Integer, nullable=False)  # American odds (+760, +333, etc.)
    to_win = Column(Float, nullable=False)  # Potential profit
    total_payout = Column(Float, nullable=False)  # Total return (wager + profit)

    # Status tracking
    status = Column(String(20), nullable=False, index=True, default='pending')  # 'pending', 'won', 'lost', 'push', 'cashed_out'
    cash_out_value = Column(Float, nullable=True)  # If cashed out early
    actual_payout = Column(Float, nullable=True)  # Actual amount received
    profit_loss = Column(Float, nullable=True)  # Actual profit/loss

    # Timestamps
    placed_at = Column(DateTime, nullable=False, index=True)
    settled_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)

    # Relationships
    legs = relationship("PlacedBetLeg", backref="bet", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_placed_bets_sportsbook', 'sportsbook'),
        Index('ix_placed_bets_status', 'status'),
        Index('ix_placed_bets_game_date', 'game_date'),
    )


class PlacedBetLeg(Base):
    """Individual legs within placed bets."""
    __tablename__ = "placed_bet_legs"

    id = Column(String(36), primary_key=True)
    bet_id = Column(String(36), ForeignKey("placed_bets.id", ondelete="CASCADE"), nullable=False, index=True)

    # Player info
    player_name = Column(String(255), nullable=False)
    player_team = Column(String(10), nullable=False)

    # Bet details
    stat_type = Column(String(50), nullable=False)  # 'points', 'assists', 'threes', etc.
    selection = Column(String(10), nullable=False)  # 'OVER', 'UNDER'
    line = Column(Float, nullable=True)  # The line (9.5, 2.5, etc.)
    special_bet = Column(String(100), nullable=True)  # 'To Score 15+ Points', etc.

    # Model prediction tracking
    predicted_value = Column(Float, nullable=True)  # Our model's prediction
    model_confidence = Column(Float, nullable=True)  # Model confidence (0.0-1.0)
    recommendation = Column(String(10), nullable=True)  # 'OVER', 'UNDER' from model

    # Result tracking
    result = Column(String(20), nullable=True)  # 'won', 'lost', 'pending', 'push'
    actual_value = Column(Float, nullable=True)  # Actual stat value achieved
    was_correct = Column(Boolean, nullable=True)  # Did the bet win?

    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_placed_bet_legs_bet_id', 'bet_id'),
    )


class PlayerInjury(Base):
    """Track player injury status and impact."""
    __tablename__ = "player_injuries"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True)

    # Injury details
    injury_type = Column(String(100), nullable=True)  # "knee", "ankle", "illness", etc.
    status = Column(String(50), nullable=False, index=True)  # out, doubtful, questionable, day-to-day, returning, available
    impact_description = Column(Text, nullable=True)  # Free text description

    # Return tracking (for "returning" status)
    days_since_return = Column(Integer, nullable=True)  # Days since returning from injury
    minutes_restriction = Column(Integer, nullable=True)  # If on minutes restriction
    games_played_since_return = Column(Integer, nullable=True)  # To track progression

    # Timing
    reported_date = Column(Date, nullable=False, index=True)
    return_date = Column(Date, nullable=True, index=True)  # When player returned
    external_source = Column(String(100), nullable=True)  # "espn", "nba_official", etc.

    # Metadata
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('ix_player_injuries_player_status', 'player_id', 'status'),
        Index('ix_player_injuries_game_id', 'game_id'),
        Index('ix_player_injuries_return_date', 'return_date'),
    )


class ExpectedLineup(Base):
    """Projected starting lineups and minutes allocations."""
    __tablename__ = "expected_lineups"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=True, index=True)
    team = Column(String(3), nullable=False)  # 3-letter team code (BOS, LAL, etc.)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)

    # Lineup details
    starter_position = Column(String(10), nullable=True)  # PG, SG, SF, PF, C, or None for bench
    is_confirmed = Column(Boolean, default=False, nullable=False)  # True = official, False = projected
    minutes_projection = Column(Integer, nullable=True)  # Expected minutes

    # Metadata
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_expected_lineups_game_team', 'game_id', 'team'),
    )


class PlayerSeasonStats(Base):
    """Cached player season-averaged per-36 stats from nba_api.

    This table stores aggregated player statistics from recent games
    to improve prediction accuracy. Data is fetched from nba_api and
    cached here with a 24-hour TTL.

    Key benefit: Uses player's actual per-36 efficiency instead of
    position averages, dramatically improving prediction accuracy.
    """
    __tablename__ = "player_season_stats"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    season = Column(String(10), nullable=False, index=True)  # e.g., "2024-25"

    # Averages from recent games (typically 10-20)
    games_count = Column(Integer, nullable=False)  # Number of games averaged
    points_per_36 = Column(Float, nullable=False)
    rebounds_per_36 = Column(Float, nullable=False)
    assists_per_36 = Column(Float, nullable=False)
    threes_per_36 = Column(Float, nullable=False)
    avg_minutes = Column(Float, nullable=False)  # Average minutes played

    # Tracking
    last_game_date = Column(Date, nullable=True)  # Date of most recent game included
    fetched_at = Column(DateTime, nullable=False, index=True)  # When this cache entry was created
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    player = relationship("Player", back_populates="season_stats")

    __table_args__ = (
        UniqueConstraint('player_id', 'season', name='uq_player_season'),
        Index('ix_player_season_stats_player_season', 'player_id', 'season'),
        Index('ix_player_season_stats_fetched_at', 'fetched_at'),
    )


class HistoricalOddsSnapshot(Base):
    """Historical bookmaker odds snapshots for hit rate calculation and value detection.

    This table captures point-in-time player prop odds from bookmakers,
    then resolves them against actual game results to calculate hit rates.

    Hit rates measure how consistently a player hits OVER/UNDER on their
    betting lines, which is used to weight prediction confidence.

    Example: If LeBron James has hit his assist OVER in 8 of 10 games,
    future assist predictions get a confidence boost.

    Opening Odds Tracking:
    - is_opening_line: TRUE for the first odds captured (opening line)
    - line_movement: Difference from opening (current_line - opening_line)
    - Value is found when line moves but prediction remains stable
    """
    __tablename__ = "historical_odds_snapshots"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)

    # Odds details
    stat_type = Column(String(50), nullable=False, index=True)  # points, rebounds, assists, threes
    bookmaker_name = Column(String(100), nullable=False, index=True)  # FanDuel, DraftKings
    bookmaker_line = Column(Float, nullable=False)  # The line (e.g., 23.5)
    over_price = Column(Float, nullable=True)  # American odds for OVER
    under_price = Column(Float, nullable=True)  # American odds for UNDER

    # Snapshot timing
    snapshot_time = Column(DateTime, nullable=False, index=True)  # When odds were captured

    # Opening odds tracking
    is_opening_line = Column(Boolean, default=False, nullable=False, index=True)  # TRUE if first snapshot
    line_movement = Column(Float, default=0.0, nullable=False)  # Current line - opening line

    # Starter filtering
    was_starter = Column(Boolean, default=False, nullable=False, index=True)

    # Resolution (after game completion)
    actual_value = Column(Float, nullable=True)
    hit_result = Column(String(10), nullable=True, index=True)  # 'OVER', 'UNDER', 'PUSH'
    resolved_at = Column(DateTime, nullable=True, index=True)

    # Metadata
    created_at = Column(DateTime, nullable=False)

    # Relationships
    game = relationship("Game")
    player = relationship("Player")

    __table_args__ = (
        Index('ix_historical_odds_player_stat', 'player_id', 'stat_type'),
        Index('ix_historical_odds_bookmaker', 'bookmaker_name'),
        Index('ix_historical_odds_hit_result', 'hit_result'),
        Index('ix_historical_odds_opening_comparison', 'game_id', 'player_id', 'stat_type', 'bookmaker_name', 'snapshot_time'),
    )


class GameMapping(Base):
    """Maps nba_api games to The Odds API events for data correlation.

    This table is the foundation of the data sync layer, linking games from
    two independent APIs (nba_api for stats, The Odds API for betting lines).

    Matching priority (confidence):
    - 1.0: Exact match (same date + both teams match via team_mappings)
    - 0.95: Fuzzy time match (same date + teams + time within 2 hours)
    - 0.85: Team name fuzzy match (Levenshtein distance < 3)

    Only games with match_confidence >= 0.85 should be used for predictions.
    """
    __tablename__ = "game_mappings"

    id = Column(String(36), primary_key=True)
    nba_game_id = Column(String(20), unique=True, nullable=False, index=True)  # From nba_api
    nba_home_team_id = Column(Integer, nullable=False)  # nba_api team ID
    nba_away_team_id = Column(Integer, nullable=False)  # nba_api team ID
    odds_event_id = Column(String(64), unique=True, nullable=True, index=True)  # From The Odds API
    odds_sport_key = Column(String(32), nullable=False, default='basketball_nba')
    game_date = Column(Date, nullable=False, index=True)
    game_time = Column(DateTime, nullable=True)  # Can be null if not known
    match_confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    match_method = Column(String(32), nullable=False)  # exact, fuzzy_time, fuzzy_team_name, manual
    status = Column(String(16), nullable=False, default='pending', index=True)  # pending, matched, failed, manual_review
    last_validated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_game_mappings_date', 'game_date'),
        Index('ix_game_mappings_status', 'status'),
        Index('ix_game_mappings_confidence', 'match_confidence'),
    )


class PlayerAlias(Base):
    """Canonical player name mappings across different data sources.

    Resolves player identity variations between APIs:
    - Suffixes: "Jr.", "Sr.", "III", "IV"
    - Punctuation: "P.J. Tucker" vs "PJ Tucker"
    - Accents: "Luka Dončić" vs "Luka Doncic"
    - Nicknames: "Steph" vs "Stephen"

    Pipeline for resolving players:
    1. Exact lookup in player_aliases table
    2. Normalized comparison (remove suffixes, lowercase, remove punctuation)
    3. Fuzzy match (Levenshtein, Jaro-Winkler)
    4. Team context match (same team + similar name)
    """
    __tablename__ = "player_aliases"

    id = Column(String(36), primary_key=True)
    nba_player_id = Column(Integer, nullable=False, index=True)  # Canonical nba_api ID
    canonical_name = Column(String(128), nullable=False, index=True)  # Official name from nba_api
    alias_name = Column(String(128), nullable=False, index=True)  # Alternate name from other sources
    alias_source = Column(String(32), nullable=False, index=True)  # nba_api, odds_api, espn, etc.
    match_confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    is_verified = Column(Boolean, nullable=False, default=False, index=True)  # Manually verified?
    created_at = Column(DateTime, nullable=False)
    verified_by = Column(String(64), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('alias_name', 'alias_source', name='uq_player_alias_source'),
        Index('ix_player_aliases_canonical', 'canonical_name'),
        Index('ix_player_aliases_alias', 'alias_name'),
        Index('ix_player_aliases_nba_id', 'nba_player_id'),
        Index('ix_player_aliases_source', 'alias_source'),
        Index('ix_player_aliases_verified', 'is_verified'),
    )


class TeamMapping(Base):
    """Team name and ID mappings between nba_api and The Odds API.

    Provides consistent team identification across APIs with support for
    alternate names and abbreviations. Used by the game matcher to correlate
    games from different sources.

    Key mappings:
    - nba_team_id: Numeric ID from nba_api (e.g., 1610612738 for Boston)
    - nba_abbreviation: 3-letter code (BOS, LAL, etc.)
    - odds_api_key: The Odds API identifier (bostonceltics, etc.)
    - alternate_names: JSONB array of variations
    """
    __tablename__ = "team_mappings"

    id = Column(String(36), primary_key=True)
    nba_team_id = Column(Integer, unique=True, nullable=False)
    nba_abbreviation = Column(String(3), nullable=False, index=True)
    nba_full_name = Column(String(64), nullable=False)
    nba_city = Column(String(32), nullable=False)
    odds_api_name = Column(String(64), nullable=True)
    odds_api_key = Column(String(32), nullable=True, index=True)
    alternate_names = Column(Text, nullable=False, default='[]')  # JSONB stored as Text for SQLAlchemy
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_team_mappings_abbreviation', 'nba_abbreviation'),
        Index('ix_team_mappings_odds_key', 'odds_api_key'),
    )


class SyncMetadata(Base):
    """Tracks sync job status and health metrics for all data sources.

    Monitors the health of the data sync layer by tracking:
    - Last sync time (started and completed)
    - Success/failure rates
    - Records processed vs matched vs failed
    - Sync duration

    Used by the orchestrator to schedule retries and monitor overall sync health.
    """
    __tablename__ = "sync_metadata"

    id = Column(String(36), primary_key=True)
    source = Column(String(32), nullable=False)  # nba_api, odds_api, espn
    data_type = Column(String(32), nullable=False)  # games, odds, player_stats
    last_sync_started_at = Column(DateTime, nullable=True)
    last_sync_completed_at = Column(DateTime, nullable=True, index=True)
    last_sync_status = Column(String(16), nullable=True, index=True)  # success, failed, in_progress, partial
    records_processed = Column(Integer, nullable=False, default=0)
    records_matched = Column(Integer, nullable=False, default=0)
    records_failed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    sync_duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint('source', 'data_type', name='uq_sync_metadata_source_type'),
        Index('ix_sync_metadata_source_type', 'source', 'data_type'),
        Index('ix_sync_metadata_status', 'last_sync_status'),
        Index('ix_sync_metadata_completed', 'last_sync_completed_at'),
    )


class MatchAuditLog(Base):
    """Audit trail for all matches and changes to mapping data.

    Provides complete traceability for:
    - Game matches (nba_game_id ↔ odds_event_id)
    - Player resolutions (alias → canonical_name)
    - Team mappings (odds_api_key → nba_team_id)

    Essential for debugging data issues and maintaining data integrity.
    """
    __tablename__ = "match_audit_log"

    id = Column(String(36), primary_key=True)
    entity_type = Column(String(16), nullable=False)  # game, player, team
    entity_id = Column(String(64), nullable=False)  # ID of the entity
    action = Column(String(16), nullable=False, index=True)  # created, updated, deleted, matched, unmapped
    previous_state = Column(Text, nullable=True)  # JSONB stored as Text
    new_state = Column(Text, nullable=True)  # JSONB stored as Text
    match_details = Column(Text, nullable=True)  # JSONB with confidence, method, etc.
    performed_by = Column(String(64), nullable=True, index=True)  # System or user
    created_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('ix_audit_entity', 'entity_type', 'entity_id'),
        Index('ix_audit_created', 'created_at'),
        Index('ix_audit_action', 'action'),
        Index('ix_audit_performed_by', 'performed_by'),
    )
