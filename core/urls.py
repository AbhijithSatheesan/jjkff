from django.urls import path
from .views import *

urlpatterns = [
    path("analysis/daily/", daily_analysis, name="daily-analysis"),
]