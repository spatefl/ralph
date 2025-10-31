# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
import json
from typing import Callable, Dict

from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ralph.assets.models.assets import ReportConfig
from ralph.assets.services.reporting import (
    AssetFilters,
    compliance_dashboard,
    compliance_dashboard as dashboard_compliance,
    finance_dashboard,
    inventory_report,
    lifecycle_report,
    maintenance_compliance_report,
    operations_dashboard as dashboard_ops,
    resource_report,
    resolve_asset_queryset,
    utilization_report,
)


def _csv_from_dicts(fieldnames, rows) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


class Command(BaseCommand):
    help = "Run a saved report configuration and email the results."

    def add_arguments(self, parser):
        parser.add_argument("config_id", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            cfg = ReportConfig.objects.get(pk=options["config_id"], is_active=True)
        except ReportConfig.DoesNotExist:
            raise CommandError("Active ReportConfig not found")

        params = cfg.params or {}
        filters = AssetFilters(
            model_label=params.get("model") or params.get("asset_model"),
            service_env=params.get("service_env"),
            owner=params.get("owner"),
            user=params.get("user"),
            region=params.get("region"),
            status=params.get("status"),
            deployment_status=params.get("deployment_status"),
            location=params.get("location"),
            project=params.get("project"),
        )
        queryset, model = resolve_asset_queryset(filters)

        endpoint = (cfg.endpoint or "").strip()
        data = None
        now = timezone.now()

        if endpoint == "inventory":
            data = inventory_report(queryset, model)
        elif endpoint == "utilization":
            start, end = params.get("start"), params.get("end")
            data = utilization_report(queryset, start=timezone.datetime.fromisoformat(start) if start else None, end=timezone.datetime.fromisoformat(end) if end else None)
        elif endpoint == "maintenance-compliance":
            data = maintenance_compliance_report(queryset)
        elif endpoint == "lifecycle":
            data = lifecycle_report(queryset, model)
        elif endpoint == "financial":
            data = finance_dashboard(queryset)
        elif endpoint == "resources":
            data = resource_report(queryset)
        elif endpoint in ("dashboard-ops", "dashboard_operations"):
            data = dashboard_ops(queryset, model)
        elif endpoint in ("dashboard-compliance", "dashboard_compliance"):
            data = dashboard_compliance(queryset, model)
        elif endpoint in ("dashboard-finance", "dashboard_finance"):
            data = finance_dashboard(queryset)
        else:
            raise CommandError(f"Unsupported endpoint: {endpoint}")

        recipients = []
        for token in (cfg.recipients or "").replace(";", ",").replace(" ", "").split(","):
            if token:
                recipients.append(token)

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING(f"DRY RUN for config {cfg.pk} – not sending email"))
            self.stdout.write(json.dumps(data, default=str)[:2000])
            return

        if not recipients:
            self.stdout.write(self.style.WARNING("No recipients configured; skipping email."))
        else:
            subject = f"Report: {cfg.name} ({endpoint})"
            body_text = f"Generated at {now.isoformat()}\nEndpoint: {endpoint}\nParameters: {json.dumps(params)}\n"
            attachment_name = f"{endpoint}_{now.strftime('%Y%m%d_%H%M%S')}.{cfg.export_format or 'csv'}"

            if (cfg.export_format or "csv").lower() == "csv":
                # try to flatten a primary table; fallback to dump JSON
                csv_payload = None
                if endpoint in ("inventory",):
                    rows = data.get("assets", [])
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
                    csv_payload = _csv_from_dicts(fieldnames, rows)
                elif endpoint in ("utilization",):
                    rows = data.get("assets", [])
                    fieldnames = [
                        "asset_id",
                        "name",
                        "active_hours",
                        "idle_hours",
                        "downtime_hours",
                        "utilization_rate",
                        "availability_rate",
                        "distance_km",
                    ]
                    csv_payload = _csv_from_dicts(fieldnames, rows)
                elif endpoint in ("maintenance-compliance",):
                    rows = [
                        {"section": "maintenance", **row}
                        for row in data.get("maintenance", {}).get("records", [])
                    ] + [
                        {"section": "compliance", **row}
                        for row in data.get("compliance", {}).get("records", [])
                    ]
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
                    csv_payload = _csv_from_dicts(fieldnames, rows)
                else:
                    # fallback JSON
                    csv_payload = json.dumps(data, default=str)

                body = EmailMultiAlternatives(subject, body_text, None, recipients, connection=get_connection())
                body.attach(attachment_name, csv_payload, "text/csv")
                body.send()
            else:
                # JSON export
                body = EmailMultiAlternatives(subject, body_text + "\nSee attachment.", None, recipients, connection=get_connection())
                body.attach(attachment_name, json.dumps(data, default=str), "application/json")
                body.send()

        cfg.last_run_at = now
        cfg.save(update_fields=["last_run_at", "modified"])
        self.stdout.write(self.style.SUCCESS(f"Report sent for config {cfg.pk} ({endpoint})"))

