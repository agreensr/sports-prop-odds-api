"""
NHL database models.

This module contains NHL-specific database models including games, players,
predictions, and statistics.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Date
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()

# Sport identifier
SPORT_ID = "nhl"


class Team(Base):
    """NHL team information."""
    __tablename__ = "nhl_teams"

    id = Column(UUID(as_uuid=True), primary_key=True)
    espn_id = Column(Integer, unique=True, nullable=True)
    abbreviation = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    city = Column(String(50))
    mascot = Column(String(50))
    conference = Column(String(10))  # Eastern or Western
    division = Column(String(20))  # Atlantic, Metropolitan, Central, Pacific
    arena = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Team {self.abbreviation} - {self.name}>"


class Player(Base):
    """NHL player information."""
    __tablename__ = "nhl_players"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    espn_id = Column(Integer, unique=True, nullable=True)
    nhl_id = Column(Integer)  # NHL.com player ID

    name = Column(String(100), nullable=False)
    full_name = Column(String(150))
    position = Column(String(10))  # C, LW, RW, D, G
    jersey_number = Column(Integer)
    catches = Column(String(10))  # L, R (which hand they shoot/catch with)
    height = Column(String(10))  # 6-1, 6-2, etc.
    weight = Column(Integer)  # in pounds
    birth_date = Column(Date)
    team_id = Column(UUID(as_uuid=True), ForeignKey("nhl_teams.id"))
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
    """NHL game information."""
    __tablename__ = "nhl_games"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    espn_id = Column(Integer)
    nhl_id = Column(Integer)  # NHL.com game ID

    season = Column(Integer, nullable=False)
    season_type = Column(String(10))  # REG, POST, PRE
    game_date = Column(DateTime(timezone=True), nullable=False, index=True)
    home_team = Column(String(10), nullable=False)  # Team abbreviation
    away_team = Column(String(10), nullable=False)  # Team abbreviation
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    status = Column(String(20), default="scheduled")  # scheduled, in_progress, final, postponed
    venue = Column(String(100))
    shootout = Column(Boolean, default=False)  # If game ended in shootout

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    home_team_obj = relationship("Team", foreign_keys=[home_team])
    away_team_obj = relationship("Team", foreign_keys=[away_team])
    predictions = relationship("Prediction", back_populates="game")
    odds_snapshots = relationship("GameOddsSnapshot", back_populates="game")

    def __repr__(self):
        return f"<Game {self.away_team} @ {self.home_team} - {self.status}>"


class Prediction(Base):
    """NHL player prop prediction."""
    __tablename__ = "nhl_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    sport_id = Column(String(3), ForeignKey("sports.id"), default=SPORT_ID)
    player_id = Column(UUID(as_uuid=True), ForeignKey("nhl_players.id"), nullable=False)
    game_id = Column(UUID(as_uuid=True), ForeignKey("nhl_games.id"), nullable=False)

    # Prediction details
    stat_type = Column(String(50), nullable=False)  # goals, assists, points, shots, saves, etc.
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
    """NHL player season statistics."""
    __tablename__ = "nhl_player_season_stats"

    id = Column(UUID(as_uuid=True), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("nhl_players.id"))
    season = Column(Integer, nullable=False)
    season_type = Column(String(10))  # REG, POST
    team = Column(String(10))

    # Offensive stats (skaters)
    games_played = Column(Integer)
    goals = Column(Integer)
    assists = Column(Integer)
    points = Column(Integer)  # goals + assists
    plus_minus = Column(Integer)  # +/-
    shots = Column(Integer)
    shooting_percentage = Column(Float)
    power_play_goals = Column(Integer)
    power_play_points = Column(Integer)
    short_handed_goals = Column(Integer)
    short_handed_points = Column(Integer)
    game_winning_goals = Column(Integer)
    overtime_goals = Column(Integer)

    # Faceoff and physical play stats
    faceoff_wins = Column(Integer)
    faceoff_losses = Column(Integer)
    faceoff_percentage = Column(Float)
    hits = Column(Integer)
    blocked_shots = Column(Integer)
    giveaways = Column(Integer)
    takeaways = Column(Integer)
    penalty_minutes = Column(Integer)

    # Goalie stats
    games_started = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    overtime_losses = Column(Integer)
    goals_against_average = Column(Float)
    saves = Column(Integer)
    shots_against = Column(Integer)
    save_percentage = Column(Float)
    shutouts = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    player = relationship("Player", back_populates="stats")

    def __repr__(self):
        return f"<PlayerSeasonStats {self.player_id} Season {self.season}>"


class GameOddsSnapshot(Base):
    """Snapshot of NHL game odds at a specific time."""
    __tablename__ = "nhl_game_odds_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("nhl_games.id"), nullable=False)
    bookmaker = Column(String(50), nullable=False)  # draftkings, fanduel, etc.
    snapshot_time = Column(DateTime(timezone=True), nullable=False)

    # Money line odds
    home_moneyline = Column(Integer)
    away_moneyline = Column(Integer)
    spread = Column(Float)  # Puck line (usually +/- 1.5)
    spread_odds_home = Column(Integer)  # Odds for spread bet on home
    spread_odds_away = Column(Integer)  # Odds for spread bet on away
    total = Column(Float)  # Over/under total goals
    total_over_odds = Column(Integer)
    total_under_odds = Column(Integer)

    # Puck line (alternative to spread)
    puck_line = Column(Float)  # e.g., -1.5, +2.5
    puck_line_odds_home = Column(Integer)  # Odds for puck line bet on home
    puck_line_odds_away = Column(Integer)  # Odds for puck line bet on away

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    game = relationship("Game", back_populates="odds_snapshots")

    def __repr__(self):
        return f"<GameOddsSnapshot {self.game_id} {self.bookmaker} {self.snapshot_time}>"


# Update Team relationships
Team.players = relationship("Player", order_by="Player.name")
