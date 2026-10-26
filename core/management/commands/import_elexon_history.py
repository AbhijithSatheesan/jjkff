from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from requests.exceptions import RequestException

from core.models import WindForecast, WindActual
from core.services.elexon import (
    fetch_wind_forecasts,
    fetch_wind_actuals,
)


def parse_timestamp(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def format_timestamp(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def date_windows(start, end, days=7):
    current = start

    while current < end:
        window_end = min(
            current + timedelta(days=days),
            end,
        )
        yield current, window_end
        current = window_end


class Command(BaseCommand):
    help = "Import historical wind forecasts and actual generation from Elexon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-days",
            type=int,
            default=7,
            help="Number of publication days to fetch per request.",
        )

    def handle(self, *args, **options):
        batch_days = options["batch_days"]

        if batch_days < 1:
            raise CommandError("--batch-days must be at least 1.")

        # Forecast versions needed for January decisions and
        # their preceding 30-day historical evaluation windows.
        forecast_start = parse_timestamp(
            "2025-12-01T00:00:00Z"
        )
        forecast_end = parse_timestamp(
            "2026-02-01T00:00:00Z"
        )

        # Actual records are filtered by their publication time.
        actual_start = parse_timestamp(
            "2025-12-03T00:00:00Z"
        )
        actual_end = parse_timestamp(
            "2026-02-03T00:00:00Z"
        )

        total_forecasts = 0
        total_actuals = 0

        self.stdout.write("Importing wind forecasts...")

        try:
            for start, end in date_windows(
                forecast_start, forecast_end, batch_days
            ):
                rows = fetch_wind_forecasts(
                    format_timestamp(start),
                    format_timestamp(end),
                )

                # Deduplicate records within this batch.
                records = {}

                for row in rows:
                    if not all(
                        row.get(field) is not None
                        for field in (
                            "publishTime",
                            "startTime",
                            "generation",
                        )
                    ):
                        continue

                    publish_time = parse_timestamp(
                        row["publishTime"]
                    )
                    start_time = parse_timestamp(
                        row["startTime"]
                    )

                    records[(publish_time, start_time)] = (
                        WindForecast(
                            publish_time=publish_time,
                            start_time=start_time,
                            generation_mw=float(row["generation"]),
                        )
                    )

                with transaction.atomic():
                    WindForecast.objects.bulk_create(
                        list(records.values()),
                        batch_size=1000,
                        update_conflicts=True,
                        update_fields=["generation_mw"],
                        unique_fields=["publish_time", "start_time"],
                    )

                total_forecasts += len(records)

                self.stdout.write(
                    f"Forecast batch {start.date()} to "
                    f"{end.date()}: {len(records)} records"
                )

            self.stdout.write("Importing actual wind generation...")

            for start, end in date_windows(
                actual_start, actual_end, batch_days
            ):
                rows = fetch_wind_actuals(
                    format_timestamp(start),
                    format_timestamp(end),
                )

                records = {}

                for row in rows:
                    if not all(
                        row.get(field) is not None
                        for field in (
                            "publishTime",
                            "startTime",
                            "generation",
                        )
                    ):
                        continue

                    start_time = parse_timestamp(row["startTime"])

                    records[start_time] = WindActual(
                        start_time=start_time,
                        publish_time=parse_timestamp(
                            row["publishTime"]
                        ),
                        generation_mw=float(row["generation"]),
                    )

                with transaction.atomic():
                    WindActual.objects.bulk_create(
                        list(records.values()),
                        batch_size=1000,
                        update_conflicts=True,
                        update_fields=[
                            "publish_time",
                            "generation_mw",
                        ],
                        unique_fields=["start_time"],
                    )

                total_actuals += len(records)

                self.stdout.write(
                    f"Actual batch {start.date()} to "
                    f"{end.date()}: {len(records)} records"
                )

        except RequestException as exc:
            raise CommandError(
                f"Elexon API request failed: {exc}. "
                "You can rerun the command to resume the import."
            ) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise CommandError(
                f"Could not process Elexon data: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "\nImport completed.\n"
                f"Forecast records processed: {total_forecasts}\n"
                f"Actual records processed: {total_actuals}\n"
                f"Forecasts stored: {WindForecast.objects.count()}\n"
                f"Actuals stored: {WindActual.objects.count()}"
            )
        )