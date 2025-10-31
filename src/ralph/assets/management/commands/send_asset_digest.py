# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from ralph.assets.models import ComplianceRecord, MaintenanceRecord
from ralph.assets.models.assets import Asset
from ralph.assets.models.assets import ComplianceRecordStatus
from ralph.assets.notifications import AssetEventType, notify_asset_event
from ralph.assets.services.analytics import aggregate_metrics
from ralph.assets.services.reporting import (
    AssetFilters,
    compliance_dashboard,
    finance_dashboard,
    operations_dashboard,
    resource_report,
    resolve_asset_queryset,
)


class Command(BaseCommand):
    help = "Send a summary email covering costs, downtime, and compliance metrics."

    def add_arguments(self, parser):
        parser.add_argument("--recipients", nargs="*", default=[getattr(settings, "ASSETS_DIGEST_RECIPIENT", "")])

    def handle(self, *args, **options):
        recipients = [address for address in options["recipients"] if address]
        if not recipients:
            self.stdout.write(self.style.WARNING("No recipients provided; skipping digest."))
            return

        queryset, model = resolve_asset_queryset(AssetFilters())
        if hasattr(settings, "ASSETS_DIGEST_ASSET_QS"):
            custom_qs = settings.ASSETS_DIGEST_ASSET_QS()
            if custom_qs is not None:
                queryset = custom_qs
                model = getattr(queryset, "model", model)

        limit = getattr(settings, "ASSETS_DIGEST_LIMIT", 500)
        if limit and limit > 0 and hasattr(queryset, "values_list"):
            limited_ids = list(queryset.values_list("pk", flat=True)[:limit])
            queryset = queryset.filter(pk__in=limited_ids)

        assets = list(queryset)
        if not assets:
            queryset = Asset.objects.all()[: (limit or 200)]
            assets = list(queryset)
            model = Asset

        asset_ids = [asset.pk for asset in assets]
        base_ids = [getattr(asset, "baseobject_ptr_id", None) or asset.pk for asset in assets]
        queryset_for_reporting = model._default_manager.filter(pk__in=asset_ids)

        cost_summary = finance_dashboard(queryset_for_reporting)
        analytics = aggregate_metrics(assets)
        maintenance_qs = MaintenanceRecord.objects.filter(base_object_id__in=base_ids)
        overdue_maintenance = maintenance_qs.overdue().count()
        open_maintenance = maintenance_qs.open().count()
        compliance_qs = ComplianceRecord.objects.filter(base_object_id__in=base_ids)
        compliance_overdue = compliance_qs.filter(
            status__in=[ComplianceRecordStatus.overdue.id, ComplianceRecordStatus.failed.id]
        ).count()

        operations_metrics = operations_dashboard(queryset_for_reporting, model)
        compliance_metrics = compliance_dashboard(queryset_for_reporting, model)
        resource_metrics = resource_report(queryset_for_reporting)

        # emit threshold breach notifications for critical resource alerts
        asset_map = {asset.pk: asset for asset in assets}
        for anomaly in resource_metrics.get("anomalies", []):
            asset = asset_map.get(anomaly.get("asset_id"))
            if not asset:
                continue
            notify_asset_event(
                asset,
                AssetEventType.THRESHOLD_BREACH,
                payload={
                    "resource": anomaly.get("resource"),
                    "level_percent": anomaly.get("level_percent"),
                    "threshold_percent": anomaly.get("threshold_percent"),
                },
                severity="warning",
                metadata={"source": "assets.send_asset_digest"},
            )

        context = {
            "as_of": date.today(),
            "analytics": analytics,
            "costs": cost_summary,
            "overdue_maintenance": overdue_maintenance,
            "open_maintenance": open_maintenance,
            "compliance_overdue": compliance_overdue,
            "operations": operations_metrics,
            "compliance_metrics": compliance_metrics,
            "resource_metrics": resource_metrics,
            "resource_alerts": resource_metrics.get("anomalies", [])[:5],
        }

        subject = f"Asset Digest – {context['as_of']}"
        body_text = render_to_string("assets/email/digest.txt", context)
        body_html = render_to_string("assets/email/digest.html", context)

        connection = get_connection()
        message = EmailMultiAlternatives(subject, body_text, settings.DEFAULT_FROM_EMAIL, recipients, connection=connection)
        message.attach_alternative(body_html, "text/html")
        message.send()

        self.stdout.write(self.style.SUCCESS(f"Sent asset digest to {', '.join(recipients)}"))
