from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ralph.assets.models import (
    Asset,
    ComplianceRecord,
    MaintenancePartUsage,
    MaintenanceRecord,
)
from ralph.assets.services.analytics import aggregate_metrics
from ralph.assets.services.costs import summarise_costs
from ralph.assets.services.reporting import (
    AssetFilters,
    compliance_dashboard,
    finance_dashboard,
    financial_report,
    inventory_report,
    lifecycle_report,
    maintenance_compliance_report,
    operations_dashboard,
    resource_report,
    resolve_asset_queryset,
    utilization_report,
)
from ralph.api import router


def _date_param(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


class ReportingViewSet(ViewSet):
    """Provides aggregated reporting endpoints for BI and dashboards."""

    serializer_class = serializers.Serializer

    def _asset_filters(self, request) -> AssetFilters:
        return AssetFilters(
            model_label=request.query_params.get("model") or request.query_params.get("asset_model"),
            service_env=request.query_params.get("service_env"),
            owner=request.query_params.get("owner"),
            user=request.query_params.get("user"),
            region=request.query_params.get("region"),
            status=request.query_params.get("status"),
            deployment_status=request.query_params.get("deployment_status"),
            location=request.query_params.get("location"),
            project=request.query_params.get("project"),
        )

    def _filtered_assets(self, request):
        filters = self._asset_filters(request)
        queryset, model = resolve_asset_queryset(filters)
        return queryset, model

    def _get_period(self, request):
        start = _date_param(request.query_params.get("start"))
        end = _date_param(request.query_params.get("end"))
        if end and timezone.is_naive(end):
            end = timezone.make_aware(end)
        if start and timezone.is_naive(start):
            start = timezone.make_aware(start)
        return start, end or timezone.now()

    @staticmethod
    def _csv_response(filename: str, fieldnames, rows):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=["get"], url_path="inventory")
    def inventory(self, request):
        queryset, model = self._filtered_assets(request)
        report = inventory_report(queryset, model)
        if request.query_params.get("format") == "csv":
            rows = report["assets"]
            fieldnames = [
                "asset_id",
                "name",
                "hostname",
                "content_type",
                "model",
                "service_env",
                "deployment_site",
                "assigned_location",
                "status_display",
            ]
            return self._csv_response("inventory_report.csv", fieldnames, rows)
        return Response(report)

    @action(detail=False, methods=["get"], url_path="utilization")
    def utilization(self, request):
        queryset, model = self._filtered_assets(request)
        start, end = self._get_period(request)
        report = utilization_report(queryset, start=start, end=end)
        if request.query_params.get("format") == "csv":
            rows = report["assets"]
            fieldnames = [
                "asset_id",
                "name",
                "active_hours",
                "idle_hours",
                "downtime_hours",
                "distance_km",
                "utilization_rate",
            ]
            return self._csv_response("utilization_report.csv", fieldnames, rows)
        return Response(report)

    @action(detail=False, methods=["get"], url_path="maintenance-compliance")
    def maintenance_compliance(self, request):
        queryset, _ = self._filtered_assets(request)
        report = maintenance_compliance_report(queryset)
        if request.query_params.get("format") == "csv":
            maintenance_rows = [
                {
                    **row,
                    "section": "maintenance",
                }
                for row in report["maintenance"]["records"]
            ]
            compliance_rows = [
                {
                    **row,
                    "section": "compliance",
                }
                for row in report["compliance"]["records"]
            ]
            rows = maintenance_rows + compliance_rows
            fieldnames = [
                "section",
                "asset_id",
                "name",
                "record_id",
                "record_type",
                "opened_at",
                "expected_completion",
                "is_overdue",
                "status",
                "title",
                "expires_on",
            ]
            return self._csv_response("maintenance_compliance_report.csv", fieldnames, rows)
        return Response(report)

    @action(detail=False, methods=["get"], url_path="financial")
    def financial(self, request):
        queryset, _ = self._filtered_assets(request)
        start, end = self._get_period(request)
        report = financial_report(queryset, start=start.date() if start else None, end=end.date() if end else None)
        if request.query_params.get("format") == "csv" or request.query_params.get("export") == "csv":
            rows = report["assets"]
            fieldnames = [
                "asset_id",
                "name",
                "capex_actual",
                "maintenance_actual",
                "parts_actual",
                "opex_actual",
                "fuel_actual",
                "distance_km",
                "active_hours",
                "idle_hours",
                "cost_per_hour",
                "fuel_consumption_per_hour",
                "budget",
            ]
            # Ensure budget column serialized as string
            for row in rows:
                budget = row.get("budget", {})
                row["budget"] = json.dumps(budget) if budget else "{}"
            return self._csv_response("financial_report.csv", fieldnames, rows)
        return Response(report)

    @action(detail=False, methods=["get"], url_path="lifecycle")
    def lifecycle(self, request):
        queryset, model = self._filtered_assets(request)
        report = lifecycle_report(queryset, model)
        if request.query_params.get("format") == "csv":
            rows = [
                {"section": "status", "label": row["status"], "count": row["count"]}
                for row in report["status_breakdown"]
            ]
            rows += [
                {"section": "disposal", "label": item["status"], "count": item["count"]}
                for item in report["disposal"]
            ]
            fieldnames = ["section", "label", "count"]
            return self._csv_response("lifecycle_report.csv", fieldnames, rows)
        return Response(report)

    @action(detail=False, methods=["get"], url_path="resources")
    def resources(self, request):
        queryset, _ = self._filtered_assets(request)
        report = resource_report(queryset)
        if request.query_params.get("format") == "csv":
            rows = []
            for resource_name in ("fuel", "water"):
                for row in report[resource_name]["assets"]:
                    rows.append({"resource": resource_name, **row})
            fieldnames = [
                "resource",
                "asset_id",
                "name",
                "capacity_liters",
                "level_percent",
                "available_liters",
                "threshold_percent",
                "deployment_site",
                "assigned_location",
                "last_reported_at",
            ]
            return self._csv_response("resource_report.csv", fieldnames, rows)
        return Response(report)

    @action(detail=False, methods=["get"], url_path="dashboard/operations")
    def dashboard_operations(self, request):
        queryset, model = self._filtered_assets(request)
        data = operations_dashboard(queryset, model)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="dashboard/compliance")
    def dashboard_compliance(self, request):
        queryset, model = self._filtered_assets(request)
        data = compliance_dashboard(queryset, model)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="dashboard/finance")
    def dashboard_finance(self, request):
        queryset, _ = self._filtered_assets(request)
        start, end = self._get_period(request)
        data = finance_dashboard(queryset, start=start.date() if start else None, end=end.date() if end else None)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="cost-trend")
    def cost_trend(self, request):
        start, end = self._get_period(request)
        records = MaintenanceRecord.objects.all()
        if start:
            records = records.filter(opened_at__gte=start)
        if end:
            records = records.filter(opened_at__lte=end)
        monthly = (
            records.annotate(month=TruncMonth("opened_at"))
            .values("month")
            .annotate(maintenance=Coalesce(Sum("cost"), Value(0)))
            .order_by("month")
        )

        part_costs = (
            MaintenancePartUsage.objects.filter(maintenance_record__in=records)
            .annotate(month=TruncMonth("maintenance_record__opened_at"))
            .values("month")
            .annotate(
                parts=Coalesce(
                    Sum(
                        F("quantity_used")
                        * Coalesce(F("unit_cost"), F("part__unit_cost"), Value(0))
                    ),
                    Value(0),
                )
            )
        )
        part_lookup = {row["month"]: float(row["parts"] or 0) for row in part_costs}

        data = []
        for row in monthly:
            month = row["month"].date().isoformat()
            maintenance = float(row["maintenance"] or 0)
            parts = part_lookup.get(row["month"], 0.0)
            data.append({"month": month, "maintenance": maintenance, "parts": parts})

        if request.query_params.get("format") == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["month", "maintenance", "parts"])
            writer.writeheader()
            writer.writerows(data)
            response = HttpResponse(output.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="cost_trend.csv"'
            return response

        return Response({"results": data})

    @action(detail=False, methods=["get"], url_path="downtime")
    def downtime(self, request):
        start, end = self._get_period(request)
        records = MaintenanceRecord.objects.filter(out_of_service=True)
        if start:
            records = records.filter(opened_at__gte=start)
        if end:
            records = records.filter(opened_at__lte=end)

        downtime = {}
        for record in records.select_related("base_object"):
            start_time = record.opened_at
            end_time = record.closed_at or timezone.now()
            if start_time and start and start_time < start:
                start_time = start
            if end_time and end and end_time > end:
                end_time = end
            delta = (end_time - start_time).total_seconds() / 3600
            if delta < 0:
                continue
            key = str(record.base_object)
            downtime.setdefault(key, 0.0)
            downtime[key] += round(delta, 2)

        return Response({"results": downtime})

    @action(detail=False, methods=["get"], url_path="compliance-rate")
    def compliance_rate(self, request):
        today = timezone.now().date()
        records = ComplianceRecord.objects.all()
        total = records.count() or 1
        compliant = records.filter(status__in=[1]).count()
        due_soon = records.filter(status=2).count()
        overdue = records.filter(status__in=[3, 4]).count()
        return Response(
            {
                "totals": {
                    "compliant": compliant,
                    "due_soon": due_soon,
                    "overdue": overdue,
                    "total": total,
                },
                "rate": compliant / total,
                "as_of": today.isoformat(),
            }
        )

    @action(detail=False, methods=["get"], url_path="utilization-heatmap")
    def utilization_heatmap(self, request):
        start, end = self._get_period(request)
        snapshots = AssetUtilizationSnapshot.objects.all()
        if start:
            snapshots = snapshots.filter(date__gte=start.date())
        if end:
            snapshots = snapshots.filter(date__lte=end.date())

        data = (
            snapshots.annotate(day=TruncDate("date"))
            .values("base_object__hostname", "day")
            .annotate(active=Sum("active_seconds"), idle=Sum("idle_seconds"))
            .order_by("day")
        )

        results = {}
        for row in data:
            asset_label = row["base_object__hostname"] or "asset-{}".format(row["day"].isoformat())
            results.setdefault(asset_label, {})[row["day"].isoformat()] = {
                "active_hours": round((row["active"] or 0) / 3600, 2),
                "idle_hours": round((row["idle"] or 0) / 3600, 2),
            }
        return Response({"results": results})

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        assets = Asset.objects.all()[:200]
        analytics = aggregate_metrics(assets)
        cost_summary = summarise_costs(assets)
        return Response(
            {
                "assets": analytics,
                "costs": cost_summary,
            }
        )


router.register(r"reporting", ReportingViewSet, basename="asset-reporting")


urlpatterns = []
