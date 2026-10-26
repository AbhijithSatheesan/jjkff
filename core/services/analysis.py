from datetime import date, datetime, time, timedelta, timezone

import numpy as np
import pandas as pd

from core.models import WindForecast, WindActual


def _forecast_frame(rows, historical=False, cutoff=None):
    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(
            columns=["start_time", "publish_time", "generation_mw"]
        )

    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["publish_time"] = pd.to_datetime(df["publish_time"], utc=True)

    if historical:
        # Forecast must be published before the delivery day's
        # previous-day purchasing cutoff.
        deadline = (
            df["start_time"].dt.normalize()
            - pd.Timedelta(days=1)
            + pd.Timedelta(hours=9, minutes=50)
        )
        df = df[df["publish_time"] <= deadline]
    else:
        df = df[df["publish_time"] <= pd.Timestamp(cutoff)]

    # Keep the newest eligible forecast for each delivery hour,
    # then sort chronologically for the frontend chart.
    return (
        df.sort_values(["start_time", "publish_time"])
        .drop_duplicates("start_time", keep="last")
        .reset_index(drop=True)
    )


def _hourly_actuals(rows):
    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(
            columns=["hour", "actual_mw", "period_count"]
        )

    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["hour"] = df["start_time"].dt.floor("h")

    return (
        df.groupby("hour")
        .agg(
            actual_mw=("generation_mw", "mean"),
            period_count=("generation_mw", "count"),
        )
        .reset_index()
    )


def _metrics(forecasts, actuals, expected_hours):
    if forecasts.empty:
        raise ValueError("No eligible forecast data found.")

    forecasts = forecasts.copy()
    forecasts["hour"] = forecasts["start_time"].dt.floor("h")

    comparison = forecasts.merge(actuals, on="hour", how="left")

    # Only use hours containing both half-hour actual readings.
    comparison = comparison[comparison["period_count"] == 2]
    errors = (
        comparison["generation_mw"] - comparison["actual_mw"]
    ).to_numpy(dtype=float)

    if not len(errors):
        raise ValueError("Insufficient matching forecast and actual data.")

    absolute = np.abs(errors)

    return {
        "compared_hours": int(len(errors)),
        "coverage_percent": round(len(errors) / expected_hours * 100, 1),
        "mae_mw": round(float(absolute.mean()), 2),
        "rmse_mw": round(float(np.sqrt(np.mean(errors ** 2))), 2),
        "bias_mw": round(float(errors.mean()), 2),
        "median_absolute_error_mw": round(float(np.median(absolute)), 2),
        "p90_absolute_error_mw": round(float(np.percentile(absolute, 90)), 2),
    }


def analyze_decision_date(decision_date: date):
    if decision_date.year != 2026 or decision_date.month != 1:
        raise ValueError("Decision date must be in January 2026.")

    cutoff = datetime.combine(
        decision_date, time(9, 50), tzinfo=timezone.utc
    )
    delivery_date = decision_date + timedelta(days=1)

    def midnight(day):
        return datetime.combine(day, time.min, tzinfo=timezone.utc)

    # Forecast for the selected decision date's following delivery day.
    forecasts = list(
        WindForecast.objects.filter(
            start_time__gte=midnight(delivery_date),
            start_time__lt=midnight(delivery_date + timedelta(days=1)),
            publish_time__lte=cutoff,
        ).values("start_time", "publish_time", "generation_mw")
    )

    forecasts = _forecast_frame(forecasts, cutoff=cutoff)

    if forecasts.empty:
        raise ValueError("No eligible forecasts found for this date.")

    # Previous 30 completed delivery days; end is exclusive.
    history_start = decision_date - timedelta(days=30)
    history_end = decision_date

    historical_forecasts = list(
        WindForecast.objects.filter(
            start_time__gte=midnight(history_start),
            start_time__lt=midnight(history_end),
        ).values("start_time", "publish_time", "generation_mw")
    )

    historical_actuals = list(
        WindActual.objects.filter(
            start_time__gte=midnight(history_start),
            start_time__lt=midnight(history_end),
        ).values("start_time", "generation_mw")
    )

    historical_forecasts = _forecast_frame(
        historical_forecasts, historical=True
    )
    historical_actuals = _hourly_actuals(historical_actuals)

    historical_metrics = _metrics(
        historical_forecasts,
        historical_actuals,
        expected_hours=720,
    )

    return {
        "decision_date": decision_date.isoformat(),
        "delivery_date": delivery_date.isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "forecast": [
            {
                "time": row.start_time.strftime("%H:%M"),
                "mw": float(row.generation_mw),
                "published_at": row.publish_time.isoformat(),
            }
            for row in forecasts.itertuples()
        ],
        "historical_accuracy": {
            "window_start": history_start.isoformat(),
            "window_end": (history_end - timedelta(days=1)).isoformat(),
            **historical_metrics,
        },
    }