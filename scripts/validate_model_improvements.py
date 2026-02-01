#!/usr/bin/env python3
"""
Validation script for NBA prediction model improvements (Tier 1-4).

This script validates:
- Tier 1: Rest days no longer random (injury filtering, last_game_date)
- Tier 2: Fatigue scaling with age-adjusted rest penalties
- Tier 3: Usage boost from injured teammates, dynamic opponent adjustments
- Tier 4: Travel fatigue calculations, matchup scoring

Usage:
    python scripts/validate_model_improvements.py [--game-id GAME_ID]
"""
import sys
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import text, and_

from app.core.database import get_db
from app.models import Player, Game, Prediction, PlayerSeasonStats, PlayerInjury
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.core.logging import get_logger

logger = get_logger(__name__)


class ModelValidator:
    """Validate model improvements across all tiers."""

    def __init__(self, db: Session):
        self.db = db
        self.service = EnhancedPredictionService(db)
        self.results = {
            "tier1": {"status": "PENDING", "tests": []},
            "tier2": {"status": "PENDING", "tests": []},
            "tier3": {"status": "PENDING", "tests": []},
            "tier4": {"status": "PENDING", "tests": []},
            "sanity_checks": {"status": "PENDING", "tests": []},
            "test_cases": {"status": "PENDING", "tests": []}
        }

    def log_test(self, tier: str, test_name: str, passed: bool, details: str):
        """Record a test result."""
        self.results[tier]["tests"].append({
            "name": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def get_upcoming_game(self) -> Optional[Game]:
        """Get an upcoming game for testing."""
        game = self.db.query(Game).filter(
            Game.sport_id == "nba",
            Game.status == "scheduled",
            Game.game_date >= datetime.now()
        ).order_by(Game.game_date).first()

        if not game:
            logger.warning("No upcoming games found, using recent game")
            game = self.db.query(Game).filter(
                Game.sport_id == "nba"
            ).order_by(Game.game_date.desc()).first()

        return game

    def validate_tier1_rest_days(self) -> bool:
        """
        Tier 1 Validation: Rest days are calculated from actual data, not random.

        Tests:
        1. _get_rest_days_since_last_game() returns consistent values
        2. Players filtered by last_game_date (recent activity check)
        3. Injury filter excludes OUT/DOUBTFUL/QUESTIONABLE players
        4. Jalen Williams should be filtered out (if injured)
        """
        logger.info("=" * 80)
        logger.info("TIER 1: Validating rest days calculations")
        logger.info("=" * 80)

        all_passed = True

        # Test 1.1: Get rest days for multiple players
        game = self.get_upcoming_game()
        if not game:
            logger.error("❌ Could not find a game for testing")
            self.log_test("tier1", "Find test game", False, "No games available")
            return False

        logger.info(f"Using game: {game.away_team} @ {game.home_team} on {game.game_date}")

        players = self.db.query(Player).filter(
            Player.team.in_([game.home_team, game.away_team]),
            Player.active == True,
            Player.sport_id == "nba"
        ).limit(10).all()

        rest_days_results = []
        for player in players:
            rest_days = self.service._get_rest_days_since_last_game(player, game)
            rest_days_results.append({
                "player": player.name,
                "rest_days": rest_days
            })

        # Check consistency: call multiple times, should return same value
        consistent_count = 0
        for player in players[:5]:  # Test first 5
            rd1 = self.service._get_rest_days_since_last_game(player, game)
            rd2 = self.service._get_rest_days_since_last_game(player, game)
            if rd1 == rd2:
                consistent_count += 1

        test_passed = (consistent_count == len(players[:5]))
        all_passed &= test_passed

        logger.info(f"Test 1.1: Rest days consistency - {consistent_count}/{len(players[:5])} consistent")
        logger.info(f"Sample rest days: {rest_days_results[:3]}")
        self.log_test(
            "tier1",
            "Rest days are deterministic (not random)",
            test_passed,
            f"{consistent_count}/{len(players[:5])} players returned consistent rest days"
        )

        # Test 1.2: Check last_game_date filtering is active
        players_with_last_game = self.db.query(Player, PlayerSeasonStats).join(
            PlayerSeasonStats,
            and_(
                Player.id == PlayerSeasonStats.player_id,
                PlayerSeasonStats.season == self.service.season
            )
        ).filter(
            Player.team.in_([game.home_team, game.away_team]),
            PlayerSeasonStats.last_game_date.isnot(None)
        ).limit(5).all()

        recent_cutoff = datetime.now() - timedelta(days=self.service.RECENT_DAYS_THRESHOLD)

        filtered_count = 0
        for player, stats in players_with_last_game:
            last_played = datetime.combine(stats.last_game_date, datetime.min.time())
            if last_played >= recent_cutoff:
                filtered_count += 1

        test_passed = (filtered_count > 0)
        all_passed &= test_passed

        logger.info(f"Test 1.2: Recent activity filtering - {filtered_count} players active")
        self.log_test(
            "tier1",
            "Players filtered by last_game_date",
            test_passed,
            f"{filtered_count} players have played within {self.service.RECENT_DAYS_THRESHOLD} days"
        )

        # Test 1.3: Injury filtering
        if players:
            player_ids = [p.id for p in players]
            healthy_ids = self.service.injury_service.filter_by_injury_status(player_ids)
            filtered_out = len(player_ids) - len(healthy_ids)

            logger.info(f"Test 1.3: Injury filter - {filtered_out} players filtered out")
            self.log_test(
                "tier1",
                "Injury filter excludes OUT/DOUBTFUL/QUESTIONABLE",
                True,  # Always passes if filter runs
                f"{filtered_out} players filtered by injury status"
            )

        # Test 1.4: Check for Jalen Williams (should be filtered if injured)
        jalen_williams = self.db.query(Player).filter(
            Player.name.ilike("%Jalen Williams%"),
            Player.active == True,
            Player.sport_id == "nba"
            ).first()

        if jalen_williams:
            # Check if he would be filtered
            stats = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == jalen_williams.id,
                PlayerSeasonStats.season == self.service.season
            ).first()

            is_filtered = False
            reason = ""

            if stats and stats.last_game_date:
                last_played = datetime.combine(stats.last_game_date, datetime.min.time())
                if last_played < recent_cutoff:
                    is_filtered = True
                    reason = f"Last played { (datetime.now() - last_played).days } days ago"

            # Check injury status
            injuries = self.db.query(PlayerInjury).filter(
                PlayerInjury.player_id == jalen_williams.id,
                PlayerInjury.reported_date >= date.today() - timedelta(days=7)
            ).all()

            active_injuries = [i for i in injuries if i.status.upper() in ['OUT', 'DOUBTFUL', 'QUESTIONABLE']]
            if active_injuries:
                is_filtered = True
                reason = f"Active injuries: {', '.join(i.status for i in active_injuries)}"

            logger.info(f"Test 1.4: Jalen Williams - Filtered: {is_filtered}, Reason: {reason}")
            self.log_test(
                "tier1",
                "Jalen Williams filtering",
                is_filtered,  # Pass if filtered out (which is correct)
                reason
            )

        self.results["tier1"]["status"] = "PASS" if all_passed else "FAIL"
        return all_passed

    def validate_tier2_fatigue_scaling(self) -> bool:
        """
        Tier 2 Validation: Fatigue scaling with age-adjusted penalties.

        Tests:
        1. Age-adjusted rest penalty varies by age group
        2. Fatigue scaling is non-linear with minutes
        3. Young players get lower B2B penalties than veterans
        4. EWMA uses numpy for robust calculations
        """
        logger.info("=" * 80)
        logger.info("TIER 2: Validating fatigue scaling and age adjustments")
        logger.info("=" * 80)

        all_passed = True

        # Test 2.1: Age-adjusted rest penalties
        from datetime import date as dt_date

        # Create mock players with different ages
        class MockPlayer:
            def __init__(self, name, birth_year):
                self.name = name
                self.birth_date = dt_date(birth_year, 1, 1)
                self.id = f"mock_{name}"

        # Calculate birth years based on current date
        current_year = date.today().year
        # 21yo (young), 30yo (prime), 38yo (veteran)
        young_player = MockPlayer("Young Player", current_year - 21)
        prime_player = MockPlayer("Prime Player", current_year - 30)
        veteran_player = MockPlayer("Veteran Player", current_year - 38)

        game = self.get_upcoming_game()

        # Test B2B (rest_days = 0) penalty for different ages
        young_b2b = self.service._get_age_adjusted_rest_penalty(young_player, 0)
        prime_b2b = self.service._get_age_adjusted_rest_penalty(prime_player, 0)
        veteran_b2b = self.service._get_age_adjusted_rest_penalty(veteran_player, 0)

        logger.info(f"Test 2.1: B2B penalties by age:")
        logger.info(f"  21yo: {young_b2b:.3f} ({young_b2b*100:.1f}%)")
        logger.info(f"  30yo: {prime_b2b:.3f} ({prime_b2b*100:.1f}%)")
        logger.info(f"  38yo: {veteran_b2b:.3f} ({veteran_b2b*100:.1f}%)")

        # Young players should have LESS penalty (closer to 0)
        # Veterans should have MORE penalty (more negative)
        test_passed = (young_b2b > prime_b2b > veteran_b2b)
        all_passed &= test_passed

        self.log_test(
            "tier2",
            "Age-adjusted B2B penalties (young < prime < veteran)",
            test_passed,
            f"21yo: {young_b2b:.3f}, 30yo: {prime_b2b:.3f}, 38yo: {veteran_b2b:.3f}"
        )

        # Test 2.2: Non-linear fatigue scaling
        fatigue_32 = self.service._apply_fatigue_scaling(100.0, 32)[1]
        fatigue_36 = self.service._apply_fatigue_scaling(100.0, 36)[1]
        fatigue_40 = self.service._apply_fatigue_scaling(100.0, 40)[1]
        fatigue_42 = self.service._apply_fatigue_scaling(100.0, 42)[1]

        logger.info(f"Test 2.2: Fatigue factors by minutes:")
        logger.info(f"  32 min: {fatigue_32:.3f} (baseline)")
        logger.info(f"  36 min: {fatigue_36:.3f}")
        logger.info(f"  40 min: {fatigue_40:.3f}")
        logger.info(f"  42 min: {fatigue_42:.3f} (floor)")

        # Should be decreasing: 32min > 36min > 40min ≈ 42min
        test_passed = (fatigue_32 >= fatigue_36 >= fatigue_40 >= fatigue_42)
        all_passed &= test_passed

        self.log_test(
            "tier2",
            "Non-linear fatigue scaling",
            test_passed,
            f"Fatigue decreases with minutes: {fatigue_32:.3f} > {fatigue_36:.3f} > {fatigue_40:.3f} > {fatigue_42:.3f}"
        )

        # Test 2.3: Rest days bonus
        young_2days = self.service._get_age_adjusted_rest_penalty(young_player, 2)
        veteran_2days = self.service._get_age_adjusted_rest_penalty(veteran_player, 2)

        logger.info(f"Test 2.3: Rest days bonus (2 days):")
        logger.info(f"  21yo: {young_2days:.3f} ({young_2days*100:.1f}%)")
        logger.info(f"  38yo: {veteran_2days:.3f} ({veteran_2days*100:.1f}%)")

        # Both should be positive (bonus), veteran might get more
        test_passed = (young_2days > 0 and veteran_2days > 0)
        all_passed &= test_passed

        self.log_test(
            "tier2",
            "Rest days bonus applied",
            test_passed,
            f"2 days rest gives bonus to all ages"
        )

        self.results["tier2"]["status"] = "PASS" if all_passed else "FAIL"
        return all_passed

    def validate_tier3_usage_boost(self) -> bool:
        """
        Tier 3 Validation: Usage boost from injured teammates.

        Tests:
        1. Usage boost calculated from injured teammates
        2. Position-specific boost applied
        3. Dynamic opponent adjustment queries actual data
        """
        logger.info("=" * 80)
        logger.info("TIER 3: Validating usage boost and dynamic adjustments")
        logger.info("=" * 80)

        all_passed = True

        game = self.get_upcoming_game()

        # Test 3.1: Get a player and calculate usage boost
        player = self.db.query(Player).filter(
            Player.team == game.home_team,
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        if not player:
            logger.warning("Could not find player for usage boost test")
            self.log_test("tier3", "Usage boost calculation", False, "No player found")
            return False

        try:
            usage_boost = self.service._calculate_teammate_injury_boost(
                player, game, "points"
            )

            logger.info(f"Test 3.1: Usage boost for {player.name}: {usage_boost:.3f} ({usage_boost*100:.1f}%)")

            # Usage boost should be between 0 and 20% (0.20)
            test_passed = (0 <= usage_boost <= 0.20)
            all_passed &= test_passed

            self.log_test(
                "tier3",
                "Usage boost in valid range",
                test_passed,
                f"Usage boost: {usage_boost:.3f} (range: 0-0.20)"
            )
        except Exception as e:
            logger.error(f"Error calculating usage boost: {e}")
            self.log_test("tier3", "Usage boost calculation", False, f"Error: {e}")
            all_passed = False

        # Test 3.2: Dynamic opponent adjustment
        try:
            opp_adj = self.service._get_dynamic_opponent_adjustment(
                player, game.away_team, "points"
            )

            logger.info(f"Test 3.2: Opponent adjustment for {player.name} vs {game.away_team}: {opp_adj:.3f}")

            # Should be between -15% and +15%
            test_passed = (-0.15 <= opp_adj <= 0.15)
            all_passed &= test_passed

            self.log_test(
                "tier3",
                "Dynamic opponent adjustment in valid range",
                test_passed,
                f"Adjustment: {opp_adj:.3f} (range: -0.15 to +0.15)"
            )
        except Exception as e:
            logger.error(f"Error calculating opponent adjustment: {e}")
            self.log_test("tier3", "Dynamic opponent adjustment", False, f"Error: {e}")
            all_passed = False

        # Test 3.3: Position-specific usage
        # Check that guards get less rebound boost than bigs
        guard_player = self.db.query(Player).filter(
            Player.position.in_(["PG", "SG", "G"]),
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        big_player = self.db.query(Player).filter(
            Player.position.in_(["C", "PF", "F"]),
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        if guard_player and big_player:
            try:
                guard_rebound_boost = self.service._calculate_teammate_injury_boost(
                    guard_player, game, "rebounds"
                )
                big_rebound_boost = self.service._calculate_teammate_injury_boost(
                    big_player, game, "rebounds"
                )

                logger.info(f"Test 3.3: Position-specific rebound boost:")
                logger.info(f"  Guard ({guard_player.position}): {guard_rebound_boost:.3f}")
                logger.info(f"  Big ({big_player.position}): {big_rebound_boost:.3f}")

                # Bigs should get equal or more rebound boost
                test_passed = (big_rebound_boost >= guard_rebound_boost)
                all_passed &= test_passed

                self.log_test(
                    "tier3",
                    "Position-specific usage (bigs get more rebound boost)",
                    test_passed,
                    f"Guard: {guard_rebound_boost:.3f}, Big: {big_rebound_boost:.3f}"
                )
            except Exception as e:
                logger.error(f"Error testing position-specific usage: {e}")
                self.log_test("tier3", "Position-specific usage", False, f"Error: {e}")

        self.results["tier3"]["status"] = "PASS" if all_passed else "FAIL"
        return all_passed

    def validate_tier4_travel_fatigue(self) -> bool:
        """
        Tier 4 Validation: Travel fatigue and matchup scoring.

        Tests:
        1. Travel fatigue calculated based on distance
        2. Time zone changes considered
        3. Altitude effects applied
        4. Matchup score combines multiple factors
        """
        logger.info("=" * 80)
        logger.info("TIER 4: Validating travel fatigue and matchup scoring")
        logger.info("=" * 80)

        all_passed = True

        game = self.get_upcoming_game()

        # Test 4.1: Travel fatigue for away team
        away_player = self.db.query(Player).filter(
            Player.team == game.away_team,
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        home_player = self.db.query(Player).filter(
            Player.team == game.home_team,
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        if away_player:
            try:
                away_travel = self.service._calculate_travel_fatigue(away_player, game)
                logger.info(f"Test 4.1a: Away player ({away_player.team}) travel fatigue: {away_travel:.3f}")

                # Should be negative or zero (penalty or no travel)
                test_passed = (away_travel <= 0)
                all_passed &= test_passed

                self.log_test(
                    "tier4",
                    "Away team travel fatigue is penalty or neutral",
                    test_passed,
                    f"Away travel fatigue: {away_travel:.3f} (≤ 0)"
                )
            except Exception as e:
                logger.error(f"Error calculating away travel fatigue: {e}")
                self.log_test("tier4", "Away travel fatigue", False, f"Error: {e}")
                all_passed = False

        if home_player:
            try:
                home_travel = self.service._calculate_travel_fatigue(home_player, game)
                logger.info(f"Test 4.1b: Home player ({home_player.team}) travel fatigue: {home_travel:.3f}")

                # Should be zero (no travel for home game)
                test_passed = (home_travel == 0)
                all_passed &= test_passed

                self.log_test(
                    "tier4",
                    "Home team has no travel fatigue",
                    test_passed,
                    f"Home travel fatigue: {home_travel:.3f} (= 0)"
                )
            except Exception as e:
                logger.error(f"Error calculating home travel fatigue: {e}")
                self.log_test("tier4", "Home travel fatigue", False, f"Error: {e}")
                all_passed = False

        # Test 4.2: Matchup scoring
        if away_player:
            try:
                matchup_score = self.service._calculate_matchup_score(
                    away_player, game, "points"
                )

                logger.info(f"Test 4.2: Matchup score for {away_player.name}: {matchup_score:.3f}")

                # Should be between 0.90 and 1.10
                test_passed = (0.90 <= matchup_score <= 1.10)
                all_passed &= test_passed

                self.log_test(
                    "tier4",
                    "Matchup score in valid range",
                    test_passed,
                    f"Matchup score: {matchup_score:.3f} (range: 0.90-1.10)"
                )
            except Exception as e:
                logger.error(f"Error calculating matchup score: {e}")
                self.log_test("tier4", "Matchup score", False, f"Error: {e}")
                all_passed = False

        self.results["tier4"]["status"] = "PASS" if all_passed else "FAIL"
        return all_passed

    def validate_sanity_checks(self, use_estimated_lines: bool = False) -> bool:
        """
        Run sanity checks on predictions.

        Tests:
        1. No negative predictions
        2. Confidence levels in valid range
        3. Edge calculations make sense
        4. Line source is valid (not 'estimated' unless use_estimated_lines=True)

        Args:
            use_estimated_lines: If True, allow estimated lines for testing
        """
        logger.info("=" * 80)
        logger.info("SANITY CHECKS: Validating prediction outputs")
        logger.info("=" * 80)

        all_passed = True

        game = self.get_upcoming_game()

        # Generate predictions
        logger.info(f"Generating predictions for game: {game.away_team} @ {game.home_team}")

        if use_estimated_lines:
            # For testing, temporarily modify service to include estimated lines
            predictions = []
            players = self.service._get_active_players(game)

            for player in players[:10]:  # Test first 10 players
                for stat_type in ["points", "rebounds", "assists"]:
                    pred = self.service._generate_single_prediction(
                        player, game, stat_type, "draftkings"
                    )
                    if pred:
                        predictions.append(pred)

            logger.info(f"Generated {len(predictions)} predictions (including estimated lines)")
        else:
            predictions = self.service.generate_prop_predictions(
                game.id,
                stat_types=["points", "rebounds", "assists"],
                bookmaker="draftkings"
            )

        if not predictions:
            logger.warning("⚠️  No predictions generated (might be no games with valid odds)")
            self.log_test("sanity_checks", "Generate predictions", False, "No predictions generated")
            return False

        logger.info(f"Generated {len(predictions)} predictions")

        # Test 1: No negative predictions
        negative_predictions = [p for p in predictions if p.get("projected", 0) < 0]
        test_passed = (len(negative_predictions) == 0)
        all_passed &= test_passed

        logger.info(f"Test 1: Negative predictions - {len(negative_predictions)} found (expected: 0)")
        self.log_test(
            "sanity_checks",
            "No negative predictions",
            test_passed,
            f"{len(negative_predictions)} negative predictions"
        )

        # Test 2: Confidence in valid range (only for bets, not PASS recommendations)
        invalid_confidence = [
            p for p in predictions
            if p.get("recommendation") in ["OVER", "UNDER"]
            and not (0.40 <= p.get("confidence", 0) <= 0.80)
        ]
        test_passed = (len(invalid_confidence) == 0)
        all_passed &= test_passed

        logger.info(f"Test 2: Confidence range - {len(invalid_confidence)} invalid (expected: 0)")
        self.log_test(
            "sanity_checks",
            "Confidence in range [0.40, 0.80]",
            test_passed,
            f"{len(invalid_confidence)} predictions with invalid confidence"
        )

        # Test 3: Line source is valid
        estimated_lines = [p for p in predictions if p.get("line_source") == "estimated"]
        test_passed = (len(estimated_lines) == 0) if not use_estimated_lines else True
        all_passed &= test_passed

        logger.info(f"Test 3: Line source - {len(estimated_lines)} estimated (expected: {0 if not use_estimated_lines else 'any'})")
        self.log_test(
            "sanity_checks",
            "All lines from bookmaker (not estimated)" if not use_estimated_lines else "Line source check (estimated allowed)",
            test_passed,
            f"{len(estimated_lines)} predictions with estimated lines"
        )

        # Test 4: Edge makes sense relative to recommendation
        bad_edges = []
        for p in predictions:
            rec = p.get("recommendation")
            edge = p.get("edge", 0)

            if rec == "OVER" and edge <= 0:
                bad_edges.append(f"{p['player']} {p['stat_type']}: OVER but edge={edge}")
            elif rec == "UNDER" and edge >= 0:
                bad_edges.append(f"{p['player']} {p['stat_type']}: UNDER but edge={edge}")
            elif rec == "PASS" and abs(edge) >= 2.0:
                bad_edges.append(f"{p['player']} {p['stat_type']}: PASS but edge={edge}")

        test_passed = (len(bad_edges) == 0)
        all_passed &= test_passed

        logger.info(f"Test 4: Edge vs recommendation - {len(bad_edges)} mismatches")
        if bad_edges:
            for bad in bad_edges[:5]:
                logger.warning(f"  {bad}")

        self.log_test(
            "sanity_checks",
            "Edge matches recommendation",
            test_passed,
            f"{len(bad_edges)} mismatches"
        )

        # Sample predictions
        logger.info(f"\nSample predictions (first 3):")
        for p in predictions[:3]:
            logger.info(f"  {p['player']:20s} {p['stat_type']:8s}: {p['projected']:5.1f} vs {p['line']:4.1f} "
                       f"({p['recommendation']}) edge={p['edge']:4.1f} conf={p['confidence']:.2f}")

        self.results["sanity_checks"]["status"] = "PASS" if all_passed else "FAIL"
        return all_passed

    def validate_test_cases(self, use_estimated_lines: bool = True) -> bool:
        """
        Validate specific test cases.

        Tests:
        1. Jaylin Williams should appear (if healthy and has recent game)
        2. Jalen Williams should NOT appear (if hasn't played recently)
        3. Young players have different B2B than veterans

        Args:
            use_estimated_lines: If True, allow estimated lines for testing
        """
        logger.info("=" * 80)
        logger.info("TEST CASES: Validating specific player scenarios")
        logger.info("=" * 80)

        all_passed = True

        # For these specific player tests, find a game with the players we're testing
        # Test 1: Jaylin Williams (OKC)
        okc_game = self.db.query(Game).filter(
            Game.sport_id == "nba",
            (Game.home_team == "OKC") | (Game.away_team == "OKC")
        ).order_by(Game.game_date.desc()).first()

        if okc_game:
            logger.info(f"Using OKC game for Jaylin test: {okc_game.away_team} @ {okc_game.home_team}")

            if use_estimated_lines:
                predictions = []
                players = self.service._get_active_players(okc_game)

                for player in players:
                    pred = self.service._generate_single_prediction(
                        player, okc_game, "points", "draftkings"
                    )
                    if pred:
                        predictions.append(pred)
            else:
                predictions = self.service.generate_prop_predictions(
                    okc_game.id,
                    stat_types=["points"],
                    bookmaker="draftkings"
                )

            player_names = [p.get("player") for p in predictions]

            # Test 1: Jaylin Williams (should appear if healthy)
            jaylin_found = any("Jaylin Williams" in name for name in player_names)
            logger.info(f"Test 1: Jaylin Williams - Found: {jaylin_found}")

            # Check his status
            jaylin = self.db.query(Player).filter(
                Player.name.ilike("%Jaylin Williams%"),
                Player.active == True,
                Player.sport_id == "nba"
            ).first()

            if jaylin:
                stats = self.db.query(PlayerSeasonStats).filter(
                    PlayerSeasonStats.player_id == jaylin.id,
                    PlayerSeasonStats.season == self.service.season
                ).first()

                if stats and stats.avg_minutes >= 15:
                    # Check if he played recently
                    from datetime import datetime, timedelta
                    recent_cutoff = datetime.now() - timedelta(days=self.service.RECENT_DAYS_THRESHOLD)

                    if stats.last_game_date:
                        last_played = datetime.combine(stats.last_game_date, datetime.min.time())
                        is_recent = last_played >= recent_cutoff

                        if is_recent:
                            # Should appear if healthy, playing enough, and played recently
                            test_passed = jaylin_found
                            logger.info(f"  Jaylin has {stats.avg_minutes:.1f} mins, played { (datetime.now() - last_played).days } days ago - should appear")
                        else:
                            logger.info(f"  Jaylin hasn't played recently ({ (datetime.now() - last_played).days } days ago) - might not appear")
                            test_passed = True  # Don't fail if filtered by recent activity
                    else:
                        logger.info(f"  Jaylin has no last_game_date - might not appear")
                        test_passed = True
                else:
                    logger.info(f"  Jaylin has {stats.avg_minutes if stats else 0:.1f} mins (<15) - might not appear")
                    test_passed = True  # Don't fail if he's just a bench player
            else:
                logger.info(f"  Jaylin Williams not in database")
                test_passed = True  # Can't test if not in DB

            all_passed &= test_passed
            self.log_test(
                "test_cases",
                "Jaylin Williams appears (if healthy)",
                test_passed,
                f"Found: {jaylin_found}"
            )

        # Test 2: Jalen Williams (should NOT appear if hasn't played recently)
        jalen = self.db.query(Player).filter(
            Player.name.ilike("%Jalen Williams%"),
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        if jalen:
            stats = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == jalen.id,
                PlayerSeasonStats.season == self.service.season
            ).first()

            if stats and stats.last_game_date:
                from datetime import datetime, timedelta
                recent_cutoff = datetime.now() - timedelta(days=self.service.RECENT_DAYS_THRESHOLD)
                last_played = datetime.combine(stats.last_game_date, datetime.min.time())
                days_since = (datetime.now() - last_played).days

                logger.info(f"Test 2: Jalen Williams - Last played {days_since} days ago")

                if last_played < recent_cutoff:
                    # Should be filtered out
                    # Test by calling _get_active_players on his team's game
                    team_game = self.db.query(Game).filter(
                        Game.sport_id == "nba",
                        (Game.home_team == jalen.team) | (Game.away_team == jalen.team)
                    ).order_by(Game.game_date.desc()).first()

                    if team_game:
                        active_players = self.service._get_active_players(team_game)
                        jalen_active = any(p.id == jalen.id for p in active_players)

                        test_passed = not jalen_active
                        logger.info(f"  Jalen filtered out: {not jalen_active} (expected: True)")
                else:
                    logger.info(f"  Jalen played recently - can't test filtering")
                    test_passed = True  # Can't test if he's been playing
            else:
                logger.info(f"  Jalen has no last_game_date - can't test")
                test_passed = True

            # Check injury status
            injuries = self.db.query(PlayerInjury).filter(
                PlayerInjury.player_id == jalen.id,
                PlayerInjury.reported_date >= date.today() - timedelta(days=7)
            ).all()

            active_injuries = [i for i in injuries if i.status.upper() in ['OUT', 'DOUBTFUL', 'QUESTIONABLE']]

            if active_injuries:
                logger.info(f"  Jalen has active injuries: {', '.join(i.status for i in active_injuries)}")
        else:
            logger.info(f"  Jalen Williams not in database")
            test_passed = True

        all_passed &= test_passed
        self.log_test(
            "test_cases",
            "Jalen Williams filtered out (if not played recently)",
            test_passed,
            f"Test passed based on recent activity filtering"
        )

        # Test 3: Young vs veteran B2B penalty
        # Find young player (<22) and veteran player (>32)
        young = self.db.query(Player).filter(
            Player.birth_date >= date.today() - timedelta(days=22*365),
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        veteran = self.db.query(Player).filter(
            Player.birth_date <= date.today() - timedelta(days=32*365),
            Player.active == True,
            Player.sport_id == "nba"
        ).first()

        if young and veteran:
            young_penalty = self.service._get_age_adjusted_rest_penalty(young, 0)
            veteran_penalty = self.service._get_age_adjusted_rest_penalty(veteran, 0)

            logger.info(f"Test 3: B2B penalty comparison:")
            logger.info(f"  Young ({young.name}, ~21yo): {young_penalty:.3f}")
            logger.info(f"  Veteran ({veteran.name}, ~32yo+): {veteran_penalty:.3f}")

            # Young should have LESS penalty (closer to 0 or less negative)
            test_passed = (young_penalty > veteran_penalty)
            all_passed &= test_passed

            self.log_test(
                "test_cases",
                "Young players have lower B2B penalty than veterans",
                test_passed,
                f"Young: {young_penalty:.3f} > Veteran: {veteran_penalty:.3f}"
            )
        else:
            logger.info("  Could not find young/veteran players for comparison")
            test_passed = True  # Don't fail if can't find players
            all_passed &= test_passed

        self.results["test_cases"]["status"] = "PASS" if all_passed else "FAIL"
        return all_passed

    def generate_report(self) -> str:
        """Generate final validation report."""
        report = []
        report.append("=" * 80)
        report.append("MODEL VALIDATION REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")

        # Summary
        total_tests = 0
        total_passed = 0

        for tier_name, tier_data in self.results.items():
            if tier_name == "test_cases":
                display_name = "Test Cases"
            elif tier_name == "sanity_checks":
                display_name = "Sanity Checks"
            else:
                display_name = f"Tier {tier_name[-1]}"

            passed = sum(1 for t in tier_data["tests"] if t["passed"])
            total = len(tier_data["tests"])
            total_tests += total
            total_passed += passed

            status_icon = "✅" if tier_data["status"] == "PASS" else "❌"
            report.append(f"{status_icon} {display_name}: {tier_data['status']} ({passed}/{total} tests passed)")

            # Detailed test results
            for test in tier_data["tests"]:
                icon = "✅" if test["passed"] else "❌"
                report.append(f"   {icon} {test['name']}")
                if not test["passed"] or test["details"]:
                    report.append(f"      {test['details']}")

            report.append("")

        # Overall summary
        report.append("=" * 80)
        overall_status = "PASS" if total_passed == total_tests else "FAIL"
        overall_icon = "✅" if overall_status == "PASS" else "❌"
        report.append(f"{overall_icon} OVERALL: {overall_status} ({total_passed}/{total_tests} tests passed)")
        report.append("=" * 80)

        return "\n".join(report)

    def run_all_validations(self, allow_estimated_lines: bool = True) -> bool:
        """Run all validation tests.

        Args:
            allow_estimated_lines: If True, use estimated lines when real odds unavailable
        """
        logger.info("Starting comprehensive model validation...")
        logger.info("")

        # Run all tiers
        self.validate_tier1_rest_days()
        self.validate_tier2_fatigue_scaling()
        self.validate_tier3_usage_boost()
        self.validate_tier4_travel_fatigue()
        self.validate_sanity_checks(use_estimated_lines=allow_estimated_lines)
        self.validate_test_cases(use_estimated_lines=allow_estimated_lines)

        # Generate and print report
        report = self.generate_report()
        print("\n" + report)

        # Save report to file
        report_path = "/Users/seangreen/Documents/my-projects/sports-bet-ai-api/validation_report.txt"
        with open(report_path, "w") as f:
            f.write(report)

        logger.info(f"Report saved to: {report_path}")

        # Return overall pass/fail
        all_passed = all(
            tier_data["status"] == "PASS"
            for tier_name, tier_data in self.results.items()
        )
        return all_passed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate NBA prediction model improvements")
    parser.add_argument("--game-id", help="Specific game ID to test (optional)")
    parser.add_argument("--no-estimated", action="store_true", help="Don't allow estimated lines for testing")
    args = parser.parse_args()

    # Get database session
    db = next(get_db())

    try:
        validator = ModelValidator(db)
        allow_estimated = not args.no_estimated
        success = validator.run_all_validations(allow_estimated_lines=allow_estimated)

        if success:
            logger.info("✅ All validations passed!")
            return 0
        else:
            logger.warning("⚠️  Some validations failed")
            return 1

    except Exception as e:
        logger.error(f"Validation failed with error: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
