"""
Database models for NBA Player Prop Prediction API.
Models are designed to match the existing database schema exactly.
"""
from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, DateTime, Date, ForeignKey, Boolean, Text, Index
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Player(Base):
    """NBA Player model with support for multiple external ID sources (ESPN, NBA)."""
    __tablename__ = "players"

    id = Column(String(36), primary_key=True)  # character varying(36)
    external_id = Column(String(100), unique=True, nullable=False, index=True)  # NBA or ESPN ID
    id_source = Column(String(10), nullable=False, index=True, default='nba')  # 'nba' or 'espn'
    name = Column(String(255), nullable=False, index=True)
    team = Column(String(3), nullable=False, index=True)  # Team abbreviation (3 chars)
    position = Column(String(10))
    active = Column(Boolean, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    predictions = relationship("Prediction", back_populates="player", cascade="all, delete-orphan")
    stats = relationship("PlayerStats", back_populates="player", cascade="all, delete-orphan")

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

    # Relationships
    player = relationship("Player", back_populates="predictions")
    game = relationship("Game", back_populates="predictions")

    __table_args__ = (
        Index('ix_predictions_odds_last_updated', 'odds_last_updated'),
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
    updated_at = Column(DateTime, nullable=False)

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
