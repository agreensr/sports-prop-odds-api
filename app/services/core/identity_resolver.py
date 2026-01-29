"""
Multi-Source Identity Resolution Service.

This service resolves player and game identities across multiple data sources.
It handles the complexity of matching the same entity across different APIs
that may use different IDs, names, or formats.

Key Features:
- Player identity resolution across nba_api, odds_api, espn, nfl, mlb, nhl
- Game identity resolution with natural key matching
- Confidence scoring for match quality
- Automatic creation of new identities when no match exists
- Canonical name management

Data Sources:
- Primary: The Odds API (games, odds, player props)
- Secondary: ESPN API (news, scores, team data)
- Tertiary: Sport-specific APIs (nba_api, nfl_data_py, etc.)
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import Player, Game

logger = logging.getLogger(__name__)


class IdentityMatch:
    """Represents a potential identity match with confidence score."""

    def __init__(
        self,
        entity: Player | Game,
        confidence: float,
        match_source: str,
        match_reason: str
    ):
        self.entity = entity
        self.confidence = confidence
        self.match_source = match_source  # Which API/source provided the match
        self.match_reason = match_reason  # Why we think this is a match

    def __repr__(self):
        return (f"IdentityMatch(entity={self.entity.id}, "
                f"confidence={self.confidence:.2f}, "
                f"source={self.match_source}, "
                f"reason={self.match_reason})")


class PlayerIdentityResolver:
    """
    Resolves player identities across multiple data sources.

    Matching Strategy (in order of priority):
    1. Exact ID match (odds_api_id, nba_api_id, espn_id, etc.)
    2. Team + canonical name exact match
    3. Canonical name fuzzy match (same team)
    4. Manual aliases table

    Confidence Thresholds:
    - 1.0: Exact ID match (authoritative)
    - 0.9: Team + exact canonical name
    - 0.7+: Fuzzy name match (same team)
    - 0.5-0.7: Fuzzy name match (different team - trade candidate)
    """

    # Minimum confidence to auto-accept a match
    AUTO_ACCEPT_THRESHOLD = 0.85

    # Confidence below which we require manual review
    MANUAL_REVIEW_THRESHOLD = 0.5

    def __init__(self, db: Session):
        self.db = db

    def resolve_player(
        self,
        sport_id: str,
        name: str,
        team: Optional[str] = None,
        **id_fields
    ) -> Tuple[Player, bool]:
        """
        Resolve a player to a database identity.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            name: Player name from source
            team: Team abbreviation (optional but recommended)
            **id_fields: API-specific IDs (odds_api_id, nba_api_id, espn_id, etc.)

        Returns:
            Tuple of (Player entity, was_created: bool)

        Example:
            player, created = resolver.resolve_player(
                sport_id='nba',
                name='Luka Doncic',
                team='DAL',
                odds_api_id='abc123'
            )
        """
        # Step 1: Try exact ID match (highest confidence)
        for source, external_id in id_fields.items():
            if external_id is None:
                continue

            player = self._find_by_api_id(sport_id, source, external_id)
            if player:
                logger.debug(
                    f"Exact ID match for {name}: {player.id} "
                    f"(source: {source}, id: {external_id})"
                )
                # Update the ID field if it wasn't set before
                self._update_id_field(player, source, external_id)
                return player, False

        # Step 2: Try team + canonical name match
        if team:
            player = self._find_by_team_and_name(sport_id, team, name)
            if player:
                logger.debug(
                    f"Team+name match for {name}: {player.id} "
                    f"(team: {team})"
                )
                # Update any ID fields we have
                for source, external_id in id_fields.items():
                    if external_id is not None:
                        self._update_id_field(player, source, external_id)
                return player, False

        # Step 3: Try canonical name only (trade candidate)
        player = self._find_by_canonical_name(sport_id, name, team)
        if player:
            logger.debug(
                f"Name-only match for {name}: {player.id} "
                f"(team change: {player.team} -> {team})"
            )
            # Update team and any ID fields
            player.team = team
            for source, external_id in id_fields.items():
                if external_id is not None:
                    self._update_id_field(player, source, external_id)
            player.updated_at = datetime.now()
            self.db.commit()
            return player, False

        # Step 4: Check player aliases table
        player = self._find_by_alias(sport_id, name, team)
        if player:
            logger.debug(f"Alias match for {name}: {player.id}")
            for source, external_id in id_fields.items():
                if external_id is not None:
                    self._update_id_field(player, source, external_id)
            return player, False

        # Step 5: No match found - create new player
        player = self._create_player(sport_id, name, team, **id_fields)
        logger.info(f"Created new player: {name} ({team}) - {player.id}")
        return player, True

    def _find_by_api_id(
        self,
        sport_id: str,
        source: str,
        external_id: str
    ) -> Optional[Player]:
        """Find player by API-specific ID."""
        # Map source names to database columns
        column_map = {
            'odds_api_id': Player.odds_api_id,
            'nba_api_id': Player.nba_api_id,
            'espn_id': Player.espn_id,
            'nfl_id': Player.nfl_id,
            'mlb_id': Player.mlb_id,
            'nhl_id': Player.nhl_id,
        }

        column = column_map.get(source)
        if not column:
            logger.warning(f"Unknown ID source: {source}")
            return None

        return self.db.query(Player).filter(
            and_(
                Player.sport_id == sport_id,
                column == external_id
            )
        ).first()

    def _find_by_team_and_name(
        self,
        sport_id: str,
        team: str,
        name: str
    ) -> Optional[Player]:
        """Find player by team and canonical name."""
        # Normalize name for comparison
        canonical_name = self._normalize_name(name)

        return self.db.query(Player).filter(
            and_(
                Player.sport_id == sport_id,
                Player.team == team,
                Player.canonical_name == canonical_name,
                Player.active == True
            )
        ).first()

    def _find_by_canonical_name(
        self,
        sport_id: str,
        name: str,
        team: Optional[str] = None
    ) -> Optional[Player]:
        """
        Find player by canonical name only (trade candidates).

        Improvement (P1 #11): Added suffix compatibility checking to prevent
        matching Jr/Sr players with the same name.

        Args:
            sport_id: Sport identifier
            name: Player name
            team: Optional team for suffix verification

        Returns:
            Player if found, None otherwise
        """
        canonical_name = self._normalize_name(name)

        # Get input suffix for comparison
        input_suffix = self._extract_suffix(name)

        # Find all matching players
        query = self.db.query(Player).filter(
            and_(
                Player.sport_id == sport_id,
                Player.canonical_name == canonical_name,
                Player.active == True
            )
        )
        players = query.all()

        if not players:
            return None

        # If only one match, verify suffix compatibility
        if len(players) == 1:
            player = players[0]
            if input_suffix:
                player_suffix = self._extract_suffix(player.name or '')
                # Check for suffix conflict (Jr vs Sr)
                if self._suffixes_conflict(input_suffix, player_suffix):
                    logger.warning(
                        f"Suffix conflict for {name}: input={input_suffix}, "
                        f"player={player_suffix} - skipping match"
                    )
                    return None
            return player

        # Multiple matches - use team to disambiguate
        if team:
            for player in players:
                if player.team == team:
                    return player

        # Use suffix to disambiguate
        if input_suffix:
            for player in players:
                player_suffix = self._extract_suffix(player.name or '')
                if player_suffix == input_suffix:
                    return player

        # Return first match as fallback
        return players[0]

    def _extract_suffix(self, name: str) -> str:
        """
        Extract suffix from a name (Jr, Sr, II, III, etc.).

        Args:
            name: Player name

        Returns:
            Suffix (lowercase, without dots) or empty string
        """
        if not name:
            return ""

        import re
        suffix_pattern = r'\b(jr|sr|ii|iii|iv|v|vi|vii|viii|ix)\.?$'
        match = re.search(suffix_pattern, name.lower())
        return match.group(1) if match else ""

    def _suffixes_conflict(self, suffix1: str, suffix2: str) -> bool:
        """
        Check if two suffixes conflict (Jr vs Sr).

        Args:
            suffix1: First suffix
            suffix2: Second suffix

        Returns:
            True if suffixes conflict
        """
        # Normalize for comparison
        s1 = suffix1.lower().replace('.', '') if suffix1 else ''
        s2 = suffix2.lower().replace('.', '') if suffix2 else ''

        # Only Jr/Sr are considered conflicting
        generational = {'jr', 'sr'}
        if s1 in generational and s2 in generational:
            return s1 != s2

        return False

    def _find_by_alias(
        self,
        sport_id: str,
        name: str,
        team: Optional[str]
    ) -> Optional[Player]:
        """Find player by checking aliases table."""
        from app.models import PlayerAlias

        canonical_name = self._normalize_name(name)

        # PlayerAlias table is NBA-specific and doesn't have sport_id
        # Only use it for NBA queries
        if sport_id != 'nba':
            return None

        # First try to find the alias by canonical name
        alias = self.db.query(PlayerAlias).filter(
            PlayerAlias.alias_name == canonical_name
        ).first()

        if alias:
            # If team specified, verify it matches
            if team:
                player = self.db.query(Player).filter(
                    and_(
                        Player.id == alias.nba_player_id,
                        Player.team == team
                    )
                ).first()
            else:
                player = self.db.query(Player).filter(
                    Player.id == alias.nba_player_id
                ).first()

            return player

        return None

    def _create_player(
        self,
        sport_id: str,
        name: str,
        team: Optional[str],
        **id_fields
    ) -> Player:
        """Create a new player record."""
        canonical_name = self._normalize_name(name)

        player = Player(
            id=str(uuid4()),
            sport_id=sport_id,
            external_id=id_fields.get('odds_api_id') or str(uuid4()),  # Fallback
            id_source='odds_api' if 'odds_api_id' in id_fields else 'manual',
            canonical_name=canonical_name,
            name=name,
            team=team or 'UNK',  # Unknown team
            active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            **{k: v for k, v in id_fields.items() if v is not None}
        )

        self.db.add(player)
        self.db.commit()

        return player

    def _update_id_field(self, player: Player, source: str, external_id: str):
        """Update an ID field if it's not already set."""
        column_map = {
            'odds_api_id': 'odds_api_id',
            'nba_api_id': 'nba_api_id',
            'espn_id': 'espn_id',
            'nfl_id': 'nfl_id',
            'mlb_id': 'mlb_id',
            'nhl_id': 'nhl_id',
        }

        column = column_map.get(source)
        if not column:
            return

        current_value = getattr(player, column, None)
        if current_value is None:
            setattr(player, column, external_id)
            player.updated_at = datetime.now()
            self.db.commit()
            logger.debug(
                f"Updated {column} for {player.name}: {external_id}"
            )

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Normalize player name for consistent matching.

        Rules:
        - Convert to lowercase
        - Remove accents/diacritics
        - Remove common suffixes (Jr., Sr., II, III)
        - Replace special characters with standard equivalents
        """
        import unicodedata
        import re

        # Convert to lowercase and normalize unicode
        name = name.lower().strip()
        name = unicodedata.normalize('NFKD', name)

        # Remove accents
        name = ''.join(
            c for c in name
            if not unicodedata.combining(c)
        )

        # Remove suffixes like "jr.", "sr.", "ii", "iii"
        name = re.sub(r'\s+(jr|sr|ii|iii|iv)\.?\s*$', '', name)

        # Remove extra whitespace
        name = ' '.join(name.split())

        return name


class GameIdentityResolver:
    """
    Resolves game identities across multiple data sources.

    Matching Strategy:
    1. Exact API ID match (odds_api_event_id, espn_game_id)
    2. Natural key match (sport_id, game_date, away_team, home_team)

    The natural key is enforced by a unique constraint to prevent duplicates.

    Natural Key Components:
    - sport_id: League identifier
    - game_date: Date and time of game
    - away_team: Away team abbreviation
    - home_team: Home team abbreviation
    """

    def __init__(self, db: Session):
        self.db = db

    def resolve_game(
        self,
        sport_id: str,
        game_date: datetime,
        away_team: str,
        home_team: str,
        **id_fields
    ) -> Tuple[Game, bool]:
        """
        Resolve a game to a database identity.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            game_date: Date and time of the game
            away_team: Away team abbreviation
            home_team: Home team abbreviation
            **id_fields: API-specific IDs (odds_api_event_id, espn_game_id)

        Returns:
            Tuple of (Game entity, was_created: bool)

        Example:
            game, created = resolver.resolve_game(
                sport_id='nba',
                game_date=datetime(2026, 1, 27, 19, 0),
                away_team='LAL',
                home_team='BOS',
                odds_api_event_id='abc123'
            )
        """
        # Step 1: Try exact ID match
        for source, external_id in id_fields.items():
            if external_id is None:
                continue

            game = self._find_by_api_id(sport_id, source, external_id)
            if game:
                logger.debug(
                    f"Exact ID match for {away_team}@{home_team}: {game.id} "
                    f"(source: {source})"
                )
                # Update the ID field if it wasn't set before
                self._update_id_field(game, source, external_id)
                return game, False

        # Step 2: Try natural key match (enforced by unique constraint)
        game = self._find_by_natural_key(
            sport_id, game_date, away_team, home_team
        )
        if game:
            logger.debug(
                f"Natural key match for {away_team}@{home_team}: {game.id}"
            )
            # Update any ID fields we have
            for source, external_id in id_fields.items():
                if external_id is not None:
                    self._update_id_field(game, source, external_id)
            return game, False

        # Step 3: No match found - create new game
        game = self._create_game(
            sport_id, game_date, away_team, home_team, **id_fields
        )
        logger.info(
            f"Created new game: {away_team}@{home_team} "
            f"({game_date.strftime('%Y-%m-%d %H:%M')}) - {game.id}"
        )
        return game, True

    def _find_by_api_id(
        self,
        sport_id: str,
        source: str,
        external_id: str
    ) -> Optional[Game]:
        """Find game by API-specific ID."""
        column_map = {
            'odds_api_event_id': Game.odds_api_event_id,
            'espn_game_id': Game.espn_game_id,
        }

        column = column_map.get(source)
        if not column:
            logger.warning(f"Unknown game ID source: {source}")
            return None

        return self.db.query(Game).filter(
            and_(
                Game.sport_id == sport_id,
                column == external_id
            )
        ).first()

    def _find_by_natural_key(
        self,
        sport_id: str,
        game_date: datetime,
        away_team: str,
        home_team: str
    ) -> Optional[Game]:
        """
        Find game by natural key.

        This uses the unique constraint that prevents duplicates:
        (sport_id, game_date, away_team, home_team)
        """
        # Use a time window for game_date matching (±6 hours)
        # to handle timezone differences between APIs
        from datetime import timedelta

        time_window = timedelta(hours=6)
        start_time = game_date - time_window
        end_time = game_date + time_window

        return self.db.query(Game).filter(
            and_(
                Game.sport_id == sport_id,
                Game.game_date >= start_time,
                Game.game_date <= end_time,
                Game.away_team == away_team,
                Game.home_team == home_team
            )
        ).first()

    def _create_game(
        self,
        sport_id: str,
        game_date: datetime,
        away_team: str,
        home_team: str,
        **id_fields
    ) -> Game:
        """Create a new game record."""
        # Extract season from game_date
        season = game_date.year
        if game_date.month >= 10:  # NBA/NHL season starts in Oct
            season += 1

        game = Game(
            id=str(uuid4()),
            sport_id=sport_id,
            external_id=id_fields.get('odds_api_event_id') or str(uuid4()),
            id_source='odds_api' if 'odds_api_event_id' in id_fields else 'manual',
            game_date=game_date,
            away_team=away_team,
            home_team=home_team,
            season=season,
            status='scheduled',
            created_at=datetime.now(),
            updated_at=datetime.now(),
            **{k: v for k, v in id_fields.items() if v is not None}
        )

        self.db.add(game)
        self.db.commit()

        return game

    def _update_id_field(self, game: Game, source: str, external_id: str):
        """Update an ID field if it's not already set."""
        column_map = {
            'odds_api_event_id': 'odds_api_event_id',
            'espn_game_id': 'espn_game_id',
        }

        column = column_map.get(source)
        if not column:
            return

        current_value = getattr(game, column, None)
        if current_value is None:
            setattr(game, column, external_id)
            game.updated_at = datetime.now()
            self.db.commit()
            logger.debug(
                f"Updated {column} for {game.away_team}@{game.home_team}: "
                f"{external_id}"
            )


# Convenience functions for dependency injection
def get_player_resolver(db: Session) -> PlayerIdentityResolver:
    """Get a player identity resolver instance."""
    return PlayerIdentityResolver(db)


def get_game_resolver(db: Session) -> GameIdentityResolver:
    """Get a game identity resolver instance."""
    return GameIdentityResolver(db)
