"""
Unified Multi-Sport Models for Sports-Bet-AI-API.

This module contains database models that work across all sports (NBA, NFL, MLB, NHL).
The models use a unified table architecture with sport_id discriminators and nullable
sport-specific fields.

Architecture Decision (P1 #5): Full Unification
- Single set of tables for all sports
- Sport-specific fields are nullable (sparse column approach)
- Filter by sport_id for sport-specific queries
- Simpler cross-sport queries and reporting

Migration Path:
- Database already uses unified tables
- Models renamed from app.models.nba to app.models.unified
- Sport-specific fields added as nullable columns
"""
from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, DateTime, Date, ForeignKey, Boolean, Text, Index, UniqueConstraint, JSON
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# =============================================================================
# SPORT REGISTRY
# =============================================================================

class Sport(Base):
    """Sports registry for multi-sport support."""
    __tablename__ = "sports"

    id = Column(String(3), primary_key=True)  # 'nba', 'nfl', 'mlb', 'nhl'
    name = Column(String(50), nullable=False)  # Display name
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_sports_active', 'active'),
    )


# =============================================================================
# PLAYER MODEL (Multi-Sport)
# =============================================================================

class Player(Base):
    """
    Unified Player model for all sports.

    Sport-specific fields are nullable and only populated for relevant sports:
    - NBA/NBA/MLB: jersey_number, height, weight
    - NFL: college, draft_year, jersey_number
    - NHL: catches (L/R), birth_date
    - MLB: bats (L/R/S), throws (L/R)

    Query by sport:
        nba_players = Player.query.filter(Player.sport_id == 'nba').all()
        all_players = Player.query.all()
    """
    __tablename__ = "players"

    id = Column(String(36), primary_key=True)

    # Multi-sport support
    sport_id = Column(String(3), ForeignKey("sports.id"), nullable=False, index=True, default='nba')

    # Legacy fields (for backward compatibility)
    external_id = Column(String(100), unique=True, nullable=False, index=True)  # Deprecated
    id_source = Column(String(10), nullable=False, index=True, default='nba')  # Deprecated

    # Multi-source ID columns (dedicated per API)
    odds_api_id = Column(String(100), nullable=True, index=True)
    nba_api_id = Column(Integer, nullable=True, index=True)
    espn_id = Column(Integer, nullable=True, index=True)
    nfl_id = Column(Integer, nullable=True, index=True)      # NFL GSIS ID
    mlb_id = Column(Integer, nullable=True, index=True)      # MLB ID
    nhl_id = Column(Integer, nullable=True, index=True)      # NHL ID

    # Player information (all sports)
    canonical_name = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    team = Column(String(3), nullable=False, index=True)
    position = Column(String(10), nullable=True)
    active = Column(Boolean, nullable=False, index=True)
    last_roster_check = Column(DateTime, nullable=True, index=True)
    data_source = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # -------------------------------------------------------------------------
    # SPORT-SPECIFIC FIELDS (Nullable - only used by specific sports)
    # -------------------------------------------------------------------------

    # Basketball (NBA, WNBA, NCAA)
    height = Column(String(10), nullable=True)       # "6-4", "6-11"
    weight = Column(Integer, nullable=True)          # Pounds

    # Football (NFL, NCAA)
    college = Column(String(100), nullable=True)     # "Alabama", "Georgia"
    draft_year = Column(Integer, nullable=True)      # Year drafted
    draft_round = Column(Integer, nullable=True)     # Round drafted
    jersey_number = Column(Integer, nullable=True)   # Uniform number

    # Hockey (NHL)
    catches = Column(String(1), nullable=True)       # "L" or "R" (shooting hand)
    birth_date = Column(Date, nullable=True)         # Date of birth
    shoots = Column(String(1), nullable=True)        # "L" or "R"

    # Baseball (MLB)
    bats = Column(String(5), nullable=True)          # "L", "R", or "Switch"
    throws = Column(String(1), nullable=True)        # "L" or "R"

    # -------------------------------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------------------------------
    predictions = relationship("Prediction", back_populates="player", cascade="all, delete-orphan")
    stats = relationship("PlayerStats", back_populates="player", cascade="all, delete-orphan")
    injuries = relationship("PlayerInjury", backref="player", cascade="all, delete-orphan")
    lineup_entries = relationship("ExpectedLineup", backref="player", cascade="all, delete-orphan")
    season_stats = relationship("PlayerSeasonStats", back_populates="player", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_players_external_id', 'external_id'),
        Index('ix_players_id_source', 'id_source'),
        Index('ix_players_sport_id', 'sport_id'),
        Index('ix_players_canonical_name', 'canonical_name'),
        Index('ix_players_odds_api_id', 'odds_api_id'),
    )


# =============================================================================
# GAME MODEL (Multi-Sport)
# =============================================================================

class Game(Base):
    """
    Unified Game model for all sports.

    Sport-specific fields:
    - NFL: week, season_type (REG, POST, PRE)
    - NHL: shootout (boolean)
    - MLB: double_header, game_number

    Query by sport:
        nba_games = Game.query.filter(Game.sport_id == 'nba').all()
    """
    __tablename__ = "games"

    id = Column(String(36), primary_key=True)

    # Multi-sport support
    sport_id = Column(String(3), ForeignKey("sports.id"), nullable=False, index=True, default='nba')

    # Legacy fields
    external_id = Column(String(100), unique=True, nullable=False, index=True)
    id_source = Column(String(10), nullable=False, index=True, default='nba')

    # Multi-source ID columns
    odds_api_event_id = Column(String(100), nullable=True, index=True)
    espn_game_id = Column(Integer, nullable=True, index=True)
    nba_api_game_id = Column(String(20), nullable=True, index=True)

    # Game information (all sports)
    game_date = Column(DateTime, nullable=False, index=True)
    scheduled_start = Column(DateTime, nullable=True)  # Scheduled tipoff time
    away_team = Column(String(3), nullable=False)
    home_team = Column(String(3), nullable=False)
    season = Column(Integer, nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Final scores (all sports) - updated when game completes
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)

    # -------------------------------------------------------------------------
    # SPORT-SPECIFIC FIELDS
    # -------------------------------------------------------------------------

    # Football (NFL, NCAA)
    week = Column(Integer, nullable=True)             # Week number (1-18)
    season_type = Column(String(10), nullable=True)   # REG, POST, PRE

    # Hockey (NHL)
    shootout = Column(Boolean, nullable=True)         # Was game decided by shootout

    # Baseball (MLB)
    double_header = Column(Boolean, nullable=True)    # Part of doubleheader
    game_number = Column(Integer, nullable=True)      # 1 or 2 for doubleheaders
    inning = Column(String(10), nullable=True)        # Current/final inning

    # -------------------------------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------------------------------
    predictions = relationship("Prediction", back_populates="game", cascade="all, delete-orphan")
    odds = relationship("GameOdds", back_populates="game", cascade="all, delete-orphan")
    injuries = relationship("PlayerInjury", foreign_keys="PlayerInjury.game_id", cascade="all, delete-orphan")
    expected_lineups = relationship("ExpectedLineup", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_games_external_id', 'external_id'),
        Index('ix_games_id_source', 'id_source'),
        Index('ix_games_sport_id', 'sport_id'),
        Index('ix_games_odds_api_event_id', 'odds_api_event_id'),
        Index('ix_games_sport_date_status', 'sport_id', 'game_date', 'status'),
    )


class GameResult(Base):
    """
    Sport-specific game results with period-by-period scoring.

    Stores detailed scoring breakdowns for each sport:
    - NBA: q1_score, q2_score, q3_score, q4_score, ot_score (multiple OT possible)
    - NFL: Uses same quarter structure as NBA
    - NHL: p1_score, p2_score, p3_score, ot_score, shootout_score
    - MLB: inning_1_away, inning_1_home, ... inning_9, extra_innings (JSON)

    Query example:
        nba_results = GameResult.query.join(Game).filter(Game.sport_id == 'nba').all()
    """
    __tablename__ = "game_results"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # -------------------------------------------------------------------------
    # BASKETBALL SCORING (NBA, WNBA, NFL)
    # -------------------------------------------------------------------------
    q1_home = Column(Integer, nullable=True)
    q1_away = Column(Integer, nullable=True)
    q2_home = Column(Integer, nullable=True)
    q2_away = Column(Integer, nullable=True)
    q3_home = Column(Integer, nullable=True)
    q3_away = Column(Integer, nullable=True)
    q4_home = Column(Integer, nullable=True)
    q4_away = Column(Integer, nullable=True)

    # Overtime periods (NBA/NFL can have multiple OTs)
    ot_home = Column(Integer, nullable=True)   # First OT
    ot_away = Column(Integer, nullable=True)
    ot2_home = Column(Integer, nullable=True)  # Second OT (rare)
    ot2_away = Column(Integer, nullable=True)
    ot3_home = Column(Integer, nullable=True)  # Third OT (very rare)
    ot3_away = Column(Integer, nullable=True)

    # -------------------------------------------------------------------------
    # HOCKEY SCORING (NHL)
    # -------------------------------------------------------------------------
    p1_home = Column(Integer, nullable=True)   # Period 1
    p1_away = Column(Integer, nullable=True)
    p2_home = Column(Integer, nullable=True)   # Period 2
    p2_away = Column(Integer, nullable=True)
    p3_home = Column(Integer, nullable=True)   # Period 3
    p3_away = Column(Integer, nullable=True)
    ot_home = Column(Integer, nullable=True)   # OT (shared with basketball)
    ot_away = Column(Integer, nullable=True)
    shootout_home = Column(Integer, nullable=True)  # Shootout goals
    shootout_away = Column(Integer, nullable=True)

    # -------------------------------------------------------------------------
    # BASEBALL SCORING (MLB)
    # -------------------------------------------------------------------------
    # Store innings as JSON array: [{"inning": 1, "away": 0, "home": 1}, ...]
    # This handles variable length games (extra innings)
    innings = Column(JSON, nullable=True)

    # -------------------------------------------------------------------------
    # BETTING OUTCOMES
    # -------------------------------------------------------------------------
    winner = Column(String(10), nullable=True)  # 'home' or 'away'
    cover_spread = Column(String(10), nullable=True)  # 'home', 'away', 'push'
    total_over = Column(Boolean, nullable=True)  # True if over hit
    total_line = Column(Float, nullable=True)  # The closing total line
    spread_line = Column(Float, nullable=True)  # The closing spread

    # -------------------------------------------------------------------------
    # METADATA
    # -------------------------------------------------------------------------
    espn_id = Column(Integer, nullable=True, index=True)  # ESPN game ID for result data
    data_source = Column(String(50), nullable=True)  # 'espn', 'nba_api', 'nfl_api', etc.
    attendance = Column(Integer, nullable=True)  # Stadium attendance
    duration = Column(Integer, nullable=True)  # Game duration in minutes
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    game = relationship("Game", uselist=False)

    __table_args__ = (
        Index('ix_game_results_game_id', 'game_id', unique=True),
        Index('ix_game_results_espn_id', 'espn_id'),
    )


# =============================================================================
# PREDICTION MODEL (Multi-Sport)
# =============================================================================

class Prediction(Base):
    """
    Unified Prediction model for all sports.

    Supports different stat types per sport:
    - NBA: points, rebounds, assists, threes, minutes
    - NFL: passing_yards, rushing_yards, receptions, touchdowns
    - NHL: goals, assists, points, shots
    - MLB: hits, home_runs, rbi, strikeouts
    """
    __tablename__ = "predictions"

    id = Column(String(36), primary_key=True)

    # Multi-sport support
    sport_id = Column(String(3), ForeignKey("sports.id"), nullable=False, index=True, default='nba')

    # Foreign keys
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)

    # Prediction details
    stat_type = Column(String(50), nullable=False)  # Varies by sport
    predicted_value = Column(Float, nullable=False)
    bookmaker_line = Column(Float, nullable=True)
    bookmaker_name = Column(String(100), nullable=True)
    recommendation = Column(String(10), nullable=False)  # OVER, UNDER
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    model_version = Column(String(50), nullable=True)

    # Odds pricing
    over_price = Column(Float, nullable=True)
    under_price = Column(Float, nullable=True)
    odds_fetched_at = Column(DateTime, nullable=True)
    odds_last_updated = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, index=True)

    # Accuracy tracking
    actual_value = Column(Float, nullable=True)
    difference = Column(Float, nullable=True)
    was_correct = Column(Boolean, nullable=True)
    actuals_resolved_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    player = relationship("Player", back_populates="predictions")
    game = relationship("Game", back_populates="predictions")

    __table_args__ = (
        Index('ix_predictions_sport_id', 'sport_id'),
        Index('ix_predictions_odds_last_updated', 'odds_last_updated'),
        Index('ix_predictions_actuals_resolved', 'actuals_resolved_at'),
        Index('ix_predictions_accuracy_lookup', 'game_id', 'stat_type', 'actuals_resolved_at'),
        Index('ix_predictions_confidence', 'confidence'),
    )


# =============================================================================
# SUPPORTING MODELS (Shared across all sports)
# =============================================================================

class PlayerStats(Base):
    """Player statistics for games (multi-sport)."""
    __tablename__ = "player_stats"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)

    # Common stats (sport-specific usage)
    points = Column(Integer, nullable=True)        # NBA/NFL/NHL/MLB
    rebounds = Column(Integer, nullable=True)      # NBA
    assists = Column(Integer, nullable=True)       # NBA/NHL
    threes = Column(Integer, nullable=True)        # NBA
    minutes = Column(Integer, nullable=True)       # NBA/NHL

    # Football-specific
    passing_yards = Column(Integer, nullable=True)
    rushing_yards = Column(Integer, nullable=True)
    receptions = Column(Integer, nullable=True)
    touchdowns = Column(Integer, nullable=True)
    interceptions = Column(Integer, nullable=True)

    # Hockey-specific
    goals = Column(Integer, nullable=True)
    shots = Column(Integer, nullable=True)
    plus_minus = Column(Integer, nullable=True)
    saves = Column(Integer, nullable=True)

    # Baseball-specific
    hits = Column(Integer, nullable=True)
    home_runs = Column(Integer, nullable=True)
    rbi = Column(Integer, nullable=True)
    strikeouts = Column(Integer, nullable=True)
    at_bats = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False)

    # Relationships
    player = relationship("Player", back_populates="stats")
    game = relationship("Game")


class GameOdds(Base):
    """Game-level betting odds from bookmakers."""
    __tablename__ = "game_odds"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    bookmaker_key = Column(String(50), nullable=False, index=True)
    bookmaker_title = Column(String(100), nullable=False)

    # Moneyline odds
    home_moneyline = Column(Float, nullable=True)
    away_moneyline = Column(Float, nullable=True)

    # Spread odds
    home_spread_point = Column(Float, nullable=True)
    home_spread_price = Column(Float, nullable=True)
    away_spread_point = Column(Float, nullable=True)
    away_spread_price = Column(Float, nullable=True)

    # Totals
    totals_point = Column(Float, nullable=True)
    over_price = Column(Float, nullable=True)
    under_price = Column(Float, nullable=True)

    last_update = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)

    # Relationships
    game = relationship("Game", back_populates="odds")

    __table_args__ = (
        Index('ix_game_odds_bookmaker', 'bookmaker_key'),
        Index('ix_game_odds_last_update', 'last_update'),
    )


class PlayerInjury(Base):
    """Track player injury status (multi-sport)."""
    __tablename__ = "player_injuries"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True)

    injury_type = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, index=True)
    impact_description = Column(Text, nullable=True)

    # Return tracking
    days_since_return = Column(Integer, nullable=True)
    minutes_restriction = Column(Integer, nullable=True)
    games_played_since_return = Column(Integer, nullable=True)

    reported_date = Column(Date, nullable=False, index=True)
    return_date = Column(Date, nullable=True, index=True)
    external_source = Column(String(100), nullable=True)

    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('ix_player_injuries_player_status', 'player_id', 'status'),
        Index('ix_player_injuries_game_id', 'game_id'),
        Index('ix_player_injuries_return_date', 'return_date'),
    )


class ExpectedLineup(Base):
    """Projected starting lineups."""
    __tablename__ = "expected_lineups"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=True, index=True)
    team = Column(String(3), nullable=False)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)

    starter_position = Column(String(10), nullable=True)
    is_confirmed = Column(Boolean, default=False, nullable=False)
    minutes_projection = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_expected_lineups_game_team', 'game_id', 'team'),
    )


class PlayerSeasonStats(Base):
    """Cached player season-averaged stats."""
    __tablename__ = "player_season_stats"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    season = Column(String(10), nullable=False, index=True)

    games_count = Column(Integer, nullable=False)
    points_per_36 = Column(Float, nullable=False)
    rebounds_per_36 = Column(Float, nullable=False)
    assists_per_36 = Column(Float, nullable=False)
    threes_per_36 = Column(Float, nullable=False)
    avg_minutes = Column(Float, nullable=False)

    last_game_date = Column(Date, nullable=True)
    fetched_at = Column(DateTime, nullable=False, index=True)
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
    """Historical bookmaker odds for hit rate calculation."""
    __tablename__ = "historical_odds_snapshots"

    id = Column(String(36), primary_key=True)
    game_id = Column(String(36), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = Column(String(36), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)

    stat_type = Column(String(50), nullable=False, index=True)
    bookmaker_name = Column(String(100), nullable=False, index=True)
    bookmaker_line = Column(Float, nullable=False)
    over_price = Column(Float, nullable=True)
    under_price = Column(Float, nullable=True)

    snapshot_time = Column(DateTime, nullable=False, index=True)
    is_opening_line = Column(Boolean, default=False, nullable=False, index=True)
    line_movement = Column(Float, default=0.0, nullable=False)
    was_starter = Column(Boolean, default=False, nullable=False, index=True)

    actual_value = Column(Float, nullable=True)
    hit_result = Column(String(10), nullable=True, index=True)
    resolved_at = Column(DateTime, nullable=True, index=True)

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


# =============================================================================
# BETTING MODELS (Shared across all sports)
# =============================================================================

class Parlay(Base):
    """Generated parlay bets."""
    __tablename__ = "parlays"

    id = Column(String(36), primary_key=True)
    parlay_type = Column(String(20), nullable=False, index=True)

    calculated_odds = Column(Float, nullable=False)
    implied_probability = Column(Float, nullable=False)
    expected_value = Column(Float, nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)

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
    """Individual leg within a parlay."""
    __tablename__ = "parlay_legs"

    id = Column(String(36), primary_key=True)
    parlay_id = Column(String(36), ForeignKey("parlays.id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_id = Column(String(36), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, index=True)

    leg_order = Column(Integer, nullable=False)
    selection = Column(String(10), nullable=False)
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
    """Actual bets placed on sportsbook platforms."""
    __tablename__ = "placed_bets"

    id = Column(String(36), primary_key=True)
    sportsbook = Column(String(50), nullable=False, index=True)
    bet_id = Column(String(100), nullable=False, index=True)
    bet_type = Column(String(20), nullable=False, index=True)

    game_id = Column(String(36), ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True)
    matchup = Column(String(100), nullable=False)
    game_date = Column(DateTime, nullable=False, index=True)

    wager_amount = Column(Float, nullable=False)
    total_charged = Column(Float, nullable=False)
    odds = Column(Integer, nullable=False)
    to_win = Column(Float, nullable=False)
    total_payout = Column(Float, nullable=False)

    status = Column(String(20), nullable=False, index=True, default='pending')
    cash_out_value = Column(Float, nullable=True)
    actual_payout = Column(Float, nullable=True)
    profit_loss = Column(Float, nullable=True)

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

    player_name = Column(String(255), nullable=False)
    player_team = Column(String(10), nullable=False)

    stat_type = Column(String(50), nullable=False)
    selection = Column(String(10), nullable=False)
    line = Column(Float, nullable=True)
    special_bet = Column(String(100), nullable=True)

    predicted_value = Column(Float, nullable=True)
    model_confidence = Column(Float, nullable=True)
    recommendation = Column(String(10), nullable=True)

    result = Column(String(20), nullable=True)
    actual_value = Column(Float, nullable=True)
    was_correct = Column(Boolean, nullable=True)

    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_placed_bet_legs_bet_id', 'bet_id'),
    )


# =============================================================================
# SYNC LAYER MODELS (Shared across all sports)
# =============================================================================

class NewsEvent(Base):
    """News and injury updates."""
    __tablename__ = "news_events"

    id = Column(String(36), primary_key=True)
    external_id = Column(String(100), unique=True, nullable=True)
    headline = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(String(50), nullable=False, index=True)
    source = Column(String(100), nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_news_published', 'published_at'),
        Index('ix_news_type', 'event_type'),
    )


class GameMapping(Base):
    """Maps API games between different sources."""
    __tablename__ = "game_mappings"

    id = Column(String(36), primary_key=True)
    nba_game_id = Column(String(20), unique=True, nullable=False, index=True)
    nba_home_team_id = Column(Integer, nullable=False)
    nba_away_team_id = Column(Integer, nullable=False)
    odds_event_id = Column(String(64), unique=True, nullable=True, index=True)
    odds_sport_key = Column(String(32), nullable=False, default='basketball_nba')
    game_date = Column(Date, nullable=False, index=True)
    game_time = Column(DateTime, nullable=True)
    match_confidence = Column(Float, nullable=False)
    match_method = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default='pending', index=True)
    last_validated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_game_mappings_date', 'game_date'),
        Index('ix_game_mappings_status', 'status'),
        Index('ix_game_mappings_confidence', 'match_confidence'),
    )


class PlayerAlias(Base):
    """Canonical player name mappings."""
    __tablename__ = "player_aliases"

    id = Column(String(36), primary_key=True)
    nba_player_id = Column(Integer, nullable=False, index=True)
    canonical_name = Column(String(128), nullable=False, index=True)
    alias_name = Column(String(128), nullable=False, index=True)
    alias_source = Column(String(32), nullable=False, index=True)
    match_confidence = Column(Float, nullable=False)
    is_verified = Column(Boolean, nullable=False, default=False, index=True)
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
    """Team name and ID mappings."""
    __tablename__ = "team_mappings"

    id = Column(String(36), primary_key=True)
    nba_team_id = Column(Integer, unique=True, nullable=False)
    nba_abbreviation = Column(String(3), nullable=False, index=True)
    nba_full_name = Column(String(64), nullable=False)
    nba_city = Column(String(32), nullable=False)
    odds_api_name = Column(String(64), nullable=True)
    odds_api_key = Column(String(32), nullable=True, index=True)
    alternate_names = Column(Text, nullable=False, default='[]')
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('ix_team_mappings_abbreviation', 'nba_abbreviation'),
        Index('ix_team_mappings_odds_key', 'odds_api_key'),
    )


class SyncMetadata(Base):
    """Sync job tracking."""
    __tablename__ = "sync_metadata"

    id = Column(String(36), primary_key=True)
    source = Column(String(32), nullable=False)
    data_type = Column(String(32), nullable=False)
    last_sync_started_at = Column(DateTime, nullable=True)
    last_sync_completed_at = Column(DateTime, nullable=True, index=True)
    last_sync_status = Column(String(16), nullable=True, index=True)
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
    """Audit trail for matches and mapping changes."""
    __tablename__ = "match_audit_log"

    id = Column(String(36), primary_key=True)
    entity_type = Column(String(16), nullable=False)
    entity_id = Column(String(64), nullable=False)
    action = Column(String(16), nullable=False, index=True)
    previous_state = Column(Text, nullable=True)
    new_state = Column(Text, nullable=True)
    match_details = Column(Text, nullable=True)
    performed_by = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('ix_audit_entity', 'entity_type', 'entity_id'),
        Index('ix_audit_created', 'created_at'),
        Index('ix_audit_action', 'action'),
        Index('ix_audit_performed_by', 'performed_by'),
    )
