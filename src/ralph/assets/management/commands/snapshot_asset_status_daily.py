# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ralph.assets.models import BaseObject
from ralph.assets.models.assets import (
    AssetStatusSnapshot,
    ComplianceRecord,
    ComplianceRecordStatus,
    MaintenanceRecord,
    MaintenanceRecordStatus,
)


class Command(BaseCommand):
    help = "Create daily status snapshots for all assets (status, deployment, open maint, overdue compliance)."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="target", default=None, help="Date ISO (YYYY-MM-DD), defaults to today")
        parser.add_argument("--limit", type=int, default=0, help="Max assets to snapshot (for testing)")

    @transaction.atomic
    def handle(self, *args, **options):
        target = options.get("target")
        if target:
            snapshot_date = date.fromisoformat(target)
        else:
            snapshot_date = timezone.now().date()

        qs = BaseObject.polymorphic_objects.all().select_related("content_type")
        if options.get("limit"):
            qs = qs[: options["limit"]]

        created, updated = 0, 0
        for base in qs:
            asset = base
            # derive labels if fields exist
            status_label = getattr(asset, "get_status_display", lambda: "")() if hasattr(asset, "status") else ""
            deployment_label = getattr(asset, "get_deployment_status_display", lambda: "")() if hasattr(asset, "deployment_status") else ""

            open_maint = MaintenanceRecord.objects.filter(
                base_object=base,
                status__in=[MaintenanceRecordStatus.open.id, MaintenanceRecordStatus.in_progress.id],
            ).count()
            overdue_compl = ComplianceRecord.objects.filter(
                base_object=base,
                status__in=[ComplianceRecordStatus.overdue.id, ComplianceRecordStatus.failed.id],
            ).count()

            obj, was_created = AssetStatusSnapshot.objects.update_or_create(
                base_object=base,
                date=snapshot_date,
                defaults={
                    "status_label": status_label or "",
                    "deployment_status_label": deployment_label or "",
                    "open_maintenance": open_maint,
                    "overdue_compliance": overdue_compl,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Status snapshots: created={created} updated={updated} for {snapshot_date}"))

