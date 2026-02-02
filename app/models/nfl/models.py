"""
NFL database models.

This module contains NFL-specific database models including games, players,
predictions, and statistics.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Date
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()

# Sport identifier
SPORT_ID = "nfl"


class Team(Base):
    """NFL team information."""
    __tablename__ = "nfl_teams"

    id = Column(UUID(as_uuid=True), primary_key=True)
    espn_id = Column(Integer, unique=True, nullable=True)
    abbreviation = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    city = Column(String(50))
    mascot = Column(String(50))
    conference = Column(String(10))  # AFC or NFC
    division = Column(String(20))
    stadium = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Team {self.abbreviation} - {self.name}>"


class Player(Base):
    """NFL player information."""
    __tablename__ = "nfl_players"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    espn_id = Column(Integer, unique=True, nullable=True)
    gsis_id = Column(Integer)  # NFL GSIS identifier
    name = Column(String(100), nullable=False)
    full_name = Column(String(150))
    position = Column(String(10))  # QB, RB, WR, TE, K, DST, etc.
    jersey_number = Column(Integer)
    height = Column(String(10))  # 6-4, 6-5, etc.
    weight = Column(Integer)  # in pounds
    college = Column(String(100))
    draft_year = Column(Integer)
    team_id = Column(UUID(as_uuid=True), ForeignKey("nfl_teams.id"))
    team = Column(String(10))  # Denormalized for queries
    status = Column(String(20), default="active")  # active, ir, retired, etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    team_obj = relationship("Team", back_populates="players")
    predictions = relationship("Prediction", back_populates="player")
    stats = relationship("PlayerSeasonStats", back_populates="player")

    def __repr__(self):
        return f"<Player {self.name} ({self.position}) - {self.team}>"


class Game(Base):
    """NFL game information."""
    __tablename__ = "nfl_games"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    espn_id = Column(Integer)
    gsis_id = Column(Integer)  # NFL GSIS identifier
    season = Column(Integer, nullable=False)
    season_type = Column(String(10))  # REG, POST, PRE
    week = Column(Integer, nullable=False)  # Week number
    game_date = Column(DateTime(timezone=True), nullable=False, index=True)
    home_team = Column(String(10), nullable=False)  # Team abbreviation
    away_team = Column(String(10), nullable=False)  # Team abbreviation
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    status = Column(String(20), default="scheduled")  # scheduled, in_progress, final
    venue = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    home_team_obj = relationship("Team", foreign_keys=[home_team])
    away_team_obj = relationship("Team", foreign_keys=[away_team])
    predictions = relationship("Prediction", back_populates="game")
    odds_snapshots = relationship("GameOddsSnapshot", back_populates="game")

    def __repr__(self):
        return f"<Game Week {self.week} ({self.away_team} @ {self.home_team}) - {self.status}>"


class Prediction(Base):
    """NFL player prop prediction."""
    __tablename__ = "nfl_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    player_id = Column(UUID(as_uuid=True), ForeignKey("nfl_players.id"), nullable=False)
    game_id = Column(UUID(as_uuid=True), ForeignKey("nfl_games.id"), nullable=False)

    # Prediction details
    stat_type = Column(String(50), nullable=False)  # passing_yards, rushing_yards, receptions, etc.
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
    """NFL player season statistics."""
    __tablename__ = "nfl_player_season_stats"

    id = Column(UUID(as_uuid=True), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("nfl_players.id"))
    season = Column(Integer, nullable=False)
    season_type = Column(String(10))  # REG, POST
    team = Column(String(10))

    # Passing stats
    passing_yards = Column(Integer)
    passing_touchdowns = Column(Integer)
    passing_interceptions = Column(Integer)
    passing_completions = Column(Integer)
    passing_attempts = Column(Integer)
    passer_rating = Column(Float)

    # Rushing stats
    rushing_yards = Column(Integer)
    rushing_touchdowns = Column(Integer)
    rushing_attempts = Column(Integer)

    # Receiving stats
    receptions = Column(Integer)
    receiving_yards = Column(Integer)
    receiving_touchdowns = Column(Integer)
    targets = Column(Integer)

    # Defense/special teams stats
    tackles = Column(Integer)
    sacks = Column(Float)
    interceptions = Column(Integer)
    field_goals_made = Column(Integer)
    field_goals_attempted = Column(Integer)
    extra_points_made = Column(Integer)
    extra_points_attempted = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    player = relationship("Player", back_populates="stats")

    def __repr__(self):
        return f"<PlayerSeasonStats {self.player_id} Season {self.season}>"


class GameOddsSnapshot(Base):
    """Snapshot of NFL game odds at a specific time."""
    __tablename__ = "nfl_game_odds_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("nfl_games.id"), nullable=False)
    bookmaker = Column(String(50), nullable=False)  # draftkings, fanduel, etc.
    snapshot_time = Column(DateTime(timezone=True), nullable=False)

    # Money line odds
    home_moneyline = Column(Integer)
    away_moneyline = Column(Integer)
    spread = Column(Float)  # Points with home team
    spread_odds_home = Column(Integer)  # Odds for spread bet on home
    spread_odds_away = Column(Integer)  # Odds for spread bet on away
    total = Column(Float)  # Over/under total points
    total_over_odds = Column(Integer)
    total_under_odds = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    game = relationship("Game", back_populates="odds_snapshots")

    def __repr__(self):
        return f"<GameOddsSnapshot {self.game_id} {self.bookmaker} {self.snapshot_time}>"


# Update Team relationships
Team.players = relationship("Player", order_by="Player.name")
