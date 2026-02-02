# Integration Tests

This directory contains HTTP endpoint integration tests using FastAPI's TestClient.

## Running Tests

```bash
# Using your existing development environment
pytest tests/api/test_endpoints.py -v

# Run specific test class
pytest tests/api/test_endpoints.py::TestRootAndHealthEndpoints -v

# Run with coverage
pytest tests/api/ --cov=app.api --cov-report=html
```

## Test Coverage

The following endpoint categories are tested:

| Category | Endpoints | Test File |
|----------|-----------|-----------|
| Root & Health | `/`, `/health`, `/api/health` | test_endpoints.py |
| NBA Predictions | `/api/nba/predictions/*` | test_endpoints.py |
| NBA Players | `/api/nba/players` | test_endpoints.py |
| NBA Odds | `/api/nba/odds/*` | test_endpoints.py |
| Accuracy | `/api/accuracy/*` | test_endpoints.py |
| Error Handling | Various endpoints | test_endpoints.py |
| CORS Headers | All endpoints | test_endpoints.py |
| Response Structure | Prediction endpoints | test_endpoints.py |

## Adding New Tests

When adding new endpoints, create test classes following this pattern:

```python
class TestNewEndpoint:
    """Test new API endpoints."""

    def test_endpoint_success(self, test_client: TestClient):
        """Test successful endpoint response."""
        response = test_client.get("/api/new-endpoint")
        assert response.status_code == 200

    def test_endpoint_with_params(self, test_client: TestClient):
        """Test endpoint with query parameters."""
        response = test_client.get("/api/new-endpoint?param=value")
        assert response.status_code == 200

    def test_endpoint_error_case(self, test_client: TestClient):
        """Test endpoint error handling."""
        response = test_client.get("/api/new-endpoint?invalid=value")
        assert response.status_code in [400, 422]
```

## Fixtures Available

From `../conftest.py`:

- `test_client`: FastAPI TestClient with test database
- `db_session`: SQLAlchemy session with in-memory SQLite database
- `sample_players_data`: Sample NBA players
- `sample_games_data`: Sample NBA games
- `sample_predictions_data`: Sample predictions

## Notes

- Tests use SQLite in-memory database for isolation
- Each test gets a fresh database session
- Rate limiting tests may be flaky in test environment
- External API calls should be mocked in tests
