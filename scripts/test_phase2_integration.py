#!/usr/bin/env python3
"""
Phase 2 Integration Test - ESPN API Data for All Sports

This script tests the ESPN API integration to verify data fetching
works correctly for all supported sports (NBA, NFL, MLB, NHL).

Tests:
1. ESPN API Service - connection and data fetching for all sports
2. Scores endpoint - game data for each sport
3. News endpoint - news articles for each sport
4. Teams endpoint - team information for each sport

Usage:
    python scripts/test_phase2_integration.py              # Test all sports
    python scripts/test_phase2_integration.py --sport nba  # Test specific sport
    python scripts/test_phase2_integration.py --verbose    # Detailed output
"""
import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional
import os

# Add parent directory to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Phase2Tester:
    """Test suite for Phase 2 ESPN API integration."""

    def __init__(self, verbose: bool = False):
        """Initialize the test suite."""
        self.verbose = verbose
        self.results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }

        # ESPN API league identifiers
        self.sport_configs = {
            'nba': {'league': 'basketball/nba', 'name': 'NBA'},
            'nfl': {'league': 'football/nfl', 'name': 'NFL'},
            'mlb': {'league': 'baseball/mlb', 'name': 'MLB'},
            'nhl': {'league': 'hockey/nhl', 'name': 'NHL'}
        }

    def log(self, message: str, level: str = "info"):
        """Log message based on verbosity."""
        if level == "debug" and not self.verbose:
            return
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)

    def assert_test(self, condition: bool, test_name: str, error_msg: str = "") -> bool:
        """Assert a test condition and track results."""
        if condition:
            self.results["passed"] += 1
            self.log(f"  ✅ {test_name}", "info")
            return True
        else:
            self.results["failed"] += 1
            self.log(f"  ❌ {test_name}: {error_msg}", "error")
            self.results["errors"].append(f"{test_name}: {error_msg}")
            return False

    async def test_espn_service_for_sport(self, sport_id: str) -> Dict[str, Any]:
        """Test ESPN API service for a specific sport."""
        config = self.sport_configs[sport_id]
        name = config['name']
        league = config['league']

        self.log("\n" + "="*70, "info")
        self.log(f"TEST {self._get_test_number()}: ESPN API - {name}", "info")
        self.log("="*70, "info")

        results = {
            'sport': sport_id,
            'name': name,
            'scores_count': 0,
            'news_count': 0,
            'teams_count': 0,
            'roster_count': 0,
            'passed': 0,
            'failed': 0
        }

        try:
            from app.services.core.espn_service import ESPNApiService

            service = ESPNApiService()

            # Test 1: Get scores - use YYYYMMDD format expected by ESPN API
            # Use yesterday's date to ensure we have data
            from datetime import timedelta
            test_date = (date.today() - timedelta(days=1)).strftime('%Y%m%d')

            self.log(f"\n  Testing {name} scores endpoint (date: {test_date})...", "info")
            scores = await service.get_scores(sport_id, test_date)

            self.assert_test(
                scores is not None,
                f"{name} GET scores",
                "API returned None"
            )

            self.assert_test(
                isinstance(scores, list),
                f"{name} scores format",
                f"Expected list, got {type(scores)}"
            )

            if scores:
                results['scores_count'] = len(scores)
                self.log(f"    Found {len(scores)} games", "info")

                # Validate score structure - ESPN API returns 'date' field
                sample = scores[0]
                has_required = 'date' in sample or any('date' in s for s in scores[:3])
                self.assert_test(
                    has_required,
                    f"{name} score has date",
                    f"Score structure: {list(sample.keys())[:5]}"
                )

                if self.verbose and scores:
                    # ESPN API structure: games have 'name', 'date', 'status', 'competitors'
                    self.log(f"\n  Sample {name} game:", "debug")
                    self.log(f"    Name: {sample.get('name', 'N/A')}", "debug")
                    self.log(f"    Date: {sample.get('date', 'N/A')}", "debug")
                    self.log(f"    Status: {sample.get('status', {}).get('type', {}).get('name', 'N/A')}", "debug")

            # Test 2: Get news
            self.log(f"\n  Testing {name} news endpoint...", "info")
            news = await service.get_news(sport_id, limit=10)

            self.assert_test(
                news is not None,
                f"{name} GET news",
                "API returned None"
            )

            self.assert_test(
                isinstance(news, list),
                f"{name} news format",
                f"Expected list, got {type(news)}"
            )

            if news:
                results['news_count'] = len(news)
                self.log(f"    Found {len(news)} news articles", "info")

                # Validate news structure - check if it has proper content
                # ESPN news can be a dict with 'headline' or other structures
                if news and isinstance(news[0], dict):
                    has_title = 'headline' in news[0] or 'title' in news[0] or 'description' in news[0]
                    self.assert_test(
                        has_title,
                        f"{name} news has title/headline",
                        f"News structure: {list(news[0].keys())[:5]}"
                    )

                    if self.verbose and news:
                        self.log(f"\n  Sample {name} news:", "debug")
                        title = news[0].get('headline') or news[0].get('title') or news[0].get('description', 'N/A')
                        self.log(f"    Title: {title}", "debug")

            # Test 3: Get teams
            self.log(f"\n  Testing {name} teams endpoint...", "info")
            teams = await service.get_teams(sport_id)

            self.assert_test(
                teams is not None,
                f"{name} GET teams",
                "API returned None"
            )

            self.assert_test(
                isinstance(teams, list),
                f"{name} teams format",
                f"Expected list, got {type(teams)}"
            )

            if teams:
                results['teams_count'] = len(teams)
                self.log(f"    Found {len(teams)} teams", "info")

                # Validate team structure - ESPN API returns 'id' and 'name'/'displayName'
                sample = teams[0]
                has_id = 'id' in sample or any('id' in t for t in teams[:3])
                has_name = 'displayName' in sample or 'name' in sample or any(
                    'displayName' in t or 'name' in t for t in teams[:3]
                )

                self.assert_test(
                    has_id,
                    f"{name} team has id",
                    f"Team structure: {list(sample.keys())[:5]}"
                )

                self.assert_test(
                    has_name,
                    f"{name} team has name/displayName",
                    f"Team structure: {list(sample.keys())[:5]}"
                )

                if self.verbose and teams:
                    self.log(f"\n  Sample {name} team:", "debug")
                    name = teams[0].get('displayName') or teams[0].get('name', 'N/A')
                    self.log(f"    Name: {name}", "debug")
                    self.log(f"    Abbr: {teams[0].get('abbreviation', 'N/A')}", "debug")
                    self.log(f"    ID: {teams[0].get('id', 'N/A')}", "debug")

                # Test 4: Get roster for first team
                if teams and len(teams) > 0:
                    first_team = teams[0]
                    team_id = first_team.get('id')

                    self.log(f"\n  Testing {name} roster for {first_team.get('abbreviation', first_team.get('displayName'))}...", "info")

                    roster = await service.get_team_roster(sport_id, team_id)

                    self.assert_test(
                        roster is not None,
                        f"{name} GET roster",
                        "API returned None"
                    )

                    if roster:
                        results['roster_count'] = len(roster.get('athletes', []))
                        athletes = roster.get('athletes', [])
                        self.log(f"    Found {len(athletes)} players", "info")

                        if athletes and self.verbose:
                            self.log(f"\n  Sample {name} player:", "debug")
                            player = athletes[0]
                            self.log(f"    Name: {player.get('displayName', 'N/A')}", "debug")
                            self.log(f"    Position: {player.get('position', {}).get('abbreviation', 'N/A')}", "debug")
                            self.log(f"    Jersey: {player.get('jersey', 'N/A')}", "debug")

            results['passed'] = self.results["passed"]
            results['failed'] = self.results["failed"]

        except Exception as e:
            self.log(f"  ❌ {name} ESPN API Error: {e}", "error")
            if self.verbose:
                import traceback
                traceback.print_exc()
            results['failed'] += 1
            self.results["errors"].append(f"{name} ESPN API: {str(e)}")

        return results

    async def test_espn_service_basic(self) -> bool:
        """Test ESPN API service basic connectivity."""
        self.log("\n" + "="*70, "info")
        self.log("TEST 1: ESPN API Service - Basic Connectivity", "info")
        self.log("="*70, "info")

        try:
            from app.services.core.espn_service import ESPNApiService

            service = ESPNApiService()
            self.assert_test(True, "ESPN Service Instantiation", "Service created successfully")

            # Test with NBA - use yesterday's date in YYYYMMDD format
            from datetime import timedelta
            test_date = (date.today() - timedelta(days=1)).strftime('%Y%m%d')
            scores = await service.get_scores('nba', test_date)
            self.assert_test(
                scores is not None,
                "ESPN API connectivity test",
                "API returned None"
            )

            return self.results["failed"] == 0

        except Exception as e:
            self.assert_test(False, "ESPN Service Connection", str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def _get_test_number(self) -> int:
        """Get the next test number."""
        return self.results["passed"] + self.results["failed"] + 2

    def print_summary(self):
        """Print test summary."""
        self.log("\n" + "="*70, "info")
        self.log("PHASE 2 ESPN API INTEGRATION TEST SUMMARY", "info")
        self.log("="*70, "info")

        total = self.results["passed"] + self.results["failed"]
        pass_rate = (self.results["passed"] / total * 100) if total > 0 else 0

        self.log(f"\n  Total Tests: {total}", "info")
        self.log(f"  ✅ Passed: {self.results['passed']}", "info")
        self.log(f"  ❌ Failed: {self.results['failed']}", "info")
        self.log(f"  Pass Rate: {pass_rate:.1f}%", "info")

        if self.results["errors"]:
            self.log("\n  Errors:", "error")
            for error in self.results["errors"][:5]:  # Show first 5 errors
                self.log(f"    - {error}", "error")
            if len(self.results["errors"]) > 5:
                self.log(f"    ... and {len(self.results['errors']) - 5} more", "error")

        self.log("\n" + "="*70, "info")

        if pass_rate >= 80:
            self.log("🎉 Phase 2 ESPN API Integration: PASSED (>80% pass rate)", "info")
        elif pass_rate >= 50:
            self.log("⚠️  Phase 2 ESPN API Integration: PARTIAL (50-80% pass rate)", "info")
        else:
            self.log("❌ Phase 2 ESPN API Integration: FAILED (<50% pass rate)", "info")

        self.log("="*70 + "\n", "info")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Phase 2 ESPN API integration for all sports"
    )
    parser.add_argument(
        '--sport',
        type=str,
        choices=['nba', 'nfl', 'mlb', 'nhl', 'all'],
        default='all',
        help='Sport to test (default: all)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable detailed output'
    )

    args = parser.parse_args()

    tester = Phase2Tester(verbose=args.verbose)

    # Test ESPN service connection first
    await tester.test_espn_service_basic()

    # Test ESPN API for each sport
    sports_to_test = ['nba', 'nfl', 'mlb', 'nhl'] if args.sport == 'all' else [args.sport]

    sport_results = {}
    for sport in sports_to_test:
        result = await tester.test_espn_service_for_sport(sport)
        sport_results[sport] = result

    # Print sport-specific summary
    if args.verbose and sport_results:
        tester.log("\n" + "="*70, "info")
        tester.log("SPORT-SPECIFIC RESULTS", "info")
        tester.log("="*70, "info")
        for sport, result in sport_results.items():
            tester.log(
                f"\n{result['name']}:\n"
                f"  Scores/Games: {result['scores_count']}\n"
                f"  News Articles: {result['news_count']}\n"
                f"  Teams: {result['teams_count']}\n"
                f"  Roster: {result['roster_count']}",
                "info"
            )

    # Print final summary
    tester.print_summary()

    # Exit with appropriate code
    sys.exit(0 if tester.results["failed"] == 0 else 1)


if __name__ == '__main__':
    asyncio.run(main())
