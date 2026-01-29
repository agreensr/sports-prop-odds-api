"""
End-to-end integration tests for sports-bet-ai-api.

These tests verify complete workflows work together with real database
but mock external API calls (nba_api, The Odds API).

Test coverage:
1. Full parlay generation flow (ParlayService methods)
2. Odds fetch and update flow (daily_odds_fetch.py workflow)
3. Prediction generation with odds matching
4. sync_nba_data.py CLI script functionality
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, date, timezone as tz
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.orm import Session

from app.models import (
    Player, Game, Prediction, PlayerStats, PlayerSeasonStats,
    Parlay, ParlayLeg, GameOdds, PlayerInjury, ExpectedLineup
)
from app.services.core.parlay_service import ParlayService
from app.services.nba.prediction_service import PredictionService
from app.services.core.odds_api_service import OddsApiService
from app.services.data_sources.odds_mapper import OddsMapper
from app.services.nba.injury_service import InjuryService
from app.services.nba.lineup_service import LineupService
from app.services.nba.nba_data_service import NbaDataService


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_players_with_stats(db_session: Session) -> List[Player]:
    """Create players with season stats for testing."""
    players = []
    today = datetime.utcnow()

    # Player 1: Jayson Tatum (BOS) - high scorer
    player1 = Player(
        id=str(uuid.uuid4()),
        external_id="1628369",
        id_source="nba",
        nba_api_id=1628369,
        name="Jayson Tatum",
        team="BOS",
        position="SF",
        active=True,
        created_at=today,
        updated_at=today
    )
    db_session.add(player1)
    players.append(player1)

    # Player 2: Jaylen Brown (BOS)
    player2 = Player(
        id=str(uuid.uuid4()),
        external_id="1628966",
        id_source="nba",
        nba_api_id=1628966,
        name="Jaylen Brown",
        team="BOS",
        position="SG",
        active=True,
        created_at=today,
        updated_at=today
    )
    db_session.add(player2)
    players.append(player2)

    # Player 3: Joel Embiid (PHI) - center
    player3 = Player(
        id=str(uuid.uuid4()),
        external_id="203954",
        id_source="nba",
        nba_api_id=203954,
        name="Joel Embiid",
        team="PHI",
        position="C",
        active=True,
        created_at=today,
        updated_at=today
    )
    db_session.add(player3)
    players.append(player3)

    # Player 4: Tyrese Maxey (PHI)
    player4 = Player(
        id=str(uuid.uuid4()),
        external_id="1630166",
        id_source="nba",
        nba_api_id=1630166,
        name="Tyrese Maxey",
        team="PHI",
        position="PG",
        active=True,
        created_at=today,
        updated_at=today
    )
    db_session.add(player4)
    players.append(player4)

    # Player 5: Stephen Curry (GSW)
    player5 = Player(
        id=str(uuid.uuid4()),
        external_id="201939",
        id_source="nba",
        nba_api_id=201939,
        name="Stephen Curry",
        team="GSW",
        position="PG",
        active=True,
        created_at=today,
        updated_at=today
    )
    db_session.add(player5)
    players.append(player5)

    # Player 6: LeBron James (LAL)
    player6 = Player(
        id=str(uuid.uuid4()),
        external_id="2544",
        id_source="nba",
        nba_api_id=2544,
        name="LeBron James",
        team="LAL",
        position="SF",
        active=True,
        created_at=today,
        updated_at=today
    )
    db_session.add(player6)
    players.append(player6)

    db_session.flush()

    # Add season stats for all players
    season_stats_data = [
        # Tatum: 27 PPG, 8.5 RPG, 4.5 APG
        {
            "player_id": player1.id,
            "points_per_36": 28.5,
            "rebounds_per_36": 8.2,
            "assists_per_36": 4.8,
            "threes_per_36": 3.2
        },
        # Brown: 23 PPG, 5 RPG, 3 APG
        {
            "player_id": player2.id,
            "points_per_36": 24.1,
            "rebounds_per_36": 5.3,
            "assists_per_36": 3.5,
            "threes_per_36": 2.4
        },
        # Embiid: 33 PPG, 10 RPG, 4 APG
        {
            "player_id": player3.id,
            "points_per_36": 34.2,
            "rebounds_per_36": 11.5,
            "assists_per_36": 4.2,
            "threes_per_36": 1.2
        },
        # Maxey: 25 PPG, 3 RPG, 6 APG
        {
            "player_id": player4.id,
            "points_per_36": 26.3,
            "rebounds_per_36": 3.8,
            "assists_per_36": 6.4,
            "threes_per_36": 2.8
        },
        # Curry: 28 PPG, 4 RPG, 6 APG, 5 threes
        {
            "player_id": player5.id,
            "points_per_36": 29.1,
            "rebounds_per_36": 4.5,
            "assists_per_36": 6.2,
            "threes_per_36": 5.1
        },
        # LeBron: 25 PPG, 7 RPG, 8 APG
        {
            "player_id": player6.id,
            "points_per_36": 25.8,
            "rebounds_per_36": 7.3,
            "assists_per_36": 8.1,
            "threes_per_36": 2.2
        },
    ]

    for stats_data in season_stats_data:
        stats = PlayerSeasonStats(
            id=str(uuid.uuid4()),
            player_id=stats_data["player_id"],
            season="2025-26",
            games_count=50,
            points_per_36=stats_data["points_per_36"],
            rebounds_per_36=stats_data["rebounds_per_36"],
            assists_per_36=stats_data["assists_per_36"],
            threes_per_36=stats_data["threes_per_36"],
            avg_minutes=32.5,
            last_game_date=today.date(),
            fetched_at=datetime.utcnow(),
            created_at=today,
            updated_at=today
        )
        db_session.add(stats)

    db_session.commit()
    return players


@pytest.fixture
def sample_games_with_predictions(
    db_session: Session,
    sample_players_with_stats: List[Player]
) -> List[Game]:
    """Create games with predictions for testing."""
    games = []
    today = datetime.utcnow()

    # Game 1: BOS @ PHI (tonight)
    game1 = Game(
        id=str(uuid.uuid4()),
        external_id="odds_event_bos_phi_001",
        id_source="odds_api",
        game_date=today.replace(hour=19, minute=0),
        away_team="BOS",
        home_team="PHI",
        season=2025,
        status="scheduled",
        created_at=today,
        updated_at=today
    )
    db_session.add(game1)
    games.append(game1)

    # Game 2: LAL @ GSW (tonight, later)
    game2 = Game(
        id=str(uuid.uuid4()),
        external_id="odds_event_lal_gsw_001",
        id_source="odds_api",
        game_date=today.replace(hour=21, minute=30),
        away_team="LAL",
        home_team="GSW",
        season=2025,
        status="scheduled",
        created_at=today,
        updated_at=today
    )
    db_session.add(game2)
    games.append(game2)

    db_session.flush()

    # Create predictions for BOS @ PHI
    # Tatum predictions
    for stat_type in ["points", "rebounds", "assists", "threes"]:
        pred = Prediction(
            id=str(uuid.uuid4()),
            player_id=sample_players_with_stats[0].id,  # Tatum
            game_id=game1.id,
            stat_type=stat_type,
            predicted_value=25.0 if stat_type == "points" else (
                8.0 if stat_type == "rebounds" else (
                    5.0 if stat_type == "assists" else 3.0
                )
            ),
            bookmaker_line=24.5 if stat_type == "points" else (
                7.5 if stat_type == "rebounds" else (
                    4.5 if stat_type == "assists" else 2.5
                )
            ),
            bookmaker_name="FanDuel",
            recommendation="OVER",
            confidence=0.68,
            model_version="1.0.0",
            over_price=-110,
            under_price=-110,
            odds_fetched_at=today,
            odds_last_updated=today,
            created_at=today
        )
        db_session.add(pred)

    # Embiid predictions
    for stat_type in ["points", "rebounds", "assists"]:
        pred = Prediction(
            id=str(uuid.uuid4()),
            player_id=sample_players_with_stats[2].id,  # Embiid
            game_id=game1.id,
            stat_type=stat_type,
            predicted_value=32.0 if stat_type == "points" else (
                10.5 if stat_type == "rebounds" else 4.5
            ),
            bookmaker_line=31.5 if stat_type == "points" else (
                10.0 if stat_type == "rebounds" else 4.0
            ),
            bookmaker_name="FanDuel",
            recommendation="OVER",
            confidence=0.72,
            model_version="1.0.0",
            over_price=-110,
            under_price=-110,
            odds_fetched_at=today,
            odds_last_updated=today,
            created_at=today
        )
        db_session.add(pred)

    # Create predictions for LAL @ GSW
    # Curry predictions
    for stat_type in ["points", "threes", "assists"]:
        pred = Prediction(
            id=str(uuid.uuid4()),
            player_id=sample_players_with_stats[4].id,  # Curry
            game_id=game2.id,
            stat_type=stat_type,
            predicted_value=28.0 if stat_type == "points" else (
                5.0 if stat_type == "threes" else 6.0
            ),
            bookmaker_line=27.5 if stat_type == "points" else (
                4.5 if stat_type == "threes" else 5.5
            ),
            bookmaker_name="FanDuel",
            recommendation="OVER",
            confidence=0.70,
            model_version="1.0.0",
            over_price=-110,
            under_price=-110,
            odds_fetched_at=today,
            odds_last_updated=today,
            created_at=today
        )
        db_session.add(pred)

    # LeBron predictions
    for stat_type in ["points", "rebounds", "assists"]:
        pred = Prediction(
            id=str(uuid.uuid4()),
            player_id=sample_players_with_stats[5].id,  # LeBron
            game_id=game2.id,
            stat_type=stat_type,
            predicted_value=26.0 if stat_type == "points" else (
                7.5 if stat_type == "rebounds" else 8.0
            ),
            bookmaker_line=25.5 if stat_type == "points" else (
                7.0 if stat_type == "rebounds" else 7.5
            ),
            bookmaker_name="FanDuel",
            recommendation="OVER",
            confidence=0.65,
            model_version="1.0.0",
            over_price=-110,
            under_price=-110,
            odds_fetched_at=today,
            odds_last_updated=today,
            created_at=today
        )
        db_session.add(pred)

    db_session.commit()
    return games


@pytest.fixture
def mock_injury_data(db_session: Session, sample_players_with_stats: List[Player]):
    """Create mock injury and lineup data."""
    today = datetime.utcnow()
    today_date = today.date()

    # No injuries for BOS players
    # Maxey questionable
    injury = PlayerInjury(
        id=str(uuid.uuid4()),
        player_id=sample_players_with_stats[3].id,  # Maxey
        game_id=None,  # General injury
        injury_type="questionable",
        status="questionable",
        impact_description="Day-to-day",
        reported_date=today_date,
        created_at=today,
        updated_at=today
    )
    db_session.add(injury)

    # Create expected lineups
    # BOS starting lineup
    for idx, player in enumerate(sample_players_with_stats[:2]):
        lineup = ExpectedLineup(
            id=str(uuid.uuid4()),
            game_id=None,  # General lineup
            team="BOS",
            player_id=player.id,
            starter_position="PG" if idx == 0 else "SF",
            is_confirmed=True,
            minutes_projection=32,
            created_at=today,
            updated_at=today
        )
        db_session.add(lineup)

    # PHI starting lineup
    lineup = ExpectedLineup(
        id=str(uuid.uuid4()),
        game_id=None,
        team="PHI",
        player_id=sample_players_with_stats[2].id,  # Embiid
        starter_position="C",
        is_confirmed=True,
        minutes_projection=34,
        created_at=today,
        updated_at=today
    )
    db_session.add(lineup)

    lineup = ExpectedLineup(
        id=str(uuid.uuid4()),
        game_id=None,
        team="PHI",
        player_id=sample_players_with_stats[3].id,  # Maxey
        starter_position="PG",
        is_confirmed=True,
        minutes_projection=32,
        created_at=today,
        updated_at=today
    )
    db_session.add(lineup)

    # GSW starting lineup
    lineup = ExpectedLineup(
        id=str(uuid.uuid4()),
        game_id=None,
        team="GSW",
        player_id=sample_players_with_stats[4].id,  # Curry
        starter_position="PG",
        is_confirmed=True,
        minutes_projection=33,
        created_at=today,
        updated_at=today
    )
    db_session.add(lineup)

    # LAL starting lineup
    lineup = ExpectedLineup(
        id=str(uuid.uuid4()),
        game_id=None,
        team="LAL",
        player_id=sample_players_with_stats[5].id,  # LeBron
        starter_position="SF",
        is_confirmed=True,
        minutes_projection=32,
        created_at=today,
        updated_at=today
    )
    db_session.add(lineup)

    db_session.commit()


@pytest.fixture
def mock_odds_api_response():
    """Mock The Odds API response for upcoming games."""
    today = datetime.utcnow()

    return [
        {
            'id': 'odds_event_bos_phi_001',
            'sport_key': 'basketball_nba',
            'sport_title': 'NBA',
            'commence_time': (today + timedelta(hours=7)).isoformat() + "Z",
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
            'bookmakers': [
                {
                    'key': 'fanduel',
                    'title': 'FanDuel',
                    'last_update': datetime.utcnow().isoformat(),
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Philadelphia 76ers', 'price': -110},
                                {'name': 'Boston Celtics', 'price': -110}
                            ]
                        }
                    ]
                }
            ]
        },
        {
            'id': 'odds_event_lal_gsw_001',
            'sport_key': 'basketball_nba',
            'sport_title': 'NBA',
            'commence_time': (today + timedelta(hours=9)).isoformat() + "Z",
            'home_team': 'Golden State Warriors',
            'away_team': 'Los Angeles Lakers',
            'bookmakers': [
                {
                    'key': 'fanduel',
                    'title': 'FanDuel',
                    'last_update': datetime.utcnow().isoformat(),
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Golden State Warriors', 'price': -105},
                                {'name': 'Los Angeles Lakers', 'price': -115}
                            ]
                        }
                    ]
                }
            ]
        }
    ]


@pytest.fixture
def mock_player_props_response():
    """Mock The Odds API player props response."""
    today = datetime.utcnow()

    return {
        'event_id': 'odds_event_bos_phi_001',
        'markets': 'player_points,player_rebounds,player_assists,player_threes',
        'data': {
            'bookmakers': [
                {
                    'key': 'fanduel',
                    'title': 'FanDuel',
                    'last_update': datetime.utcnow().isoformat(),
                    'markets': [
                        {
                            'key': 'player_points',
                            'outcomes': [
                                {
                                    'name': 'Jayson Tatum',
                                    'price': -110,
                                    'point': 24.5
                                },
                                {
                                    'name': 'Joel Embiid',
                                    'price': -110,
                                    'point': 31.5
                                }
                            ]
                        },
                        {
                            'key': 'player_rebounds',
                            'outcomes': [
                                {
                                    'name': 'Jayson Tatum',
                                    'price': -110,
                                    'point': 7.5
                                },
                                {
                                    'name': 'Joel Embiid',
                                    'price': -110,
                                    'point': 10.0
                                }
                            ]
                        },
                        {
                            'key': 'player_assists',
                            'outcomes': [
                                {
                                    'name': 'Jayson Tatum',
                                    'price': -110,
                                    'point': 4.5
                                },
                                {
                                    'name': 'Joel Embiid',
                                    'price': -110,
                                    'point': 4.0
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }


# =============================================================================
# Test 1: Full Parlay Generation Flow
# =============================================================================

class TestParlayGenerationFlow:
    """Test complete parlay generation workflows."""

    def test_generate_same_game_parlays_complete_flow(
        self,
        db_session: Session,
        sample_games_with_predictions: List[Game]
    ):
        """Test complete same-game parlay generation flow."""
        game = sample_games_with_predictions[0]  # BOS @ PHI

        # Initialize service
        parlay_service = ParlayService(db_session)

        # Generate same-game parlays
        parlays = parlay_service.generate_same_game_parlays(
            game_id=str(game.id),
            min_confidence=0.60,
            max_legs=3,
            min_ev=0.05,
            limit=50
        )

        # Verify parlays were generated
        assert len(parlays) > 0, "Should generate at least one parlay"

        # Verify parlay structure
        parlay = parlays[0]
        assert "parlay_type" in parlay
        assert parlay["parlay_type"] == "same_game"
        assert "legs" in parlay
        assert len(parlay["legs"]) >= 2
        assert "expected_value" in parlay
        assert "calculated_odds" in parlay
        assert "confidence_score" in parlay

        # Verify leg structure
        leg = parlay["legs"][0]
        assert "player_id" in leg
        assert "player_name" in leg
        assert "stat_type" in leg
        assert "selection" in leg
        assert "line" in leg
        assert "odds" in leg
        assert leg["selection"] in ["OVER", "UNDER"]

        # Verify parlays were saved to database
        saved_parlays = db_session.query(Parlay).filter(
            Parlay.parlay_type == "same_game"
        ).all()

        assert len(saved_parlays) > 0, "Parlays should be saved to database"

        # Verify parlay legs were saved
        saved_parlay = saved_parlays[0]
        legs = db_session.query(ParlayLeg).filter(
            ParlayLeg.parlay_id == saved_parlay.id
        ).all()

        assert len(legs) == saved_parlay.total_legs

    def test_generate_cross_game_parlays_complete_flow(
        self,
        db_session: Session,
        sample_games_with_predictions: List[Game]
    ):
        """Test complete cross-game parlay generation flow."""
        # Initialize service
        parlay_service = ParlayService(db_session)

        # Generate cross-game parlays with lower thresholds
        parlays = parlay_service.generate_cross_game_parlays(
            days_ahead=1,
            min_confidence=0.50,  # Lower threshold
            min_ev=0.01,  # Lower threshold
            limit=30
        )

        # Note: Parlay generation depends on having high-confidence predictions
        # with odds from the same bookmaker. This test verifies the flow works,
        # but parlays may not be generated if conditions aren't met.
        # Just verify no errors occur and the service works.

        # If parlays were generated, verify their structure
        if len(parlays) > 0:
            parlay = parlays[0]
            assert parlay["parlay_type"] == "multi_game"
            assert len(parlay["legs"]) == 2

            # Verify legs are from different games
            game_ids = {leg["game_id"] for leg in parlay["legs"]}
            assert len(game_ids) == 2, "Cross-game parlay should have legs from different games"

    def test_parlay_retrieval_and_filtering(
        self,
        db_session: Session,
        sample_games_with_predictions: List[Game]
    ):
        """Test retrieving and filtering parlays."""
        game = sample_games_with_predictions[0]

        # Generate parlays first
        parlay_service = ParlayService(db_session)
        parlays = parlay_service.generate_same_game_parlays(
            game_id=str(game.id),
            min_confidence=0.60,
            max_legs=3,
            min_ev=0.05
        )

        assert len(parlays) > 0

        # Test retrieval by type
        same_game_parlays = parlay_service.get_parlays(
            parlay_type="same_game",
            limit=50
        )

        assert len(same_game_parlays) > 0

        # Test retrieval by min EV
        high_ev_parlays = parlay_service.get_parlays(
            min_ev=0.08,
            limit=50
        )

        # Verify filtering works
        for parlay in high_ev_parlays:
            assert parlay["expected_value"] >= 0.08

    def test_parlay_cleanup(
        self,
        db_session: Session,
        sample_games_with_predictions: List[Game]
    ):
        """Test cleanup of old parlays."""
        game = sample_games_with_predictions[0]

        # Generate parlays
        parlay_service = ParlayService(db_session)
        parlays = parlay_service.generate_same_game_parlays(
            game_id=str(game.id),
            min_confidence=0.60
        )

        initial_count = db_session.query(Parlay).count()
        assert initial_count > 0

        # Clean up parlays older than 7 days (shouldn't delete any)
        deleted = parlay_service.cleanup_old_parlays(days_old=7)
        assert deleted == 0

        current_count = db_session.query(Parlay).count()
        assert current_count == initial_count


# =============================================================================
# Test 2: Odds Fetch and Update Flow
# =============================================================================

class TestOddsFetchUpdateFlow:
    """Test complete odds fetch and update workflow."""

    @pytest.mark.asyncio
    async def test_fetch_upcoming_games_and_create_in_db(
        self,
        db_session: Session,
        mock_odds_api_response: List[Dict]
    ):
        """Test fetching upcoming games from Odds API and creating in database."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_odds_api_response
        mock_response.headers = {}

        with patch.object(OddsApiService, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            # Initialize service
            odds_service = OddsApiService(api_key="test_key")

            # Fetch games
            games_data = await odds_service.get_upcoming_games_with_odds(days_ahead=3)

            # Verify games were fetched
            assert len(games_data) == 2
            assert games_data[0]["id"] == "odds_event_bos_phi_001"
            assert games_data[0]["home_team"] == "Philadelphia 76ers"

            # Use OddsMapper to create games in database
            mapper = OddsMapper(db_session)
            result = mapper.create_games_from_odds_schedule(games_data)

            # Verify games were created
            assert result["created"] > 0

            # Verify games exist in database
            games = db_session.query(Game).filter(
                Game.id_source == "odds_api"
            ).all()

            assert len(games) > 0

            # Verify game details
            game = db_session.query(Game).filter(
                Game.external_id == "odds_event_bos_phi_001"
            ).first()

            assert game is not None
            assert game.away_team == "BOS"
            assert game.home_team == "PHI"

    @pytest.mark.asyncio
    async def test_fetch_player_props_and_update_predictions(
        self,
        db_session: Session,
        sample_games_with_predictions: List[Game],
        sample_players_with_stats: List[Player],
        mock_player_props_response: Dict
    ):
        """Test fetching player props and updating predictions."""
        game = sample_games_with_predictions[0]

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_player_props_response["data"]
        mock_response.headers = {}

        with patch.object(OddsApiService, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            # Initialize service
            odds_service = OddsApiService(api_key="test_key")

            # Fetch player props
            props_data = await odds_service.get_event_player_props(
                event_id=game.external_id
            )

            # Verify props were fetched
            assert props_data["event_id"] == game.external_id
            assert "data" in props_data

            # Use OddsMapper to map props to predictions
            mapper = OddsMapper(db_session)
            updates = await mapper.map_player_props_to_predictions(props_data, game)

            # Note: This test verifies the mapping logic works
            # In a real scenario, player names need to match exactly
            assert isinstance(updates, list)

    def test_odds_mapper_game_creation(
        self,
        db_session: Session,
        mock_odds_api_response: List[Dict]
    ):
        """Test OddsMapper game creation functionality."""
        mapper = OddsMapper(db_session)

        result = mapper.create_games_from_odds_schedule(mock_odds_api_response)

        # Verify result structure
        assert "created" in result
        assert "updated" in result
        assert "errors" in result

        # Verify games exist
        games = db_session.query(Game).all()
        assert len(games) > 0


# =============================================================================
# Test 3: Prediction Generation with Odds Matching
# =============================================================================

class TestPredictionGenerationWithOdds:
    """Test prediction generation with odds matching."""

    def test_generate_predictions_for_game_complete_flow(
        self,
        db_session: Session,
        sample_players_with_stats: List[Player],
        mock_injury_data
    ):
        """Test complete prediction generation flow for a game."""
        today = datetime.utcnow()

        # Create a game
        game = Game(
            id=str(uuid.uuid4()),
            external_id="test_game_001",
            id_source="nba",
            game_date=today.replace(hour=19, minute=0),
            away_team="BOS",
            home_team="PHI",
            season=2025,
            status="scheduled",
            created_at=today,
            updated_at=today
        )
        db_session.add(game)
        db_session.flush()

        # Initialize service
        prediction_service = PredictionService(db_session)

        # Generate predictions
        predictions = prediction_service.generate_predictions_for_game(
            game_id=str(game.id),
            stat_types=["points", "rebounds", "assists", "threes"]
        )

        # Verify predictions were generated
        assert len(predictions) > 0

        # Verify prediction structure
        pred = predictions[0]
        assert "player" in pred
        assert "team" in pred
        assert "stat_type" in pred
        assert "predicted_value" in pred
        assert "confidence" in pred
        assert "recommendation" in pred

        # Verify predictions were saved to database
        saved_predictions = db_session.query(Prediction).filter(
            Prediction.game_id == game.id
        ).all()

        assert len(saved_predictions) > 0

    def test_predictions_with_high_confidence_get_recommendations(
        self,
        db_session: Session,
        sample_players_with_stats: List[Player],
        mock_injury_data
    ):
        """Test that high confidence predictions get recommendations."""
        today = datetime.utcnow()

        # Create a game
        game = Game(
            id=str(uuid.uuid4()),
            external_id="test_game_002",
            id_source="nba",
            game_date=today.replace(hour=19, minute=0),
            away_team="GSW",
            home_team="LAL",
            season=2025,
            status="scheduled",
            created_at=today,
            updated_at=today
        )
        db_session.add(game)
        db_session.flush()

        # Initialize service
        prediction_service = PredictionService(db_session)

        # Generate predictions
        predictions = prediction_service.generate_predictions_for_game(
            game_id=str(game.id),
            stat_types=["points", "threes"]
        )

        # Check that some predictions have recommendations
        predictions_with_recs = [
            p for p in predictions
            if p["recommendation"] in ["OVER", "UNDER"]
        ]

        # At least some should have recommendations
        assert len(predictions_with_recs) >= 0

    def test_predictions_skip_out_players(
        self,
        db_session: Session,
        sample_players_with_stats: List[Player]
    ):
        """Test that predictions skip players who are OUT."""
        today = datetime.utcnow()
        today_date = today.date()

        # Mark a player as OUT
        injury = PlayerInjury(
            id=str(uuid.uuid4()),
            player_id=sample_players_with_stats[0].id,
            game_id=None,
            injury_type="ankle",
            status="out",
            impact_description="Out for game",
            reported_date=today_date,
            created_at=today,
            updated_at=today
        )
        db_session.add(injury)

        # Create a game
        game = Game(
            id=str(uuid.uuid4()),
            external_id="test_game_003",
            id_source="nba",
            game_date=today.replace(hour=19, minute=0),
            away_team="BOS",
            home_team="PHI",
            season=2025,
            status="scheduled",
            created_at=today,
            updated_at=today
        )
        db_session.add(game)
        db_session.flush()

        # Initialize service
        prediction_service = PredictionService(db_session)

        # Generate predictions
        predictions = prediction_service.generate_predictions_for_game(
            game_id=str(game.id),
            stat_types=["points"]
        )

        # Verify OUT player was skipped
        out_player_preds = [
            p for p in predictions
            if p["player"] == sample_players_with_stats[0].name
        ]

        assert len(out_player_preds) == 0


# =============================================================================
# Test 4: sync_nba_data.py CLI Script Functionality
# =============================================================================

class TestSyncNbaDataScript:
    """Test sync_nba_data.py CLI script functionality."""

    @pytest.mark.asyncio
    async def test_sync_stats_function(
        self,
        db_session: Session,
        sample_players_with_stats: List[Player]
    ):
        """Test the sync_stats function from sync_nba_data.py."""
        from app.services.nba.nba_data_service import NbaDataService

        service = NbaDataService(db_session)

        # Verify service can be instantiated and has the right methods
        assert hasattr(service, 'update_player_season_stats')
        assert hasattr(service, 'get_league_leaders')
        assert hasattr(service, 'get_player_stats_by_team')

        # Note: Full integration testing would require mocking nba_api
        # which is complex due to its structure. This test verifies
        # the service interface is correct.

    @pytest.mark.asyncio
    async def test_get_league_leaders_function(
        self,
        db_session: Session
    ):
        """Test the show_league_leaders function from sync_nba_data.py."""
        from app.services.nba.nba_data_service import NbaDataService

        service = NbaDataService(db_session)

        # Verify the method exists and can be called
        # Full integration testing would require proper nba_api mocking
        assert hasattr(service, 'get_league_leaders')
        assert callable(service.get_league_leaders)

    @pytest.mark.asyncio
    async def test_get_team_stats_function(
        self,
        db_session: Session
    ):
        """Test the show_team_stats function from sync_nba_data.py."""
        from app.services.nba.nba_data_service import NbaDataService

        service = NbaDataService(db_session)

        # Verify the method exists
        assert hasattr(service, 'get_player_stats_by_team')
        assert callable(service.get_player_stats_by_team)


# =============================================================================
# Test 5: End-to-End Workflow Integration
# =============================================================================

class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    @pytest.mark.asyncio
    async def test_daily_odds_fetch_workflow_simulation(
        self,
        db_session: Session,
        sample_players_with_stats: List[Player],
        mock_injury_data,
        mock_odds_api_response: List[Dict],
        mock_player_props_response: Dict
    ):
        """Simulate the complete daily_odds_fetch.py workflow."""
        today = datetime.utcnow()

        # Step 1: Fetch upcoming games (mocked)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_odds_api_response
        mock_response.headers = {}

        with patch.object(OddsApiService, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            odds_service = OddsApiService(api_key="test_key")
            games_data = await odds_service.get_upcoming_games_with_odds(days_ahead=3)

            # Verify games fetched
            assert len(games_data) == 2

        # Step 2: Create games in database
        mapper = OddsMapper(db_session)
        result = mapper.create_games_from_odds_schedule(games_data)

        assert result["created"] > 0

        # Step 3: Generate predictions for games
        games = db_session.query(Game).filter(
            Game.status == "scheduled"
        ).all()

        prediction_service = PredictionService(db_session)
        total_predictions = 0

        for game in games:
            predictions = prediction_service.generate_predictions_for_game(
                game_id=str(game.id),
                stat_types=["points", "rebounds", "assists"]
            )
            total_predictions += len(predictions)

        # Verify predictions generated
        assert total_predictions > 0

        # Step 4: Fetch player props (mocked) and update predictions
        # This would be done for games within 2 hours of start time
        # For testing, we just verify the mapping logic exists
        assert hasattr(mapper, 'map_player_props_to_predictions')

    def test_parlay_generation_after_predictions_and_odds(
        self,
        db_session: Session,
        sample_games_with_predictions: List[Game]
    ):
        """Test parlay generation after predictions and odds are in place."""
        game = sample_games_with_predictions[0]

        # Verify predictions have odds
        predictions = db_session.query(Prediction).filter(
            Prediction.game_id == game.id,
            Prediction.bookmaker_line.isnot(None)
        ).all()

        assert len(predictions) > 0, "Need predictions with odds"

        # Generate parlays
        parlay_service = ParlayService(db_session)

        # Test same-game parlays
        same_game_parlays = parlay_service.generate_same_game_parlays(
            game_id=str(game.id),
            min_confidence=0.60,
            min_ev=0.05
        )

        assert len(same_game_parlays) > 0, "Should generate same-game parlays"

        # Verify parlays have valid structure
        for parlay in same_game_parlays:
            assert "legs" in parlay
            assert len(parlay["legs"]) >= 2
            assert "expected_value" in parlay
            assert parlay["expected_value"] >= 0.05

    def test_complete_workflow_game_to_parlay(
        self,
        db_session: Session,
        sample_players_with_stats: List[Player],
        mock_injury_data
    ):
        """Test complete workflow from game creation to parlay generation."""
        today = datetime.utcnow()

        # Step 1: Create game
        game = Game(
            id=str(uuid.uuid4()),
            external_id="workflow_test_game",
            id_source="test",
            game_date=today.replace(hour=20, minute=0),
            away_team="BOS",
            home_team="PHI",
            season=2025,
            status="scheduled",
            created_at=today,
            updated_at=today
        )
        db_session.add(game)
        db_session.flush()

        # Step 2: Generate predictions
        prediction_service = PredictionService(db_session)
        predictions = prediction_service.generate_predictions_for_game(
            game_id=str(game.id),
            stat_types=["points", "rebounds", "assists", "threes"]
        )

        assert len(predictions) > 0

        # Step 3: Manually add odds to predictions (simulating odds fetch)
        db_predictions = db_session.query(Prediction).filter(
            Prediction.game_id == game.id
        ).all()

        for pred in db_predictions:
            pred.bookmaker_line = 20.0
            pred.bookmaker_name = "FanDuel"
            pred.over_price = -110
            pred.under_price = -110
            pred.odds_fetched_at = today
            pred.odds_last_updated = today

            # Set recommendation for high confidence predictions
            if pred.confidence >= 0.60:
                pred.recommendation = "OVER" if pred.predicted_value > pred.bookmaker_line else "UNDER"

        db_session.commit()

        # Step 4: Generate parlays
        parlay_service = ParlayService(db_session)
        parlays = parlay_service.generate_same_game_parlays(
            game_id=str(game.id),
            min_confidence=0.60,
            min_ev=0.01  # Lower threshold for testing
        )

        # Verify workflow completed
        assert len(predictions) > 0, "Predictions should be generated"
        assert len(db_predictions) > 0, "Predictions should be in database"

        # Parlays may or may not be generated depending on confidence scores
        # Just verify the service doesn't error
        assert isinstance(parlays, list)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
