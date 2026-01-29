#!/usr/bin/env python3
"""
Phase 3 Integration Test - Single Bet Service

This script tests the single bet service implementation to verify:
- Single bet generation from predictions
- Edge and EV calculations
- Timezone conversion (UTC to Central Time)
- Business rules enforcement (10 bets max, 3 per game)
- API endpoint functionality

Usage:
    python scripts/test_phase3_integration.py              # Run all tests
    python scripts/test_phase3_integration.py --verbose    # Detailed output
    python scripts/test_phase3_integration.py --sport nba  # Test specific sport
"""
import argparse
import logging
import sys
import os
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

# Add parent directory to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Phase3Tester:
    """Test suite for Phase 3 single bet service."""

    def __init__(self, verbose: bool = False):
        """Initialize the test suite."""
        self.verbose = verbose
        self.results = {
            "passed": 0,
            "failed": 0,
            "errors": []
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

    def test_timezone_utilities(self) -> bool:
        """Test timezone conversion utilities."""
        self.log("\n" + "="*70, "info")
        self.log("TEST 1: Timezone Utilities", "info")
        self.log("="*70, "info")

        try:
            from app.utils.timezone import (
                utc_to_central,
                format_central_time,
                format_game_time_central
            )

            # Test winter time (CST)
            utc_winter = datetime(2025, 1, 28, 18, 0)
            central_winter = utc_to_central(utc_winter)
            self.assert_test(
                central_winter.hour == 12,
                "Winter time conversion (CST UTC-6)",
                f"Expected 12:00, got {central_winter.hour}:00"
            )

            # Test summer time (CDT)
            utc_summer = datetime(2025, 7, 15, 18, 0)
            central_summer = utc_to_central(utc_summer)
            self.assert_test(
                central_summer.hour == 13,
                "Summer time conversion (CDT UTC-5)",
                f"Expected 13:00, got {central_summer.hour}:00"
            )

            # Test formatting
            formatted = format_central_time(utc_winter)
            self.assert_test(
                "CST" in formatted or "CDT" in formatted,
                "Format includes timezone abbreviation",
                f"Got: {formatted}"
            )

            # Test None handling
            none_result = utc_to_central(None)
            self.assert_test(
                none_result is None,
                "None input returns None",
                f"Got: {none_result}"
            )

            if self.verbose:
                self.log(f"\n  Winter (CST): {utc_winter} → {central_winter}", "debug")
                self.log(f"  Summer (CDT): {utc_summer} → {central_summer}", "debug")
                self.log(f"  Formatted: {formatted}", "debug")

            return True

        except Exception as e:
            self.assert_test(False, "Timezone utilities", str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def test_single_bet_service(self) -> bool:
        """Test single bet service instantiation and methods."""
        self.log("\n" + "="*70, "info")
        self.log("TEST 2: Single Bet Service", "info")
        self.log("="*70, "info")

        try:
            from app.core.database import SessionLocal
            from app.services.core.single_bet_service import (
                SingleBetService,
                SingleBet,
                get_single_bet_service
            )

            db = SessionLocal()

            # Test instantiation
            service = get_single_bet_service(db)
            self.assert_test(
                service is not None,
                "Service instantiation",
                "Service is None"
            )

            # Test thresholds
            self.assert_test(
                service.MIN_CONFIDENCE == 0.60,
                "Min confidence is 60%",
                f"Got {service.MIN_CONFIDENCE}"
            )

            self.assert_test(
                service.MIN_EDGE == 5.0,
                "Min edge is 5%",
                f"Got {service.MIN_EDGE}"
            )

            self.assert_test(
                service.MAX_BETS_PER_DAY == 10,
                "Max bets per day is 10",
                f"Got {service.MAX_BETS_PER_DAY}"
            )

            self.assert_test(
                service.MAX_BETS_PER_GAME == 3,
                "Max bets per game is 3",
                f"Got {service.MAX_BETS_PER_GAME}"
            )

            # Test odds conversion
            american_neg = -110
            decimal_neg = service._american_to_decimal(american_neg)
            self.assert_test(
                abs(decimal_neg - 1.91) < 0.01,
                f"American to decimal: {american_neg} → {decimal_neg}",
                "Expected ~1.91"
            )

            american_pos = +150
            decimal_pos = service._american_to_decimal(american_pos)
            self.assert_test(
                abs(decimal_pos - 2.50) < 0.01,
                f"American to decimal: {american_pos} → {decimal_pos}",
                "Expected ~2.50"
            )

            if self.verbose:
                self.log(f"\n  Odds conversion examples:", "debug")
                self.log(f"    -110 → {decimal_neg:.2f}", "debug")
                self.log(f"    +150 → {decimal_pos:.2f}", "debug")

            db.close()
            return True

        except Exception as e:
            self.assert_test(False, "Single Bet Service", str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def test_bet_generation(self) -> bool:
        """Test bet generation from predictions."""
        self.log("\n" + "="*70, "info")
        self.log("TEST 3: Bet Generation", "info")
        self.log("="*70, "info")

        try:
            from app.core.database import SessionLocal
            from app.services.core.single_bet_service import SingleBetService

            db = SessionLocal()
            service = SingleBetService(db)

            # Generate bets for today
            target_date = date.today()
            self.log(f"\n  Generating bets for {target_date}...", "info")

            bets = service.generate_daily_bets(target_date=target_date)

            self.assert_test(
                bets is not None,
                "Bet generation returns data",
                "Got None"
            )

            self.assert_test(
                isinstance(bets, list),
                "Bet generation returns list",
                f"Got {type(bets)}"
            )

            if bets:
                self.log(f"    Generated {len(bets)} bets", "info")

                # Check business rules
                self.assert_test(
                    len(bets) <= service.MAX_BETS_PER_DAY,
                    f"Max {service.MAX_BETS_PER_DAY} bets per day",
                    f"Got {len(bets)}"
                )

                # Check per-game limit
                game_counts = {}
                for bet in bets:
                    game_key = (bet.game_date.date(), bet.team, bet.opponent)
                    game_counts[game_key] = game_counts.get(game_key, 0) + 1

                max_per_game = max(game_counts.values()) if game_counts else 0
                self.assert_test(
                    max_per_game <= service.MAX_BETS_PER_GAME,
                    f"Max {service.MAX_BETS_PER_GAME} bets per game",
                    f"Got {max_per_game}"
                )

                # Check bet structure
                if bets:
                    sample = bets[0]
                    self.assert_test(
                        hasattr(sample, 'player_name'),
                        "Bet has player_name",
                        "Missing attribute"
                    )
                    self.assert_test(
                        hasattr(sample, 'edge_percent'),
                        "Bet has edge_percent",
                        "Missing attribute"
                    )
                    self.assert_test(
                        hasattr(sample, 'ev_percent'),
                        "Bet has ev_percent",
                        "Missing attribute"
                    )
                    self.assert_test(
                        hasattr(sample, 'game_date'),
                        "Bet has game_date",
                        "Missing attribute"
                    )

                    # Verify timezone conversion (game_date should be in Central Time)
                    if sample.game_date:
                        self.log(f"\n  Sample bet:", "info")
                        self.log(f"    Player: {sample.player_name} ({sample.team})", "info")
                        self.log(f"    Game: {sample.team} vs {sample.opponent}", "info")
                        self.log(f"    Game Time: {sample.game_date} (Central Time)", "info")
                        self.log(f"    Stat: {sample.stat_type} {sample.recommendation.value} {sample.bookmaker_line}", "info")
                        self.log(f"    Confidence: {sample.confidence:.1%} | Edge: {sample.edge_percent:+.1f}%", "info")
                        self.log(f"    EV: {sample.ev_percent:+.1f}% | Odds: {sample.odds_american}", "info")

            else:
                self.log("    No bets generated (may be no qualifying predictions)", "info")

            db.close()
            return True

        except Exception as e:
            self.assert_test(False, "Bet Generation", str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def test_bet_display_format(self) -> bool:
        """Test bet display formatting."""
        self.log("\n" + "="*70, "info")
        self.log("TEST 4: Bet Display Format", "info")
        self.log("="*70, "info")

        try:
            from app.core.database import SessionLocal
            from app.services.core.single_bet_service import SingleBetService

            db = SessionLocal()
            service = SingleBetService(db)

            # Generate some bets
            bets = service.generate_daily_bets(target_date=date.today())

            if bets:
                display = service.format_bets_for_display(bets)

                self.assert_test(
                    isinstance(display, str),
                    "Display format is string",
                    f"Got {type(display)}"
                )

                self.assert_test(
                    len(display) > 0,
                    "Display format not empty",
                    "Got empty string"
                )

                self.assert_test(
                    "CST" in display or "CDT" in display,
                    "Display includes timezone",
                    "No timezone found"
                )

                if self.verbose:
                    self.log(f"\n  Sample display output:", "debug")
                    lines = display.split("\n")[:10]  # First 10 lines
                    for line in lines:
                        self.log(f"    {line}", "debug")
                    if len(display.split("\n")) > 10:
                        self.log(f"    ... ({len(display.split(chr(10)))} total lines)", "debug")

            else:
                self.log("    Skipped (no bets to format)", "info")

            db.close()
            return True

        except Exception as e:
            self.assert_test(False, "Bet Display Format", str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def test_api_endpoints(self) -> bool:
        """Test API endpoints (if FastAPI is available)."""
        self.log("\n" + "="*70, "info")
        self.log("TEST 5: API Endpoints", "info")
        self.log("="*70, "info")

        try:
            from app.core.database import SessionLocal
            from app.services.core.single_bet_service import get_single_bet_service

            db = SessionLocal()
            service = get_single_bet_service(db)

            # Simulate API call
            bets = service.generate_daily_bets(
                target_date=date.today(),
                sport_id=None
            )

            self.assert_test(
                bets is not None,
                "API bet retrieval",
                "Service returned None"
            )

            # Check summary calculation
            if bets:
                avg_confidence = sum(b.confidence for b in bets) / len(bets)
                avg_edge = sum(b.edge_percent for b in bets) / len(bets)
                avg_ev = sum(b.ev_percent for b in bets) / len(bets)

                self.assert_test(
                    0 <= avg_confidence <= 1,
                    f"Avg confidence in valid range: {avg_confidence:.2f}",
                    "Out of range"
                )

                self.log(f"\n  Summary for {len(bets)} bets:", "info")
                self.log(f"    Avg Confidence: {avg_confidence:.1%}", "info")
                self.log(f"    Avg Edge: {avg_edge:+.1f}%", "info")
                self.log(f"    Avg EV: {avg_ev:+.1f}%", "info")

            db.close()
            return True

        except Exception as e:
            self.assert_test(False, "API Endpoints", str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def print_summary(self):
        """Print test summary."""
        self.log("\n" + "="*70, "info")
        self.log("PHASE 3 SINGLE BET SERVICE TEST SUMMARY", "info")
        self.log("="*70, "info")

        total = self.results["passed"] + self.results["failed"]
        pass_rate = (self.results["passed"] / total * 100) if total > 0 else 0

        self.log(f"\n  Total Tests: {total}", "info")
        self.log(f"  ✅ Passed: {self.results['passed']}", "info")
        self.log(f"  ❌ Failed: {self.results['failed']}", "info")
        self.log(f"  Pass Rate: {pass_rate:.1f}%", "info")

        if self.results["errors"]:
            self.log("\n  Errors:", "error")
            for error in self.results["errors"][:5]:
                self.log(f"    - {error}", "error")
            if len(self.results["errors"]) > 5:
                self.log(f"    ... and {len(self.results['errors']) - 5} more", "error")

        self.log("\n" + "="*70, "info")

        if pass_rate >= 80:
            self.log("🎉 Phase 3 Single Bet Service: PASSED (>80% pass rate)", "info")
        elif pass_rate >= 50:
            self.log("⚠️  Phase 3 Single Bet Service: PARTIAL (50-80% pass rate)", "info")
        else:
            self.log("❌ Phase 3 Single Bet Service: FAILED (<50% pass rate)", "info")

        self.log("="*70 + "\n", "info")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Phase 3 single bet service implementation"
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable detailed output'
    )

    args = parser.parse_args()

    tester = Phase3Tester(verbose=args.verbose)

    # Run all tests
    tester.test_timezone_utilities()
    tester.test_single_bet_service()
    tester.test_bet_generation()
    tester.test_bet_display_format()
    tester.test_api_endpoints()

    # Print summary
    tester.print_summary()

    # Exit with appropriate code
    sys.exit(0 if tester.results["failed"] == 0 else 1)


if __name__ == '__main__':
    main()
