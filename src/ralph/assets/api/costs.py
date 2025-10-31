from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

from django.http import HttpResponse
from django.urls import re_path
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from ralph.assets.models.assets import Asset
from ralph.assets.services.costs import summarise_costs


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    parsed = parse_date(value)
    return parsed


class CostSummaryView(APIView):
    """Return aggregated CAPEX/OPEX summaries for assets."""

    def get_queryset(self, request):
        asset_ids = request.query_params.getlist("asset_id")
        if asset_ids:
            return Asset.objects.filter(pk__in=asset_ids)
        return Asset.objects.all()

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset(request)
        start = _parse_date(request.query_params.get("start"))
        end = _parse_date(request.query_params.get("end"))

        summary = summarise_costs(queryset, start=start, end=end)

        if request.query_params.get("export") == "csv":
            return self._export_csv(summary)
        return Response(summary)

    def _export_csv(self, summary):
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "asset_id",
                "name",
                "capex_actual",
                "opex_actual",
                "fuel_actual",
                "distance_km",
                "active_hours",
                "idle_hours",
                "cost_per_hour",
                "fuel_consumption_per_hour",
                "capex_budget",
                "opex_budget",
                "capex_variance",
                "opex_variance",
            ]
        )
        for asset in summary["assets"]:
            budget = asset["budget"]
            writer.writerow(
                [
                    asset["asset_id"],
                    asset["name"],
                    asset["capex_actual"],
                    asset["opex_actual"],
                    asset["fuel_actual"],
                    asset["distance_km"],
                    asset["active_hours"],
                    asset["idle_hours"],
                    asset["cost_per_hour"],
                    asset["fuel_consumption_per_hour"],
                    budget["capex_budget"],
                    budget["opex_budget"],
                    budget["capex_variance"],
                    budget["opex_variance"],
                ]
            )
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=asset_cost_summary.csv"
        return response


urlpatterns = [
    re_path(r"^costs/summary/$", CostSummaryView.as_view()),
]
