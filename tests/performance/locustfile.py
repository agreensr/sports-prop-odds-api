"""
Performance tests for Sports-Bet-AI-API using Locust.

Tests load on API endpoints to identify:
- Bottlenecks and slow endpoints
- Maximum concurrent users before degradation
- Database query performance under load
- Rate limiting behavior

Usage:
    # Run with default settings (web UI at http://localhost:8089)
    locust

    # Run without web UI (headless mode)
    locust --headless --users 100 --spawn-rate 10 --run-time 60s

    # Run against specific host
    locust --host https://api.example.com

    # See all options
    locust --help
"""
import os
import random
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

# Default host for local testing
DEFAULT_HOST = os.getenv("API_HOST", "http://localhost:8001")


class NBAUser(HttpUser):
    """
    Simulates a user browsing NBA predictions and player data.

    Wait time between requests: 1-3 seconds (realistic browsing behavior).
    """

    # Wait between tasks (seconds)
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a user starts. Login or setup goes here."""
        # Check health before starting
        self.client.get("/api/health")

    @task(3)  # Weight: 3x more likely than weight=1 tasks
    def get_nba_predictions(self):
        """Browse predictions for games."""
        # Random game ID or recent games
        self.client.get("/api/v1/nba/predictions")

    @task(2)
    def get_nba_predictions_by_game(self):
        """Get predictions for a specific game."""
        # Use a recent game ID (would be dynamic in production)
        game_ids = [
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440002",
        ]
        game_id = random.choice(game_ids)
        self.client.get(f"/api/v1/nba/predictions?game_id={game_id}")

    @task(2)
    def get_nba_top_picks(self):
        """Get top betting picks."""
        self.client.get("/api/v1/nba/top-picks")

    @task(1)
    def get_nba_players(self):
        """Browse player list."""
        self.client.get("/api/v1/nba/players")

    @task(1)
    def get_nba_player_by_name(self):
        """Search for a specific player."""
        players = ["Jayson Tatum", "Luka Doncic", "LeBron James"]
        player = random.choice(players)
        self.client.get(f"/api/v1/nba/players?name={player}")

    @task(1)
    def get_nba_odds(self):
        """Get betting odds."""
        self.client.get("/api/v1/nba/odds")

    @task(1)
    def get_nba_upcoming_games(self):
        """Get upcoming games."""
        self.client.get("/api/v1/nba/games/upcoming")


class NFLUser(HttpUser):
    """
    Simulates a user browsing NFL predictions.

    Separate user class allows testing multi-sport load distribution.
    """

    wait_time = between(2, 4)  # Slower browsing pattern

    def on_start(self):
        self.client.get("/api/health")

    @task(3)
    def get_nfl_predictions(self):
        self.client.get("/api/v1/nfl/predictions")

    @task(2)
    def get_nfl_top_picks(self):
        self.client.get("/api/v1/nfl/top-picks")

    @task(1)
    def get_nfl_players(self):
        self.client.get("/api/v1/nfl/players")


class AccuracyUser(HttpUser):
    """
    Simulates a user checking prediction accuracy.

    These queries involve aggregations and may be slower.
    """

    wait_time = between(5, 10)  # Less frequent checks

    @task
    def get_overall_accuracy(self):
        """Get overall prediction accuracy."""
        self.client.get("/api/v1/accuracy/overall")

    @task
    def get_accuracy_by_stat(self):
        """Get accuracy for specific stat type."""
        stats = ["points", "rebounds", "assists", "threes"]
        stat = random.choice(stats)
        self.client.get(f"/api/v1/accuracy/by-stat?stat_type={stat}")

    @task
    def get_accuracy_resolutions(self):
        """Get prediction resolution status."""
        self.client.get("/api/v1/accuracy/resolutions")


class MetricsUser(HttpUser):
    """
    Simulates monitoring/prometheus scraping.

    High frequency, lightweight requests.
    """

    wait_time = between(10, 15)  # Poll every 10-15 seconds

    @task
    def get_metrics(self):
        """Scrape Prometheus metrics."""
        self.client.get("/metrics")


# Weight distribution for mixed traffic
# 70% NBA users, 15% NFL users, 10% Accuracy checkers, 5% Metrics scrapers
class MixedTrafficUser(HttpUser):
    """
    Weighted user that randomly behaves as different user types.

    Simulates realistic mixed traffic patterns.
    """

    wait_time = between(1, 3)

    @task(7)
    def nba_browse(self):
        """70% weight - NBA browsing."""
        endpoints = [
            "/api/v1/nba/predictions",
            "/api/v1/nba/top-picks",
            "/api/v1/nba/players",
            "/api/v1/nba/odds",
        ]
        self.client.get(random.choice(endpoints))

    @task(2)
    def accuracy_check(self):
        """20% weight - Accuracy checks."""
        self.client.get("/api/v1/accuracy/overall")

    @task(1)
    def health_check(self):
        """10% weight - Health checks."""
        self.client.get("/api/health")


# =============================================================================
# Event Handlers for Custom Metrics and Reporting
# =============================================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the load test starts."""
    print(f"\n{'='*60}")
    print(f"Starting load test against: {environment.host}")
    print(f"Target users: {environment.target_user_count if environment.target_user_count else 'unlimited'}")
    print(f"Spawn rate: {environment.spawn_rate if environment.spawn_rate else 'default'} users/sec")
    print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the load test ends."""
    print(f"\n{'='*60}")
    print("Load test completed")
    print(f"{'='*60}\n")

    # Print summary statistics
    if environment.stats.total.fail_ratio > 0.05:  # More than 5% failures
        print(f"⚠️  WARNING: Failure rate was {environment.stats.total.fail_ratio:.1%}")
    else:
        print(f"✅ Failure rate was acceptable: {environment.stats.total.fail_ratio:.1%}")

    if environment.stats.total.avg_response_time > 1000:  # More than 1 second
        print(f"⚠️  WARNING: Average response time was {environment.stats.total.avg_response_time:.0f}ms")
    else:
        print(f"✅ Average response time: {environment.stats.total.avg_response_time:.0f}ms")

    # Request/sec
    rps = environment.stats.total.total_rps
    print(f"📊 Throughput: {rps:.1f} requests/sec")


# =============================================================================
# Quick Test Configuration
# =============================================================================

class QuickTestUser(HttpUser):
    """
    Lightweight user for quick smoke tests.

    Usage: locust -f locustfile.py QuickTestUser --users 10 --headless --run-time 10s
    """

    wait_time = between(0, 1)  # Minimal wait time

    @task
    def health_check(self):
        self.client.get("/api/health")

    @task
    def get_predictions(self):
        self.client.get("/api/v1/nba/predictions")


# =============================================================================
# Stress Test Configuration
# =============================================================================

class StressTestUser(HttpUser):
    """
    Aggressive user for stress testing.

    Minimal wait times, focus on heavy endpoints.
    """

    wait_time = between(0, 0.5)  # Very aggressive

    @task(5)
    def get_predictions(self):
        """Heavy endpoint - likely to cause issues."""
        self.client.get("/api/v1/nba/predictions")

    @task(3)
    def get_top_picks(self):
        """Involves sorting and filtering."""
        self.client.get("/api/v1/nba/top-picks")

    @task(2)
    def get_accuracy(self):
        """Involves database aggregations."""
        self.client.get("/api/v1/accuracy/overall")
