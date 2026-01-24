"""Player resolver for matching player identities across APIs.

Handles name variations between APIs:
- Suffixes: "Jr.", "Sr.", "III"
- Punctuation: "P.J. Tucker" vs "PJ Tucker"
- Accents: "Luka Dončić" vs "Luka Doncic"
- Typos: Variations and misspellings

Pipeline:
1. Exact lookup in player_aliases table
2. Normalized comparison (remove suffixes, lowercase, etc.)
3. Fuzzy match (Levenshtein, Jaro-Winkler)
4. Team context match (same team + similar name)
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.sync.utils.name_normalizer import (
    normalize, extract_player_name_parts, are_names_equal
)
from app.services.sync.utils.confidence_scorer import calculate_player_match_confidence
from app.models.nba.models import PlayerAlias, MatchAuditLog
import uuid
import json

logger = logging.getLogger(__name__)


class PlayerResolver:
    """
    Resolve player identities across different APIs.

    Uses a multi-step pipeline to find the canonical nba_player_id
    for any player name from any source (odds_api, espn, etc.).
    """

    def __init__(self, db: Session):
        """
        Initialize the player resolver.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def resolve_player(
        self,
        player_name: str,
        source: str = 'odds_api',
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve player name to canonical nba_player_id.

        Pipeline:
        1. Exact lookup in player_aliases
        2. Normalized comparison
        3. Fuzzy match (RapidFuzz WRatio)
        4. Team context match (if team provided in context)

        Args:
            player_name: Player name to resolve
            source: Source of the name (odds_api, espn, etc.)
            context: Optional context dict with:
                - team_id: nba_api team ID for context
                - team_abbr: Team abbreviation
                - position: Player position

        Returns:
            Resolution dict with keys:
                - nba_player_id: int (canonical ID)
                - canonical_name: str (official name)
                - match_confidence: float (0.0-1.0)
                - match_method: str ('exact', 'normalized', 'fuzzy', 'context')
            Or None if no match found
        """
        context = context or {}

        # Step 1: Exact lookup
        result = await self._exact_lookup(player_name, source)
        if result:
            logger.debug(f"Exact match found for {player_name}")
            return result

        # Step 2: Normalized comparison
        result = await self._normalized_lookup(player_name, source)
        if result:
            logger.debug(f"Normalized match found for {player_name}")
            return result

        # Step 3: Fuzzy match
        result = await self._fuzzy_lookup(player_name, source, context)
        if result:
            logger.debug(f"Fuzzy match found for {player_name}")
            return result

        # Step 4: Team context match
        if context.get('team_id') or context.get('team_abbr'):
            result = await self._context_lookup(player_name, source, context)
            if result:
                logger.debug(f"Context match found for {player_name}")
                return result

        logger.warning(f"No match found for player: {player_name} (source: {source})")
        return None

    async def _exact_lookup(
        self,
        player_name: str,
        source: str
    ) -> Optional[Dict[str, Any]]:
        """
        Step 1: Exact lookup in player_aliases table.

        Args:
            player_name: Player name to look up
            source: Source of the name

        Returns:
            Resolution dict or None
        """
        alias = self.db.query(PlayerAlias).filter(
            PlayerAlias.alias_name == player_name,
            PlayerAlias.alias_source == source
        ).first()

        if alias:
            return {
                'nba_player_id': alias.nba_player_id,
                'canonical_name': alias.canonical_name,
                'match_confidence': float(alias.match_confidence),
                'match_method': 'exact'
            }

        return None

    async def _normalized_lookup(
        self,
        player_name: str,
        source: str
    ) -> Optional[Dict[str, Any]]:
        """
        Step 2: Normalized comparison.

        Normalizes both input and stored aliases, then compares.
        Handles suffixes, punctuation, case differences.

        Args:
            player_name: Player name to look up
            source: Source of the name

        Returns:
            Resolution dict or None
        """
        normalized_input = normalize(player_name)

        # Get all aliases from this source
        aliases = self.db.query(PlayerAlias).filter(
            PlayerAlias.alias_source == source
        ).all()

        for alias in aliases:
            if normalize(alias.alias_name) == normalized_input:
                return {
                    'nba_player_id': alias.nba_player_id,
                    'canonical_name': alias.canonical_name,
                    'match_confidence': 0.95,
                    'match_method': 'normalized'
                }

        return None

    async def _fuzzy_lookup(
        self,
        player_name: str,
        source: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Step 3: Fuzzy match using RapidFuzz.

        Uses WRatio which handles case, length differences, and
        various string similarity metrics.

        Args:
            player_name: Player name to look up
            source: Source of the name
            context: Context dict for boosting confidence

        Returns:
            Resolution dict or None
        """
        from rapidfuzz import fuzz, process

        # Get all aliases
        aliases = self.db.query(PlayerAlias).filter(
            PlayerAlias.alias_source == source
            ).all()

        if not aliases:
            return None

        # Create list of (alias_name, alias_obj) tuples
        alias_choices = [(alias.alias_name, alias) for alias in aliases]

        # Find best match
        best_match = process.extractOne(
            player_name,
            alias_choices,
            scorer=fuzz.WRatio,
            score_cutoff=85  # Minimum 85% similarity
        )

        if best_match:
            alias_name, alias_obj = best_match[0]
            score = best_match[1]

            # Calculate confidence based on score
            confidence = score / 100.0

            # Boost if context supports it
            if context.get('team_match'):
                confidence = min(confidence + 0.05, 1.0)

            return {
                'nba_player_id': alias_obj.nba_player_id,
                'canonical_name': alias_obj.canonical_name,
                'match_confidence': confidence,
                'match_method': 'fuzzy'
            }

        return None

    async def _context_lookup(
        self,
        player_name: str,
        source: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Step 4: Team context match.

        If we know the team, filter candidates to that team first,
        then do fuzzy matching. This significantly improves accuracy.

        Args:
            player_name: Player name to look up
            source: Source of the name
            context: Context dict with team_id or team_abbr

        Returns:
            Resolution dict or None
        """
        from rapidfuzz import fuzz, process

        # Try to get team ID from context
        team_id = context.get('team_id')

        if not team_id and context.get('team_abbr'):
            # Look up team ID from abbreviation
            from app.models.nba.models import TeamMapping
            team_mapping = self.db.query(TeamMapping).filter(
                TeamMapping.nba_abbreviation == context['team_abbr']
            ).first()
            if team_mapping:
                team_id = team_mapping.nba_team_id

        if not team_id:
            return None

        # Get player aliases, filtered by team if possible
        from app.models.nba.models import Player
        players = self.db.query(Player).filter(
            Player.nba_api_id.isnot(None),
            Player.team == context.get('team_abbr', '')
        ).all()

        if not players:
            return None

        # Create choices from player names
        player_choices = [(p.name, p) for p in players]

        # Find best match
        best_match = process.extractOne(
            player_name,
            player_choices,
            scorer=fuzz.WRatio,
            score_cutoff=80  # Lower threshold for context match
        )

        if best_match:
            player_name_matched, player_obj = best_match[0]
            score = best_match[1]

            confidence = min(score / 100.0 + 0.10, 1.0)  # Boost for team match

            return {
                'nba_player_id': player_obj.nba_api_id,
                'canonical_name': player_obj.name,
                'match_confidence': confidence,
                'match_method': 'context'
            }

        return None

    async def create_or_update_alias(
        self,
        nba_player_id: int,
        canonical_name: str,
        alias_name: str,
        alias_source: str,
        match_confidence: float,
        is_verified: bool = False
    ) -> PlayerAlias:
        """
        Create or update a player alias.

        Args:
            nba_player_id: Canonical nba_api player ID
            canonical_name: Official player name from nba_api
            alias_name: Alternate name from other source
            alias_source: Source of the alias (odds_api, espn, etc.)
            match_confidence: Confidence score (0.0-1.0)
            is_verified: Whether manually verified

        Returns:
            Created or updated PlayerAlias instance
        """
        # Check for existing alias
        existing = self.db.query(PlayerAlias).filter(
            PlayerAlias.alias_name == alias_name,
            PlayerAlias.alias_source == alias_source
        ).first()

        previous_state = None
        if existing:
            previous_state = {
                'nba_player_id': existing.nba_player_id,
                'canonical_name': existing.canonical_name,
                'match_confidence': float(existing.match_confidence)
            }

        if existing:
            # Update existing
            existing.nba_player_id = nba_player_id
            existing.canonical_name = canonical_name
            existing.match_confidence = match_confidence
            existing.is_verified = is_verified
            if is_verified and not existing.verified_at:
                existing.verified_at = datetime.utcnow()
                existing.verified_by = 'system'

            alias = existing
        else:
            # Create new
            alias = PlayerAlias(
                id=str(uuid.uuid4()),
                nba_player_id=nba_player_id,
                canonical_name=canonical_name,
                alias_name=alias_name,
                alias_source=alias_source,
                match_confidence=match_confidence,
                is_verified=is_verified,
                verified_at=datetime.utcnow() if is_verified else None,
                verified_by='system' if is_verified else None,
                created_at=datetime.utcnow()
            )
            self.db.add(alias)

        self.db.commit()
        self.db.refresh(alias)

        # Log to audit trail
        new_state = {
            'nba_player_id': alias.nba_player_id,
            'canonical_name': alias.canonical_name,
            'match_confidence': float(alias.match_confidence),
            'is_verified': alias.is_verified
        }

        await self._log_audit(
            entity_type='player',
            entity_id=str(nba_player_id),
            action='created' if not existing else 'updated',
            previous_state=previous_state,
            new_state=new_state,
            match_details={
                'alias_name': alias_name,
                'alias_source': alias_source,
                'match_confidence': match_confidence
            }
        )

        logger.info(
            f"Player alias created/updated: {alias_name} → {canonical_name} "
            f"(confidence: {match_confidence:.2f})"
        )

        return alias

    async def _log_audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        previous_state: Optional[Dict[str, Any]],
        new_state: Dict[str, Any],
        match_details: Optional[Dict[str, Any]] = None
    ):
        """Log match to audit trail."""
        try:
            audit_log = MatchAuditLog(
                id=str(uuid.uuid4()),
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                previous_state=json.dumps(previous_state) if previous_state else None,
                new_state=json.dumps(new_state),
                match_details=json.dumps(match_details) if match_details else None,
                performed_by='system',
                created_at=datetime.utcnow()
            )
            self.db.add(audit_log)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log audit entry: {e}")

    def get_canonical_name(self, nba_player_id: int) -> Optional[str]:
        """
        Get canonical name for an nba_player_id.

        Args:
            nba_player_id: nba_api player ID

        Returns:
            Canonical name or None
        """
        alias = self.db.query(PlayerAlias).filter(
            PlayerAlias.nba_player_id == nba_player_id
        ).first()

        return alias.canonical_name if alias else None

    def get_all_aliases_for_player(self, nba_player_id: int) -> list[PlayerAlias]:
        """
        Get all aliases for a player.

        Args:
            nba_player_id: nba_api player ID

        Returns:
            List of PlayerAlias instances
        """
        return self.db.query(PlayerAlias).filter(
            PlayerAlias.nba_player_id == nba_player_id
        ).all()

    async def batch_resolve_players(
        self,
        player_names: list[str],
        source: str = 'odds_api',
        context: Optional[Dict[str, Any]] = None
    ) -> list[Optional[Dict[str, Any]]]:
        """
        Resolve multiple players in batch.

        Args:
            player_names: List of player names to resolve
            source: Source of the names (odds_api, espn, etc.)
            context: Optional context dict applied to all players

        Returns:
            List of resolution dicts (same length as input), with None for unresolved players
        """
        results = []
        for player_name in player_names:
            result = await self.resolve_player(player_name, source, context)
            results.append(result)
        return results
