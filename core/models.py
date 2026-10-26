from django.db import models


class WindForecast(models.Model):
    publish_time = models.DateTimeField(db_index=True)
    start_time = models.DateTimeField(db_index=True)
    generation_mw = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["publish_time", "start_time"],
                name="unique_wind_forecast_version",
            )
        ]
        ordering = ["start_time", "publish_time"]

    def __str__(self):
        return f"Forecast {self.start_time} @ {self.publish_time}"


class WindActual(models.Model):
    start_time = models.DateTimeField(unique=True)
    publish_time = models.DateTimeField()
    generation_mw = models.FloatField()

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return f"Actual {self.start_time}"