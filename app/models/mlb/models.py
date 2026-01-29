"""
MLB database models.

This module contains MLB-specific database models including games, players,
predictions, and statistics.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Date
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()

# Sport identifier
SPORT_ID = "mlb"


class Team(Base):
    """MLB team information."""
    __tablename__ = "mlb_teams"

    id = Column(UUID(as_uuid=True), primary_key=True)
    espn_id = Column(Integer, unique=True, nullable=True)
    abbreviation = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    city = Column(String(50))
    mascot = Column(String(50))
    league = Column(String(10))  # AL or NL
    division = Column(String(20))  # East, Central, West
    stadium = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Team {self.abbreviation} - {self.name}>"


class Player(Base):
    """MLB player information."""
    __tablename__ = "mlb_players"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    espn_id = Column(Integer, unique=True, nullable=True)
    mlb_id = Column(Integer)  # MLB.com player ID

    name = Column(String(100), nullable=False)
    full_name = Column(String(150))
    position = Column(String(10))  # P, C, 1B, 2B, SS, 3B, OF, DH, etc.
    jersey_number = Column(Integer)
    bats = Column(String(10))  # L, R, Switch
    throws = Column(String(10))  # L, R
    height = Column(String(10))  # 6-1, 6-2, etc.
    weight = Column(Integer)  # in pounds
    birth_date = Column(Date)
    team_id = Column(UUID(as_uuid=True), ForeignKey("mlb_teams.id"))
    team = Column(String(10))  # Denormalized for queries
    status = Column(String(20), default="active")  # active, ir, injured, etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    team_obj = relationship("Team", back_populates="players")
    predictions = relationship("Prediction", back_populates="player")
    stats = relationship("PlayerSeasonStats", back_populates="player")

    def __repr__(self):
        return f"<Player {self.name} ({self.position}) - {self.team}>"


class Game(Base):
    """MLB game information."""
    __tablename__ = "mlb_games"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    espn_id = Column(Integer)
    mlb_id = Column(Integer)  # MLB.com game ID

    season = Column(Integer, nullable=False)
    season_type = Column(String(10))  # REG, POST, PRE, SPRING
    game_date = Column(DateTime(timezone=True), nullable=False, index=True)
    home_team = Column(String(10), nullable=False)  # Team abbreviation
    away_team = Column(String(10), nullable=False)  # Team abbreviation
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    status = Column(String(20), default="scheduled")  # scheduled, in_progress, final, postponed
    venue = Column(String(100))
    double_header = Column(Boolean, default=False)
    game_number = Column(Integer)  # 1 or 2 for doubleheaders

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    home_team_obj = relationship("Team", foreign_keys=[home_team])
    away_team_obj = relationship("Team", foreign_keys=[away_team])
    predictions = relationship("Prediction", back_populates="game")
    odds_snapshots = relationship("GameOddsSnapshot", back_populates="game")

    def __repr__(self):
        return f"<Game {self.away_team} @ {self.home_team} - {self.status}>"


class Prediction(Base):
    """MLB player prop prediction."""
    __tablename__ = "mlb_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    player_id = Column(UUID(as_uuid=True), ForeignKey("mlb_players.id"), nullable=False)
    game_id = Column(UUID(as_uuid=True), ForeignKey("mlb_games.id"), nullable=False)

    # Prediction details
    stat_type = Column(String(50), nullable=False)  # hits, runs, home_runs, strikeouts, etc.
    predicted_value = Column(Float, nullable=False)
    bookmaker_line = Column(Float, nullable=False)
    recommendation = Column(String(10), nullable=False)  # OVER or UNDER
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    model_version = Column(String(50), default="v1.0")

    # Odds information
    bookmaker_name = Column(String(100))
    over_price = Column(Float)  # American odds for OVER
    under_price = Column(Float)  # American odds for UNDER
    odds_last_updated = Column(DateTime(timezone=True))

    # Resolution
    actual_value = Column(Float)
    was_correct = Column(Boolean)
    resolved_at = Column(DateTime(timezone=True))

    # Metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    player = relationship("Player", back_populates="predictions")
    game = relationship("Game", back_populates="predictions")

    def __repr__(self):
        return (f"<Prediction {self.player_id} {self.stat_type} "
                f"{self.recommendation} {self.bookmaker_line} "
                f"({self.confidence:.2f})>")


class PlayerSeasonStats(Base):
    """MLB player season statistics."""
    __tablename__ = "mlb_player_season_stats"

    id = Column(UUID(as_uuid=True), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("mlb_players.id"))
    season = Column(Integer, nullable=False)
    season_type = Column(String(10))  # REG, POST, SPRING
    team = Column(String(10))

    # Batting stats
    games_played = Column(Integer)
    plate_appearances = Column(Integer)
    at_bats = Column(Integer)
    hits = Column(Integer)
    doubles = Column(Integer)
    triples = Column(Integer)
    home_runs = Column(Integer)
    runs_batted_in = Column(Integer)
    runs = Column(Integer)
    rbi = Column(Integer)
    stolen_bases = Column(Integer)
    caught_stealing = Column(Integer)
    strike_outs = Column(Integer)
    walks = Column(Integer)
    batting_average = Column(Float)
    on_base_percentage = Column(Float)
    slugging_percentage = Column(Float)

    # Pitching stats (for pitchers)
    innings_pitched = Column(Float)
    wins = Column(Integer)
    losses = Column(Integer)
    saves = Column(Integer)
    earned_run_average = Column(Float)
    strikeouts = Column(Integer)
    walks_allowed = Column(Integer)
    hits_allowed = Column(Integer)
    runs_allowed = Column(Integer)
    home_runs_allowed = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    player = relationship("Player", back_populates="stats")

    def __repr__(self):
        return f"<PlayerSeasonStats {self.player_id} Season {self.season}>"


class GameOddsSnapshot(Base):
    """Snapshot of MLB game odds at a specific time."""
    __tablename__ = "mlb_game_odds_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("mlb_games.id"), nullable=False)
    bookmaker = Column(String(50), nullable=False)  # draftkings, fanduel, etc.
    snapshot_time = Column(DateTime(timezone=True), nullable=False)

    # Money line odds
    home_moneyline = Column(Integer)
    away_moneyline = Column(Integer)
    spread = Column(Float)  # Run line
    spread_odds_home = Column(Integer)  # Odds for spread bet on home
    spread_odds_away = Column(Integer)  # Odds for spread bet on away
    total = Column(Float)  # Over/under total runs
    total_over_odds = Column(Integer)
    total_under_odds = Column(Integer)

    # Run line (alternative to spread)
    run_line = Column(Float)  # e.g., -1.5, +2.5
    run_line_odds_home = Column(Integer)  # Odds for run line bet on home
    run_line_odds_away = Column(Integer)  # Odds for run line bet on away

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    game = relationship("Game", back_populates="odds_snapshots")

    def __repr__(self):
        return f"<GameOddsSnapshot {self.game_id} {self.bookmaker} {self.snapshot_time}>"


# Update Team relationships
Team.players = relationship("Player", order_by="Player.name")
