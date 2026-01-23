"""
Accuracy Calculation Service

Calculates prediction accuracy metrics including:
- MAE (Mean Absolute Error): Average absolute difference between predicted and actual
- RMSE (Root Mean Square Error): Square root of average squared differences
- Win Rate: Percentage of OVER/UNDER recommendations that were correct
- Model Drift Detection: Compares recent performance to baseline
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case, literal_column, cast, Date, extract

from app.models.nba.models import Prediction, Player, Game

logger = logging.getLogger(__name__)


class AccuracyService:
    """
    Service for calculating prediction accuracy metrics.

    Metrics calculated:
    - MAE (Mean Absolute Error): avg(|predicted - actual|)
    - RMSE (Root Mean Square Error): sqrt(avg((predicted - actual)^2))
    - Win Rate: correct_recommendations / total_recommendations
    """

    def __init__(self, db: Session):
        """
        Initialize the accuracy service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def calculate_overall_metrics(
        self,
        model_version: Optional[str] = None,
        days_back: int = 30
    ) -> Dict:
        """
        Calculate overall accuracy metrics across all stat types.

        Args:
            model_version: Filter by model version (None = all versions)
            days_back: Only include predictions from last N days

        Returns:
            Dictionary with metrics:
            - total_predictions: Total number of predictions
            - resolved_count: Number of resolved predictions
            - unresolved_count: Number of unresolved predictions
            - mae: Mean Absolute Error
            - rmse: Root Mean Square Error
            - win_rate: Percentage of correct recommendations (0-1)
            - over_count: Number of OVER recommendations
            - under_count: Number of UNDER recommendations
            - correct_over: Correct OVER recommendations
            - correct_under: Correct UNDER recommendations
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Base query - resolved predictions within date range
        base_query = self.db.query(Prediction).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.created_at >= cutoff
        )

        # Apply model version filter if specified
        if model_version:
            base_query = base_query.filter(Prediction.model_version == model_version)

        # Total counts
        total_predictions = base_query.count()
        unresolved_count = self.db.query(Prediction).filter(
            Prediction.actuals_resolved_at.is_(None),
            Prediction.created_at >= cutoff
        ).count()
        if model_version:
            unresolved_count = self.db.query(Prediction).filter(
                Prediction.actuals_resolved_at.is_(None),
                Prediction.created_at >= cutoff,
                Prediction.model_version == model_version
            ).count()

        # MAE calculation
        mae_result = base_query.with_entities(
            func.avg(func.abs(Prediction.predicted_value - Prediction.actual_value))
        ).scalar()
        mae = float(mae_result) if mae_result is not None else 0.0

        # RMSE calculation
        rmse_result = base_query.with_entities(
            func.sqrt(
                func.avg(
                    func.pow(Prediction.predicted_value - Prediction.actual_value, 2)
                )
            )
        ).scalar()
        rmse = float(rmse_result) if rmse_result is not None else 0.0

        # Win rate calculation
        # Count correct recommendations (OVER/UNDER that were correct)
        total_recommendations = base_query.filter(
            Prediction.recommendation.in_(["OVER", "UNDER"])
        ).count()

        correct_count = base_query.filter(
            Prediction.recommendation.in_(["OVER", "UNDER"]),
            Prediction.was_correct == True
        ).count()

        win_rate = correct_count / total_recommendations if total_recommendations > 0 else 0.0

        # Breakdown by recommendation type
        over_count = base_query.filter(Prediction.recommendation == "OVER").count()
        under_count = base_query.filter(Prediction.recommendation == "UNDER").count()

        correct_over = base_query.filter(
            Prediction.recommendation == "OVER",
            Prediction.was_correct == True
        ).count()

        correct_under = base_query.filter(
            Prediction.recommendation == "UNDER",
            Prediction.was_correct == True
        ).count()

        return {
            "model_version": model_version,
            "days_back": days_back,
            "total_predictions": total_predictions,
            "resolved_count": total_predictions,
            "unresolved_count": unresolved_count,
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "win_rate": round(win_rate, 3),
            "recommendation_breakdown": {
                "over": {
                    "total": over_count,
                    "correct": correct_over,
                    "win_rate": round(correct_over / over_count, 3) if over_count > 0 else 0.0
                },
                "under": {
                    "total": under_count,
                    "correct": correct_under,
                    "win_rate": round(correct_under / under_count, 3) if under_count > 0 else 0.0
                }
            }
        }

    def calculate_metrics_by_stat_type(
        self,
        model_version: Optional[str] = None,
        days_back: int = 30
    ) -> List[Dict]:
        """
        Calculate accuracy metrics broken down by stat type.

        Args:
            model_version: Filter by model version (None = all versions)
            days_back: Only include predictions from last N days

        Returns:
            List of dictionaries, one per stat type, with metrics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Group by stat_type
        query = self.db.query(
            Prediction.stat_type,
            func.count(Prediction.id).label('total'),
            func.avg(func.abs(Prediction.predicted_value - Prediction.actual_value)).label('mae'),
            func.sqrt(
                func.avg(
                    func.pow(Prediction.predicted_value - Prediction.actual_value, 2)
                )
            ).label('rmse')
        ).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.created_at >= cutoff
        )

        if model_version:
            query = query.filter(Prediction.model_version == model_version)

        results = query.group_by(Prediction.stat_type).all()

        stat_metrics = []
        for stat_type, total, mae, rmse in results:
            # Win rate for this stat type
            total_recs = self.db.query(Prediction).filter(
                Prediction.stat_type == stat_type,
                Prediction.recommendation.in_(["OVER", "UNDER"]),
                Prediction.actuals_resolved_at.isnot(None),
                Prediction.created_at >= cutoff
            )
            if model_version:
                total_recs = total_recs.filter(Prediction.model_version == model_version)

            total_rec_count = total_recs.count()

            correct_recs = self.db.query(Prediction).filter(
                Prediction.stat_type == stat_type,
                Prediction.recommendation.in_(["OVER", "UNDER"]),
                Prediction.was_correct == True,
                Prediction.actuals_resolved_at.isnot(None),
                Prediction.created_at >= cutoff
            )
            if model_version:
                correct_recs = correct_recs.filter(Prediction.model_version == model_version)

            correct_count = correct_recs.count()

            win_rate = correct_count / total_rec_count if total_rec_count > 0 else 0.0

            stat_metrics.append({
                "stat_type": stat_type,
                "total_predictions": total,
                "mae": round(float(mae), 2) if mae else 0.0,
                "rmse": round(float(rmse), 2) if rmse else 0.0,
                "win_rate": round(win_rate, 3)
            })

        # Sort by stat_type
        stat_metrics.sort(key=lambda x: x["stat_type"])

        return stat_metrics

    def get_accuracy_timeline(
        self,
        model_version: Optional[str] = None,
        days_back: int = 30,
        window_days: int = 1
    ) -> List[Dict]:
        """
        Get accuracy metrics over time for drift detection.

        Args:
            model_version: Filter by model version (None = all versions)
            days_back: Total time period to analyze
            window_days: Size of each time window (default: 1 day)

        Returns:
            List of time-ordered dictionaries with metrics for each window
        """
        timeline = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Calculate number of windows
        num_windows = days_back // window_days
        if days_back % window_days != 0:
            num_windows += 1

        for i in range(num_windows):
            window_start = cutoff + timedelta(days=i * window_days)
            window_end = window_start + timedelta(days=window_days)

            # Query for this window
            base_query = self.db.query(Prediction).filter(
                Prediction.actuals_resolved_at.isnot(None),
                Prediction.created_at >= window_start,
                Prediction.created_at < window_end
            )

            if model_version:
                base_query = base_query.filter(Prediction.model_version == model_version)

            total = base_query.count()

            if total == 0:
                continue

            # MAE
            mae_result = base_query.with_entities(
                func.avg(func.abs(Prediction.predicted_value - Prediction.actual_value))
            ).scalar()
            mae = float(mae_result) if mae_result else 0.0

            # RMSE
            rmse_result = base_query.with_entities(
                func.sqrt(
                    func.avg(
                        func.pow(Prediction.predicted_value - Prediction.actual_value, 2)
                    )
                )
            ).scalar()
            rmse = float(rmse_result) if rmse_result else 0.0

            # Win rate
            total_recs = base_query.filter(
                Prediction.recommendation.in_(["OVER", "UNDER"])
            ).count()

            correct_recs = base_query.filter(
                Prediction.recommendation.in_(["OVER", "UNDER"]),
                Prediction.was_correct == True
            ).count()

            win_rate = correct_recs / total_recs if total_recs > 0 else 0.0

            timeline.append({
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "total_predictions": total,
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "win_rate": round(win_rate, 3)
            })

        return timeline

    def detect_model_drift(
        self,
        model_version: Optional[str] = None,
        baseline_days: int = 30,
        recent_days: int = 7,
        threshold: float = 0.10
    ) -> Dict:
        """
        Detect if model performance has degraded (drift detection).

        Compares recent performance to baseline and alerts if degradation
        exceeds the threshold percentage.

        Args:
            model_version: Filter by model version (None = all versions)
            baseline_days: Size of baseline window (default: 30 days)
            recent_days: Size of recent window (default: 7 days)
            threshold: Degradation threshold as percentage (default: 10%)

        Returns:
            Dictionary with drift detection results:
            - drift_detected: Boolean indicating if drift was detected
            - baseline_metrics: Metrics from baseline period
            - recent_metrics: Metrics from recent period
            - changes: Percentage changes for each metric
            - alerts: List of alert messages if drift detected
        """
        # Calculate baseline metrics
        baseline_cutoff = datetime.now(timezone.utc) - timedelta(days=baseline_days)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)

        # Baseline period
        baseline_query = self.db.query(Prediction).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.created_at >= baseline_cutoff,
            Prediction.created_at >= datetime.now(timezone.utc) - timedelta(days=baseline_days + recent_days),
            Prediction.created_at < recent_cutoff
        )

        if model_version:
            baseline_query = baseline_query.filter(Prediction.model_version == model_version)

        # Recent period
        recent_query = self.db.query(Prediction).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.created_at >= recent_cutoff
        )

        if model_version:
            recent_query = recent_query.filter(Prediction.model_version == model_version)

        # Calculate baseline metrics
        baseline_mae = baseline_query.with_entities(
            func.avg(func.abs(Prediction.predicted_value - Prediction.actual_value))
        ).scalar()
        baseline_mae = float(baseline_mae) if baseline_mae else 0.0

        baseline_rmse = baseline_query.with_entities(
            func.sqrt(
                func.avg(
                    func.pow(Prediction.predicted_value - Prediction.actual_value, 2)
                )
            )
        ).scalar()
        baseline_rmse = float(baseline_rmse) if baseline_rmse else 0.0

        baseline_total_recs = baseline_query.filter(
            Prediction.recommendation.in_(["OVER", "UNDER"])
        ).count()

        baseline_correct = baseline_query.filter(
            Prediction.recommendation.in_(["OVER", "UNDER"]),
            Prediction.was_correct == True
        ).count()

        baseline_win_rate = baseline_correct / baseline_total_recs if baseline_total_recs > 0 else 0.0

        # Calculate recent metrics
        recent_mae = recent_query.with_entities(
            func.avg(func.abs(Prediction.predicted_value - Prediction.actual_value))
        ).scalar()
        recent_mae = float(recent_mae) if recent_mae else 0.0

        recent_rmse = recent_query.with_entities(
            func.sqrt(
                func.avg(
                    func.pow(Prediction.predicted_value - Prediction.actual_value, 2)
                )
            )
        ).scalar()
        recent_rmse = float(recent_rmse) if recent_rmse else 0.0

        recent_total_recs = recent_query.filter(
            Prediction.recommendation.in_(["OVER", "UNDER"])
        ).count()

        recent_correct = recent_query.filter(
            Prediction.recommendation.in_(["OVER", "UNDER"]),
            Prediction.was_correct == True
        ).count()

        recent_win_rate = recent_correct / recent_total_recs if recent_total_recs > 0 else 0.0

        # Calculate changes
        # For MAE/RMSE: increase is bad (positive change = degradation)
        # For win rate: decrease is bad (negative change = degradation)
        mae_change = (recent_mae - baseline_mae) / baseline_mae if baseline_mae > 0 else 0
        rmse_change = (recent_rmse - baseline_rmse) / baseline_rmse if baseline_rmse > 0 else 0
        win_rate_change = (recent_win_rate - baseline_win_rate) / baseline_win_rate if baseline_win_rate > 0 else 0

        # Detect drift
        alerts = []
        drift_detected = False

        if mae_change > threshold:
            drift_detected = True
            alerts.append(
                f"MAE increased by {mae_change * 100:.1f}% "
                f"(baseline: {baseline_mae:.2f}, recent: {recent_mae:.2f})"
            )

        if rmse_change > threshold:
            drift_detected = True
            alerts.append(
                f"RMSE increased by {rmse_change * 100:.1f}% "
                f"(baseline: {baseline_rmse:.2f}, recent: {recent_rmse:.2f})"
            )

        if win_rate_change < -threshold:
            drift_detected = True
            alerts.append(
                f"Win rate decreased by {abs(win_rate_change) * 100:.1f}% "
                f"(baseline: {baseline_win_rate:.3f}, recent: {recent_win_rate:.3f})"
            )

        return {
            "model_version": model_version,
            "drift_detected": drift_detected,
            "threshold": threshold,
            "baseline": {
                "days": baseline_days,
                "mae": round(baseline_mae, 2),
                "rmse": round(baseline_rmse, 2),
                "win_rate": round(baseline_win_rate, 3)
            },
            "recent": {
                "days": recent_days,
                "mae": round(recent_mae, 2),
                "rmse": round(recent_rmse, 2),
                "win_rate": round(recent_win_rate, 3)
            },
            "changes": {
                "mae_pct": round(mae_change * 100, 1),
                "rmse_pct": round(rmse_change * 100, 1),
                "win_rate_pct": round(win_rate_change * 100, 1)
            },
            "alerts": alerts
        }

    def get_best_and_worst_predictions(
        self,
        model_version: Optional[str] = None,
        days_back: int = 30,
        limit: int = 10
    ) -> Dict:
        """
        Get the best and worst predictions based on error magnitude.

        Args:
            model_version: Filter by model version (None = all versions)
            days_back: Only include predictions from last N days
            limit: Number of results to return for each category

        Returns:
            Dictionary with best and worst predictions
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        query = self.db.query(
            Prediction,
            Player,
            Game
        ).join(
            Player, Prediction.player_id == Player.id
        ).join(
            Game, Prediction.game_id == Game.id
        ).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.created_at >= cutoff
        )

        if model_version:
            query = query.filter(Prediction.model_version == model_version)

        # Best predictions (lowest error)
        best = query.order_by(func.abs(Prediction.predicted_value - Prediction.actual_value)).limit(limit).all()

        # Worst predictions (highest error)
        worst = query.order_by(func.abs(Prediction.predicted_value - Prediction.actual_value).desc()).limit(limit).all()

        def format_prediction(result):
            prediction, player, game = result[0], result[1], result[2]
            error = abs(prediction.predicted_value - prediction.actual_value)
            return {
                "id": prediction.id,
                "player": player.name,
                "team": player.team,
                "stat_type": prediction.stat_type,
                "predicted": prediction.predicted_value,
                "actual": prediction.actual_value,
                "difference": round(float(error), 2),
                "recommendation": prediction.recommendation,
                "was_correct": prediction.was_correct,
                "game_date": game.game_date.isoformat(),
                "opponent": f"@ {game.home_team}" if game.away_team == player.team else f"vs {game.away_team}"
            }

        return {
            "best": [format_prediction(p) for p in best],
            "worst": [format_prediction(p) for p in worst]
        }

    def get_accuracy_by_player(
        self,
        min_predictions: int = 5,
        days_back: int = 30
    ) -> List[Dict]:
        """
        Get accuracy metrics grouped by player.

        Args:
            min_predictions: Minimum number of predictions to include player
            days_back: Only include predictions from last N days

        Returns:
            List of player accuracy metrics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Group by player
        query = self.db.query(
            Player.id,
            Player.name,
            Player.team,
            func.count(Prediction.id).label('total'),
            func.avg(func.abs(Prediction.predicted_value - Prediction.actual_value)).label('mae'),
            func.sum(
                case(
                    (Prediction.was_correct == True, 1),
                    else_=0
                )
            ).label('correct_count')
        ).join(
            Prediction, Player.id == Prediction.player_id
        ).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.created_at >= cutoff,
            Prediction.recommendation.in_(["OVER", "UNDER"])
        ).group_by(
            Player.id, Player.name, Player.team
        ).having(
            func.count(Prediction.id) >= min_predictions
        ).all()

        results = []
        for player_id, name, team, total, mae, correct_count in query:
            win_rate = correct_count / total if total > 0 else 0.0
            results.append({
                "player_id": player_id,
                "name": name,
                "team": team,
                "total_predictions": total,
                "mae": round(float(mae), 2) if mae else 0.0,
                "correct_count": int(correct_count) if correct_count else 0,
                "win_rate": round(win_rate, 3)
            })

        # Sort by win rate descending
        results.sort(key=lambda x: x["win_rate"], reverse=True)

        return results
