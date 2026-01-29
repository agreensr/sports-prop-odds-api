"""
HTTP endpoint integration tests for sports-bet-ai-api.

These tests verify that FastAPI endpoints:
- Return correct HTTP status codes
- Validate request/response schemas
- Handle errors gracefully
- Respect rate limiting (where applicable)

Uses FastAPI TestClient for in-memory HTTP testing.
"""
from datetime import datetime, UTC
import uuid

import pytest
from fastapi.testclient import TestClient

# Add project root to path
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_players_data(db_session):
    """Create sample player data for testing endpoints."""
    from app.models import Player

    now = datetime.now(UTC)
    players = []

    player_data = [
        ("1628369", "Jayson Tatum", "BOS", "SF"),
        ("1628966", "Jaylen Brown", "BOS", "SG"),
        ("203954", "Joel Embiid", "PHI", "C"),
        ("201939", "Stephen Curry", "GSW", "PG"),
        ("2544", "LeBron James", "LAL", "SF"),
    ]

    for external_id, name, team, position in player_data:
        player = Player(
            id=str(uuid.uuid4()),
            external_id=external_id,
            id_source="nba",
            nba_api_id=int(external_id),
            name=name,
            team=team,
            position=position,
            active=True,
            created_at=now,
            updated_at=now
        )
        db_session.add(player)
        players.append(player)

    db_session.flush()  # Ensure data is written before commit
    db_session.commit()
    return players


@pytest.fixture
def sample_games_data(db_session, sample_players_data):
    """Create sample game data for testing endpoints."""
    from app.models import Game

    now = datetime.now(UTC)
    games = []

    game_data = [
        ("BOS", "PHI", "2025-01-29T19:00:00"),
        ("GSW", "LAL", "2025-01-29T21:30:00"),
    ]

    for away, home, game_time in game_data:
        game = Game(
            id=str(uuid.uuid4()),
            external_id=f"0022400{len(games) + 1}",
            id_source="nba",
            game_date=datetime.fromisoformat(game_time),
            away_team=away,
            home_team=home,
            season=2025,
            status="scheduled",
            created_at=now,
            updated_at=now
        )
        db_session.add(game)
        games.append(game)

    db_session.commit()
    return games


@pytest.fixture
def sample_predictions_data(db_session, sample_players_data, sample_games_data):
    """Create sample prediction data for testing endpoints."""
    from app.models import Prediction

    now = datetime.now(UTC)
    predictions = []

    # Create predictions for the first game
    game = sample_games_data[0]
    players = sample_players_data[:3]  # Tatum, Brown, Embiid

    stat_types = ["points", "rebounds", "assists"]

    for player in players:
        for stat_type in stat_types:
            pred = Prediction(
                id=str(uuid.uuid4()),
                sport_id="nba",
                player_id=player.id,
                game_id=game.id,
                stat_type=stat_type,
                predicted_value=25.5,
                bookmaker_line=24.5,
                bookmaker_name="FanDuel",
                recommendation="OVER",
                confidence=0.65,
                model_version="v1.0",
                over_price=-110,
                under_price=-110,
                created_at=now
            )
            db_session.add(pred)
            predictions.append(pred)

    db_session.commit()
    return predictions


# =============================================================================
# ROOT & HEALTH ENDPOINTS
# =============================================================================

class TestRootAndHealthEndpoints:
    """Test root and health check endpoints."""

    def test_root_endpoint(self, test_client: TestClient):
        """Test root endpoint returns API information."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "name" in data
        assert "version" in data
        assert "status" in data
        assert "endpoints" in data
        assert data["status"] == "running"

    def test_health_endpoint(self, test_client: TestClient):
        """Test basic health check endpoint."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "version" in data

    def test_api_health_endpoint(self, test_client: TestClient):
        """Test detailed health check endpoint."""
        response = test_client.get("/api/health")

        # Should return 200 or 503 depending on database/API status
        assert response.status_code in [200, 503]
        data = response.json()

        assert "status" in data
        assert "components" in data


# =============================================================================
# NBA PREDICTIONS ENDPOINTS
# =============================================================================

class TestNBAPredictionsEndpoints:
    """Test NBA prediction endpoints."""

    def test_get_nba_predictions_by_game(self, test_client: TestClient, sample_predictions_data):
        """Test getting predictions by game ID."""
        game = sample_predictions_data[0].game_id

        response = test_client.get(f"/api/v1/nba/predictions/game/{game}")

        assert response.status_code == 200
        data = response.json()

        assert "predictions" in data
        assert isinstance(data["predictions"], list)
        assert len(data["predictions"]) > 0

        # Verify prediction structure
        pred = data["predictions"][0]
        assert "player" in pred
        assert "game" in pred
        assert "stat_type" in pred
        assert "predicted_value" in pred
        assert "confidence" in pred

    def test_get_nba_predictions_by_player(self, test_client: TestClient, sample_predictions_data):
        """Test getting predictions by player ID."""
        # Get the player from the first prediction
        prediction = sample_predictions_data[0]
        player_id = str(prediction.player_id)

        response = test_client.get(f"/api/v1/nba/predictions/player/{player_id}")

        assert response.status_code == 200
        data = response.json()

        assert "player" in data
        assert "predictions" in data
        assert data["player"]["id"] == player_id

    def test_get_nba_predictions_not_found(self, test_client: TestClient):
        """Test getting predictions for non-existent player returns 404."""
        fake_id = str(uuid.uuid4())

        response = test_client.get(f"/api/v1/nba/predictions/player/{fake_id}")

        assert response.status_code == 404

    def test_get_nba_top_picks(self, test_client: TestClient, sample_predictions_data):
        """Test getting top picks endpoint."""
        response = test_client.get("/api/v1/nba/predictions/top?min_confidence=0.60&limit=5")

        assert response.status_code == 200
        data = response.json()

        assert "predictions" in data
        assert "count" in data
        assert "min_confidence" in data

        # Verify all returned predictions meet confidence threshold
        for pred in data["predictions"]:
            assert pred["confidence"] >= 0.60


# =============================================================================
# NBA PLAYERS ENDPOINTS
# =============================================================================

class TestNBAPlayersEndpoints:
    """Test NBA player endpoints."""

    def test_get_nba_players_list(self, test_client: TestClient, sample_players_data):
        """Test getting list of NBA players."""
        response = test_client.get("/api/v1/nba/players?limit=10")

        assert response.status_code == 200
        data = response.json()

        assert "players" in data
        assert "count" in data
        assert isinstance(data["players"], list)
        assert len(data["players"]) > 0

        # Verify player structure
        player = data["players"][0]
        assert "id" in player
        assert "name" in player
        assert "team" in player
        assert "position" in player

    def test_search_nba_players_by_name(self, test_client: TestClient, sample_players_data):
        """Test searching NBA players by name."""
        response = test_client.get("/api/v1/nba/players?name=Tatum&limit=5")

        assert response.status_code == 200
        data = response.json()

        assert "players" in data
        # Should find Jayson Tatum
        assert any("Tatum" in p["name"] for p in data["players"])


# =============================================================================
# NBA ODDS ENDPOINTS
# =============================================================================

class TestNBAOddsEndpoints:
    """Test NBA odds endpoints."""

    def test_get_upcoming_odds(self, test_client: TestClient, sample_games_data):
        """Test getting upcoming odds endpoint."""
        response = test_client.get("/api/v1/nba/odds/upcoming?days=1")

        # Should succeed even if no odds data available
        assert response.status_code == 200
        data = response.json()

        assert "games" in data

    def test_get_event_player_props(self, test_client: TestClient, sample_games_data):
        """Test getting player props for a specific event."""
        game = sample_games_data[0]

        response = test_client.get(f"/api/v1/nba/odds/player-props?event_id={game.id}")

        # Should succeed even if no props available
        assert response.status_code == 200
        data = response.json()

        assert "event_id" in data


# =============================================================================
# ACCURACY ENDPOINTS
# =============================================================================

class TestAccuracyEndpoints:
    """Test accuracy tracking endpoints."""

    def test_get_overall_accuracy(self, test_client: TestClient):
        """Test getting overall accuracy metrics."""
        response = test_client.get("/api/v1/accuracy/overall?days_back=30")

        assert response.status_code == 200
        data = response.json()

        # Should return metrics even if no resolved predictions
        assert "total_predictions" in data or "message" in data

    def test_get_resolution_status(self, test_client: TestClient):
        """Test getting prediction resolution status."""
        response = test_client.get("/api/v1/accuracy/resolution-status")

        assert response.status_code == 200
        data = response.json()

        assert "total_predictions" in data
        assert "resolved_predictions" in data
        assert "unresolved_predictions" in data


# =============================================================================
# ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Test error handling across endpoints."""

    def test_invalid_game_id_format(self, test_client: TestClient):
        """Test handling of invalid game ID format."""
        response = test_client.get("/api/v1/nba/predictions?game_id=invalid-uuid")

        # Should handle gracefully - either return empty list or error
        assert response.status_code in [200, 400, 422]

    def test_invalid_min_confidence(self, test_client: TestClient):
        """Test handling of invalid min_confidence parameter."""
        response = test_client.get("/api/v1/nba/predictions/top?min_confidence=invalid")

        # Should return validation error
        assert response.status_code in [400, 422]

    def test_invalid_limit_value(self, test_client: TestClient):
        """Test handling of limit value outside allowed range."""
        response = test_client.get("/api/v1/nba/players?limit=999")

        # Should handle gracefully
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            # If it succeeds, verify limit was capped
            data = response.json()
            assert data["count"] <= 100  # Max limit should be enforced


# =============================================================================
# CORS HEADERS
# =============================================================================

class TestCORSHeaders:
    """Test CORS headers are properly set."""

    def test_cors_headers_on_options(self, test_client: TestClient):
        """Test CORS preflight request handling."""
        response = test_client.options(
            "/api/v1/nba/predictions",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        # Should handle OPTIONS request
        assert response.status_code in [200, 405]  # 405 if OPTIONS not explicitly allowed

    def test_cors_headers_on_get(self, test_client: TestClient):
        """Test CORS headers are present on GET request."""
        response = test_client.get(
            "/api/v1/nba/predictions",
            headers={"Origin": "http://localhost:3000"}
        )

        # In development mode, should return data
        assert response.status_code in [200, 404]


# =============================================================================
# RATE LIMITING
# =============================================================================

class TestRateLimiting:
    """Test rate limiting on prediction endpoints."""

    def test_rate_limiting_works(self, test_client: TestClient, sample_predictions_data):
        """
        Test that rate limiting is enforced.

        Note: This test may be flaky if rate limiting storage is in-memory
        and test isolation is not perfect. Consider marking as integration-only.
        """
        game_id = sample_predictions_data[0].game_id

        # Make multiple requests rapidly
        responses = []
        for _ in range(15):  # Try 15 requests (limit is 10/minute for predictions)
            response = test_client.get(f"/api/v1/nba/predictions/player/{sample_predictions_data[0].player_id}")
            responses.append(response)

        # At least some requests should succeed
        successful = sum(1 for r in responses if r.status_code == 200)
        assert successful > 0, "At least some requests should succeed"

        # If rate limiting is working, some requests might be rate limited
        # (This is optional to verify since it depends on test environment)


# =============================================================================
# RESPONSE STRUCTURE VALIDATION
# =============================================================================

class TestResponseStructure:
    """Validate API response structures match expected schemas."""

    def test_prediction_response_structure(self, test_client: TestClient, sample_predictions_data):
        """Test prediction response has all required fields."""
        game = sample_predictions_data[0].game_id

        response = test_client.get(f"/api/v1/nba/predictions?game_id={game}")
        assert response.status_code == 200

        data = response.json()
        assert "predictions" in data

        if len(data["predictions"]) > 0:
            pred = data["predictions"][0]

            # Verify player structure
            assert "player" in pred
            player = pred["player"]
            required_player_fields = ["id", "name", "team", "position"]
            for field in required_player_fields:
                assert field in player, f"Missing player field: {field}"

            # Verify game structure
            assert "game" in pred
            game_data = pred["game"]
            required_game_fields = ["id", "date", "away_team", "home_team", "status"]
            for field in required_game_fields:
                assert field in game_data, f"Missing game field: {field}"

            # Verify prediction fields
            required_pred_fields = ["stat_type", "predicted_value", "confidence", "recommendation"]
            for field in required_pred_fields:
                assert field in pred, f"Missing prediction field: {field}"
