from datetime import date

from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.services.analysis import analyze_decision_date


@api_view(["GET"])
def daily_analysis(request):
    try:
        decision_date = date.fromisoformat(
            request.query_params["decision_date"]
        )
        result = analyze_decision_date(decision_date)
        return Response(result)

    except KeyError:
        return Response(
            {"error": "Provide decision_date=YYYY-MM-DD"},
            status=400,
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)