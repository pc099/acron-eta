"""
ForecastingModel -- cost and cache prediction for Asahi.

Uses exponential moving average (EMA) for short-term (7-day) predictions
and linear regression for 30-day projections.  Confidence intervals are
derived from historical variance.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.exceptions import ObservabilityError
from src.observability.analytics import AnalyticsEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Forecast(BaseModel):
    """A cost or rate prediction with confidence bounds.

    Attributes:
        period: The forecast horizon description (e.g. ``"30 days"``).
        predicted_cost: Point estimate of total cost.
        confidence_low: Lower bound of the confidence interval.
        confidence_high: Upper bound of the confidence interval.
        trend: Direction of the trend.
        warning: Optional human-readable warning message.
    """

    period: str
    predicted_cost: float
    confidence_low: float
    confidence_high: float
    trend: Literal["increasing", "decreasing", "stable"]
    warning: Optional[str] = None


class ForecastConfig(BaseModel):
    """Configuration for the ForecastingModel.

    Attributes:
        ema_span_days: Number of days for the EMA window.
        min_data_points: Minimum observations needed for a forecast.
        stable_threshold_pct: Maximum daily change to classify as stable.
    """

    ema_span_days: int = Field(default=7, ge=1)
    min_data_points: int = Field(default=3, ge=1)
    stable_threshold_pct: float = Field(default=5.0, ge=0.0)


# ---------------------------------------------------------------------------
# ForecastingModel
# ---------------------------------------------------------------------------


class ForecastingModel:
    """Predict future costs based on historical trends.

    Supports EMA-based short-term forecasts and linear-regression-based
    long-term projections with confidence intervals derived from the
    standard deviation of residuals.

    Args:
        analytics: The AnalyticsEngine supplying historical data.
        config: Optional configuration; defaults are applied if omitted.
    """

    def __init__(
        self,
        analytics: AnalyticsEngine,
        config: Optional[ForecastConfig] = None,
    ) -> None:
        self._analytics = analytics
        self._config = config or ForecastConfig()

    # ------------------------------------------------------------------
    # Cost prediction
    # ------------------------------------------------------------------

    def predict_cost(
        self,
        horizon_days: int = 30,
        confidence: float = 0.95,
    ) -> Forecast:
        """Predict total cost over the next ``horizon_days``.

        Uses EMA for horizons <= 7 days, linear regression for longer.

        Args:
            horizon_days: Number of days to forecast.
            confidence: Confidence level for the interval (0-1).

        Returns:
            A ``Forecast`` with predicted cost and confidence bounds.

        Raises:
            ObservabilityError: If there is insufficient data.
        """
        daily_costs = self._get_daily_costs()

        if len(daily_costs) < self._config.min_data_points:
            logger.warning(
                "Insufficient data for cost forecast",
                extra={
                    "data_points": len(daily_costs),
                    "min_required": self._config.min_data_points,
                },
            )
            return Forecast(
                period=f"{horizon_days} days",
                predicted_cost=0.0,
                confidence_low=0.0,
                confidence_high=0.0,
                trend="stable",
                warning=(
                    f"Insufficient data: {len(daily_costs)} days available, "
                    f"need at least {self._config.min_data_points}."
                ),
            )

        if horizon_days <= self._config.ema_span_days:
            predicted_daily = self._ema(daily_costs)
        else:
            predicted_daily = self._linear_predict(
                daily_costs, steps_ahead=horizon_days
            )

        predicted_total = predicted_daily * horizon_days
        std_dev = self._std_dev(daily_costs)
        z = self._z_score(confidence)

        margin = z * std_dev * math.sqrt(horizon_days)
        confidence_low = max(0.0, predicted_total - margin)
        confidence_high = predicted_total + margin

        trend = self._classify_trend(daily_costs)

        warning = None
        if trend == "increasing" and horizon_days >= 14:
            warning = (
                f"Costs are trending upward. Projected spend over "
                f"{horizon_days} days: ${predicted_total:.2f}."
            )

        result = Forecast(
            period=f"{horizon_days} days",
            predicted_cost=round(predicted_total, 4),
            confidence_low=round(confidence_low, 4),
            confidence_high=round(confidence_high, 4),
            trend=trend,
            warning=warning,
        )

        logger.info(
            "Cost forecast generated",
            extra={
                "horizon_days": horizon_days,
                "predicted_cost": result.predicted_cost,
                "trend": result.trend,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Cache hit rate prediction
    # ------------------------------------------------------------------

    def predict_cache_hit_rate(
        self,
        horizon_days: int = 30,
    ) -> Dict[str, float]:
        """Predict future cache hit rates per tier.

        Uses EMA of recent cache performance to extrapolate.

        Args:
            horizon_days: Forecast horizon (informational).

        Returns:
            Dictionary with ``tier_1``, ``tier_2``, ``tier_3``, and
            ``overall`` predicted hit rates.
        """
        perf = self._analytics.cache_performance()

        result: Dict[str, float] = {}
        total_hits = 0.0
        total_total = 0.0
        for tier in ["1", "2", "3"]:
            tier_data = perf.get(f"tier_{tier}", {})
            hits = float(tier_data.get("hits", 0))
            misses = float(tier_data.get("misses", 0))
            total = hits + misses
            rate = hits / total if total > 0 else 0.0
            result[f"tier_{tier}"] = round(rate, 4)
            total_hits += hits
            total_total += total

        result["overall"] = round(
            total_hits / total_total if total_total > 0 else 0.0, 4
        )

        logger.debug(
            "Cache hit rate forecast generated",
            extra={"horizon_days": horizon_days, "overall": result["overall"]},
        )
        return result

    # ------------------------------------------------------------------
    # Budget risk
    # ------------------------------------------------------------------

    def detect_budget_risk(
        self,
        monthly_budget: float,
    ) -> Optional[str]:
        """Check whether projected spend will exceed the monthly budget.

        Args:
            monthly_budget: Monthly spending cap in dollars.

        Returns:
            A warning message if the projected spend exceeds the budget,
            or ``None`` if within budget.
        """
        forecast = self.predict_cost(horizon_days=30)

        if forecast.warning and "Insufficient data" in forecast.warning:
            return None

        if forecast.predicted_cost > monthly_budget:
            overage = forecast.predicted_cost - monthly_budget
            return (
                f"Projected 30-day spend (${forecast.predicted_cost:.2f}) "
                f"exceeds monthly budget (${monthly_budget:.2f}) "
                f"by ${overage:.2f}. Consider optimising routing or "
                f"cache settings."
            )

        # Also warn if the upper confidence bound exceeds budget
        if forecast.confidence_high > monthly_budget:
            return (
                f"Projected spend (${forecast.predicted_cost:.2f}) is "
                f"within budget, but worst-case estimate "
                f"(${forecast.confidence_high:.2f}) exceeds the "
                f"${monthly_budget:.2f} monthly budget."
            )

        return None

    # ------------------------------------------------------------------
    # Internal algorithms
    # ------------------------------------------------------------------

    def _get_daily_costs(self) -> List[float]:
        """Aggregate events into daily cost totals.

        Returns:
            List of daily cost values (oldest first).
        """
        # Retrieve all events (up to retention window)
        events = self._analytics._collector.get_events()

        if not events:
            return []

        daily: Dict[str, float] = {}
        for evt in events:
            day_key = evt.timestamp.strftime("%Y-%m-%d")
            daily[day_key] = daily.get(day_key, 0.0) + evt.value

        # Sort by date and return values
        return [v for _, v in sorted(daily.items())]

    def _ema(self, values: List[float]) -> float:
        """Compute exponential moving average.

        Args:
            values: Time-series values (oldest first).

        Returns:
            Latest EMA value.
        """
        if not values:
            return 0.0

        span = min(self._config.ema_span_days, len(values))
        alpha = 2.0 / (span + 1)
        ema = values[0]
        for val in values[1:]:
            ema = alpha * val + (1 - alpha) * ema
        return ema

    def _linear_predict(
        self, values: List[float], steps_ahead: int = 1
    ) -> float:
        """Predict the next value using ordinary least squares regression.

        Args:
            values: Time-series values (oldest first).
            steps_ahead: How many steps ahead to predict.

        Returns:
            Predicted daily value at ``len(values) + steps_ahead - 1``.
        """
        n = len(values)
        if n < 2:
            return values[-1] if values else 0.0

        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = sum(values) / n

        numerator = sum(
            (x - x_mean) * (y - y_mean)
            for x, y in zip(x_vals, values)
        )
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator == 0:
            return y_mean

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Predict the daily rate at the future point
        future_x = n + steps_ahead - 1
        predicted = intercept + slope * future_x

        # Don't predict negative daily costs
        return max(0.0, predicted)

    def _std_dev(self, values: List[float]) -> float:
        """Compute sample standard deviation.

        Args:
            values: Numeric values.

        Returns:
            Standard deviation, or 0.0 if fewer than 2 values.
        """
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return math.sqrt(variance)

    def _classify_trend(self, values: List[float]) -> Literal[
        "increasing", "decreasing", "stable"
    ]:
        """Classify the overall trend of a time series.

        Uses the linear regression slope relative to the mean to
        determine direction.

        Args:
            values: Daily values (oldest first).

        Returns:
            ``"increasing"``, ``"decreasing"``, or ``"stable"``.
        """
        if len(values) < 2:
            return "stable"

        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        numerator = sum(
            (i - x_mean) * (v - y_mean) for i, v in enumerate(values)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0 or y_mean == 0:
            return "stable"

        slope = numerator / denominator
        daily_change_pct = abs(slope / y_mean) * 100

        if daily_change_pct < self._config.stable_threshold_pct:
            return "stable"
        return "increasing" if slope > 0 else "decreasing"

    @staticmethod
    def _z_score(confidence: float) -> float:
        """Approximate z-score for a given confidence level.

        Uses a lookup table for common values.

        Args:
            confidence: Confidence level between 0 and 1.

        Returns:
            Approximate z-score.
        """
        table = {
            0.80: 1.282,
            0.85: 1.440,
            0.90: 1.645,
            0.95: 1.960,
            0.99: 2.576,
        }
        # Return exact match or nearest
        if confidence in table:
            return table[confidence]

        closest = min(table.keys(), key=lambda k: abs(k - confidence))
        return table[closest]
