"""Test prediction accuracy by comparing predictions to actual results.

This script provides comprehensive accuracy analysis:
1. Fetches all resolved predictions from prediction_tracking table
2. Calculates accuracy metrics across multiple dimensions
3. Generates detailed reports by confidence buckets, stat types, and edge magnitude
4. Identifies best and worst performing predictions
5. Computes statistical measures (MAE, confidence calibration)

Usage:
    python scripts/test_prediction_accuracy.py
    python scripts/test_prediction_accuracy.py --stat-type points
    python scripts/test_prediction_accuracy.py --min-confidence 0.80
    python scripts/test_prediction_accuracy.py --days-back 30
"""
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import statistics

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal


class AccuracyAnalyzer:
    """Analyzes prediction accuracy across multiple dimensions."""

    def __init__(self, db):
        self.db = db
        self.predictions = []
        self.metrics = {}

    def fetch_predictions(self, stat_type: Optional[str] = None, days_back: Optional[int] = None,
                         min_confidence: Optional[float] = None) -> List[Dict]:
        """Fetch resolved predictions from database.

        Args:
            stat_type: Filter by stat type (points, rebounds, assists, etc.)
            days_back: Only include predictions from last N days
            min_confidence: Minimum confidence threshold (0.0 to 1.0)

        Returns:
            List of prediction dictionaries
        """
        query = """
            SELECT
                id,
                game_id,
                game_date,
                away_team,
                home_team,
                player_name,
                player_team,
                stat_type,
                predicted_value,
                bookmaker_line,
                bookmaker,
                edge,
                recommendation,
                confidence,
                actual_value,
                is_correct,
                difference,
                prediction_generated_at,
                actual_resolved_at
            FROM prediction_tracking
            WHERE actual_resolved_at IS NOT NULL
              AND actual_value IS NOT NULL
              AND is_correct IS NOT NULL
        """

        conditions = []
        params = {}

        if stat_type:
            conditions.append("stat_type = :stat_type")
            params["stat_type"] = stat_type

        if days_back:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            conditions.append("game_date >= :cutoff_date")
            params["cutoff_date"] = cutoff_date

        if min_confidence:
            conditions.append("confidence >= :min_confidence")
            params["min_confidence"] = min_confidence

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += " ORDER BY game_date DESC, confidence DESC"

        result = self.db.execute(text(query), params)
        columns = result.keys()
        self.predictions = [dict(zip(columns, row)) for row in result.fetchall()]

        return self.predictions

    def calculate_overall_metrics(self) -> Dict:
        """Calculate overall accuracy metrics.

        Returns:
            Dictionary with overall statistics
        """
        if not self.predictions:
            return {}

        total = len(self.predictions)
        correct = sum(1 for p in self.predictions if p["is_correct"])
        incorrect = total - correct

        # Calculate Mean Absolute Error (MAE)
        mae_values = [abs(p["difference"]) for p in self.predictions if p["difference"] is not None]
        mae = statistics.mean(mae_values) if mae_values else 0

        # Calculate Mean Signed Error (bias)
        mse_values = [p["difference"] for p in self.predictions if p["difference"] is not None]
        mean_signed_error = statistics.mean(mse_values) if mse_values else 0

        # Average confidence
        avg_confidence = statistics.mean([p["confidence"] for p in self.predictions])

        # Average edge
        avg_edge = statistics.mean([p["edge"] for p in self.predictions if p["edge"] is not None])

        # Calibrated confidence (does confidence match actual accuracy?)
        confidence_buckets = self.get_confidence_buckets()
        calibration_error = 0
        if confidence_buckets:
            errors = []
            for bucket, data in confidence_buckets.items():
                predicted_acc = (bucket[0] + bucket[1]) / 2  # Midpoint of bucket
                actual_acc = data["accuracy_rate"]
                errors.append(abs(predicted_acc - actual_acc))
            calibration_error = statistics.mean(errors) if errors else 0

        return {
            "total_predictions": total,
            "correct": correct,
            "incorrect": incorrect,
            "accuracy_rate": correct / total if total > 0 else 0,
            "mean_absolute_error": mae,
            "mean_signed_error": mean_signed_error,
            "average_confidence": avg_confidence,
            "average_edge": avg_edge,
            "calibration_error": calibration_error,
        }

    def get_confidence_buckets(self) -> Dict[Tuple[float, float], Dict]:
        """Group predictions by confidence buckets.

        Returns:
            Dict mapping (min_conf, max_conf) to bucket statistics
        """
        buckets = {
            (0.50, 0.59): {"correct": 0, "total": 0, "accuracy_rate": 0},
            (0.60, 0.69): {"correct": 0, "total": 0, "accuracy_rate": 0},
            (0.70, 0.79): {"correct": 0, "total": 0, "accuracy_rate": 0},
            (0.80, 0.89): {"correct": 0, "total": 0, "accuracy_rate": 0},
            (0.90, 1.00): {"correct": 0, "total": 0, "accuracy_rate": 0},
        }

        for pred in self.predictions:
            conf = pred["confidence"]
            for (min_conf, max_conf), bucket in buckets.items():
                if min_conf <= conf < max_conf:
                    bucket["total"] += 1
                    if pred["is_correct"]:
                        bucket["correct"] += 1
                    break

        # Calculate accuracy rates
        for bucket_data in buckets.values():
            if bucket_data["total"] > 0:
                bucket_data["accuracy_rate"] = bucket_data["correct"] / bucket_data["total"]

        # Remove empty buckets
        return {k: v for k, v in buckets.items() if v["total"] > 0}

    def get_stat_type_metrics(self) -> Dict[str, Dict]:
        """Calculate accuracy metrics by stat type.

        Returns:
            Dict mapping stat_type to statistics
        """
        stats = defaultdict(lambda: {"correct": 0, "total": 0, "mae": []})

        for pred in self.predictions:
            stat = pred["stat_type"]
            stats[stat]["total"] += 1
            if pred["is_correct"]:
                stats[stat]["correct"] += 1
            if pred["difference"] is not None:
                stats[stat]["mae"].append(abs(pred["difference"]))

        # Calculate summary metrics
        result = {}
        for stat, data in stats.items():
            result[stat] = {
                "total": data["total"],
                "correct": data["correct"],
                "accuracy_rate": data["correct"] / data["total"] if data["total"] > 0 else 0,
                "mean_absolute_error": statistics.mean(data["mae"]) if data["mae"] else 0,
            }

        return result

    def get_edge_buckets(self) -> Dict[str, Dict]:
        """Group predictions by edge magnitude.

        Edge = predicted_value - bookmaker_line
        Larger edge = more value in the bet

        Returns:
            Dict mapping edge bucket to statistics
        """
        buckets = {
            "small (0-2%)": {"correct": 0, "total": 0, "accuracy_rate": 0},
            "medium (2-5%)": {"correct": 0, "total": 0, "accuracy_rate": 0},
            "large (5-10%)": {"correct": 0, "total": 0, "accuracy_rate": 0},
            "huge (10%+)": {"correct": 0, "total": 0, "accuracy_rate": 0},
        }

        for pred in self.predictions:
            edge = pred.get("edge")
            if edge is None:
                continue

            edge_pct = edge * 100  # Convert to percentage

            if edge_pct < 2:
                bucket = buckets["small (0-2%)"]
            elif edge_pct < 5:
                bucket = buckets["medium (2-5%)"]
            elif edge_pct < 10:
                bucket = buckets["large (5-10%)"]
            else:
                bucket = buckets["huge (10%+)"]

            bucket["total"] += 1
            if pred["is_correct"]:
                bucket["correct"] += 1

        # Calculate accuracy rates
        for bucket_data in buckets.values():
            if bucket_data["total"] > 0:
                bucket_data["accuracy_rate"] = bucket_data["correct"] / bucket_data["total"]

        return {k: v for k, v in buckets.items() if v["total"] > 0}

    def get_recommendation_metrics(self) -> Dict[str, Dict]:
        """Calculate accuracy by recommendation type (OVER/UNDER).

        Returns:
            Dict with OVER and UNDER statistics
        """
        recs = defaultdict(lambda: {"correct": 0, "total": 0, "mae": []})

        for pred in self.predictions:
            rec = pred["recommendation"]
            recs[rec]["total"] += 1
            if pred["is_correct"]:
                recs[rec]["correct"] += 1
            if pred["difference"] is not None:
                recs[rec]["mae"].append(abs(pred["difference"]))

        result = {}
        for rec, data in recs.items():
            result[rec] = {
                "total": data["total"],
                "correct": data["correct"],
                "accuracy_rate": data["correct"] / data["total"] if data["total"] > 0 else 0,
                "mean_absolute_error": statistics.mean(data["mae"]) if data["mae"] else 0,
            }

        return result

    def get_best_performers(self, n: int = 10) -> List[Dict]:
        """Get players with highest accuracy (minimum 5 predictions).

        Args:
            n: Number of players to return

        Returns:
            List of player performance dictionaries
        """
        player_stats = defaultdict(lambda: {"correct": 0, "total": 0, "mae": []})

        for pred in self.predictions:
            name = pred["player_name"]
            player_stats[name]["total"] += 1
            if pred["is_correct"]:
                player_stats[name]["correct"] += 1
            if pred["difference"] is not None:
                player_stats[name]["mae"].append(abs(pred["difference"]))

        # Filter to players with at least 5 predictions
        qualified = {k: v for k, v in player_stats.items() if v["total"] >= 5}

        # Sort by accuracy rate
        sorted_players = sorted(
            qualified.items(),
            key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=True
        )

        result = []
        for name, data in sorted_players[:n]:
            result.append({
                "player_name": name,
                "total_predictions": data["total"],
                "correct": data["correct"],
                "accuracy_rate": data["correct"] / data["total"],
                "mean_absolute_error": statistics.mean(data["mae"]) if data["mae"] else 0,
            })

        return result

    def get_worst_performers(self, n: int = 10) -> List[Dict]:
        """Get players with lowest accuracy (minimum 5 predictions).

        Args:
            n: Number of players to return

        Returns:
            List of player performance dictionaries
        """
        player_stats = defaultdict(lambda: {"correct": 0, "total": 0, "mae": []})

        for pred in self.predictions:
            name = pred["player_name"]
            player_stats[name]["total"] += 1
            if pred["is_correct"]:
                player_stats[name]["correct"] += 1
            if pred["difference"] is not None:
                player_stats[name]["mae"].append(abs(pred["difference"]))

        # Filter to players with at least 5 predictions
        qualified = {k: v for k, v in player_stats.items() if v["total"] >= 5}

        # Sort by accuracy rate (ascending for worst)
        sorted_players = sorted(
            qualified.items(),
            key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=False
        )

        result = []
        for name, data in sorted_players[:n]:
            result.append({
                "player_name": name,
                "total_predictions": data["total"],
                "correct": data["correct"],
                "accuracy_rate": data["correct"] / data["total"],
                "mean_absolute_error": statistics.mean(data["mae"]) if data["mae"] else 0,
            })

        return result

    def get_extreme_predictions(self, n: int = 5) -> Dict[str, List[Dict]]:
        """Get predictions with largest deviations from actual.

        Args:
            n: Number of predictions to return for each category

        Returns:
            Dict with 'overestimates' and 'underestimates'
        """
        # Sort by absolute difference
        with_diff = [p for p in self.predictions if p["difference"] is not None]
        sorted_by_diff = sorted(with_diff, key=lambda x: abs(x["difference"]), reverse=True)

        # Overestimates (predicted much higher than actual)
        overestimates = sorted(
            [p for p in with_diff if p["difference"] > 0],
            key=lambda x: x["difference"],
            reverse=True
        )[:n]

        # Underestimates (predicted much lower than actual)
        underestimates = sorted(
            [p for p in with_diff if p["difference"] < 0],
            key=lambda x: x["difference"]
        )[:n]

        return {
            "overestimates": overestimates,
            "underestimates": underestimates,
            "largest_errors": sorted_by_diff[:n],
        }

    def generate_report(self) -> str:
        """Generate comprehensive accuracy report.

        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("PREDICTION ACCURACY REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Overall metrics
        overall = self.calculate_overall_metrics()
        if not overall:
            lines.append("No predictions found matching criteria.")
            return "\n".join(lines)

        lines.append("OVERALL PERFORMANCE")
        lines.append("-" * 80)
        lines.append(f"Total Predictions:     {overall['total_predictions']:,}")
        lines.append(f"Correct:               {overall['correct']:,} ({overall['accuracy_rate']*100:.1f}%)")
        lines.append(f"Incorrect:             {overall['incorrect']:,} ({(1-overall['accuracy_rate'])*100:.1f}%)")
        lines.append(f"Mean Absolute Error:   {overall['mean_absolute_error']:.2f} points")
        lines.append(f"Mean Signed Error:     {overall['mean_signed_error']:+.2f} points (bias)")
        lines.append(f"Average Confidence:    {overall['average_confidence']*100:.1f}%")
        lines.append(f"Average Edge:          {overall['average_edge']*100:+.2f}%")
        lines.append(f"Calibration Error:     {overall['calibration_error']*100:.1f}% (lower is better)")
        lines.append("")

        # Confidence buckets
        lines.append("ACCURACY BY CONFIDENCE BUCKET")
        lines.append("-" * 80)
        conf_buckets = self.get_confidence_buckets()
        for (min_conf, max_conf), data in sorted(conf_buckets.items()):
            lines.append(f"{min_conf*100:.0f}%-{max_conf*100:.0f}%: {data['correct']}/{data['total']} ({data['accuracy_rate']*100:.1f}%)")
        lines.append("")

        # Stat type metrics
        lines.append("ACCURACY BY STAT TYPE")
        lines.append("-" * 80)
        stat_metrics = self.get_stat_type_metrics()
        for stat, data in sorted(stat_metrics.items(), key=lambda x: x[1]["total"], reverse=True):
            lines.append(f"{stat:15} {data['correct']:4}/{data['total']:4} ({data['accuracy_rate']*100:5.1f}%)  MAE: {data['mean_absolute_error']:.2f}")
        lines.append("")

        # Recommendation metrics
        lines.append("ACCURACY BY RECOMMENDATION TYPE")
        lines.append("-" * 80)
        rec_metrics = self.get_recommendation_metrics()
        for rec, data in rec_metrics.items():
            lines.append(f"{rec:6} {data['correct']:4}/{data['total']:4} ({data['accuracy_rate']*100:5.1f}%)  MAE: {data['mean_absolute_error']:.2f}")
        lines.append("")

        # Edge buckets
        lines.append("ACCURACY BY EDGE MAGNITUDE")
        lines.append("-" * 80)
        edge_buckets = self.get_edge_buckets()
        for bucket, data in edge_buckets.items():
            lines.append(f"{bucket:20} {data['correct']:4}/{data['total']:4} ({data['accuracy_rate']*100:5.1f}%)")
        lines.append("")

        # Best performers
        lines.append("TOP PERFORMING PLAYERS (min 5 predictions)")
        lines.append("-" * 80)
        best = self.get_best_performers(10)
        for i, player in enumerate(best, 1):
            lines.append(f"{i:2}. {player['player_name']:25} {player['correct']:3}/{player['total_predictions']:3} ({player['accuracy_rate']*100:5.1f}%)  MAE: {player['mean_absolute_error']:.2f}")
        lines.append("")

        # Worst performers
        lines.append("LOWEST PERFORMING PLAYERS (min 5 predictions)")
        lines.append("-" * 80)
        worst = self.get_worst_performers(10)
        for i, player in enumerate(worst, 1):
            lines.append(f"{i:2}. {player['player_name']:25} {player['correct']:3}/{player['total_predictions']:3} ({player['accuracy_rate']*100:5.1f}%)  MAE: {player['mean_absolute_error']:.2f}")
        lines.append("")

        # Extreme predictions
        extremes = self.get_extreme_predictions(5)

        lines.append("LARGEST OVERESTIMATES (predicted - actual)")
        lines.append("-" * 80)
        for pred in extremes["overestimates"]:
            lines.append(f"{pred['player_name']:25} {pred['stat_type']:8}: Pred {pred['predicted_value']:.1f} vs Actual {pred['actual_value']:.1f} (Diff: {pred['difference']:+.1f})")
        lines.append("")

        lines.append("LARGEST UNDERESTIMATES (predicted - actual)")
        lines.append("-" * 80)
        for pred in extremes["underestimates"]:
            lines.append(f"{pred['player_name']:25} {pred['stat_type']:8}: Pred {pred['predicted_value']:.1f} vs Actual {pred['actual_value']:.1f} (Diff: {pred['difference']:+.1f})")
        lines.append("")

        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)

        return "\n".join(lines)


def main():
    """Main entry point for accuracy testing."""
    parser = argparse.ArgumentParser(
        description="Test prediction accuracy with comprehensive metrics"
    )
    parser.add_argument(
        "--stat-type",
        type=str,
        help="Filter by stat type (points, rebounds, assists, etc.)"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        help="Minimum confidence threshold (0.0 to 1.0)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        help="Only include predictions from last N days"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save report to file instead of printing"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.min_confidence is not None and not 0 <= args.min_confidence <= 1:
        print("Error: min-confidence must be between 0 and 1")
        sys.exit(1)

    # Initialize analyzer
    db = SessionLocal()
    try:
        analyzer = AccuracyAnalyzer(db)

        # Fetch predictions with filters
        print("Fetching predictions...")
        if args.stat_type:
            print(f"  Filtering by stat_type: {args.stat_type}")
        if args.min_confidence:
            print(f"  Minimum confidence: {args.min_confidence*100:.0f}%")
        if args.days_back:
            print(f"  Last {args.days_back} days")

        analyzer.fetch_predictions(
            stat_type=args.stat_type,
            days_back=args.days_back,
            min_confidence=args.min_confidence
        )

        print(f"Found {len(analyzer.predictions)} resolved predictions")
        print()

        # Generate report
        if args.json:
            import json

            # Convert confidence bucket tuple keys to strings for JSON
            conf_buckets = analyzer.get_confidence_buckets()
            conf_buckets_serializable = {
                f"{min_conf*100:.0f}%-{max_conf*100:.0f}%": data
                for (min_conf, max_conf), data in conf_buckets.items()
            }

            report = {
                "overall": analyzer.calculate_overall_metrics(),
                "confidence_buckets": conf_buckets_serializable,
                "stat_type_metrics": analyzer.get_stat_type_metrics(),
                "recommendation_metrics": analyzer.get_recommendation_metrics(),
                "edge_buckets": analyzer.get_edge_buckets(),
                "best_performers": analyzer.get_best_performers(10),
                "worst_performers": analyzer.get_worst_performers(10),
                "extreme_predictions": analyzer.get_extreme_predictions(5),
            }
            output = json.dumps(report, indent=2, default=str)
        else:
            output = analyzer.generate_report()

        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"Report saved to: {args.output}")
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
