# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg, Sum
from django.utils import timezone

from ralph.assets.models import Asset, AssetUtilizationSnapshot, MaintenanceRecord, MaintenanceRecordStatus
from ralph.assets.notifications import AssetEventType, notify_asset_event

ACTIVE_THRESHOLD_HOURS = 18
BUDGET_OVERRUN_RATIO = 1.1


class Command(BaseCommand):
    help = "Forecast upcoming maintenance, reschedule overdue tasks, and raise predictive alerts."

    def handle(self, *args, **options):
        today = timezone.now().date()
        start_window = today - timedelta(days=7)

        self._auto_reschedule(today)
        alerts = 0

        for asset in Asset.objects.all():
            snapshots = AssetUtilizationSnapshot.objects.filter(
                base_object=getattr(asset, "baseobject_ptr", asset),
                date__gte=start_window,
                date__lte=today,
            )
            if not snapshots.exists():
                continue
            agg = snapshots.aggregate(
                active=Avg("active_seconds"),
                idle=Avg("idle_seconds"),
                distance=Sum("distance_km"),
            )
            avg_active_hours = (agg["active"] or 0) / 3600
            if avg_active_hours > ACTIVE_THRESHOLD_HOURS:
                notify_asset_event(
                    asset,
                    AssetEventType.THRESHOLD_BREACH,
                    payload={
                        "metric": "active_hours",
                        "average": round(avg_active_hours, 2),
                        "threshold": ACTIVE_THRESHOLD_HOURS,
                    },
                )
                alerts += 1

        self.stdout.write(self.style.SUCCESS(f"Predictive checks completed; {alerts} alerts emitted."))

    def _auto_reschedule(self, today):
        overdue = MaintenanceRecord.objects.filter(
            status__in=[
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ],
            expected_completion__lt=today,
        )
        for record in overdue:
            record.expected_completion = today + timedelta(days=1)
            record.save(update_fields=["expected_completion", "modified"])
            notify_asset_event(
                record.base_object,
                AssetEventType.MAINTENANCE_OVERDUE,
                payload={
                    "record_id": record.pk,
                    "rescheduled_for": record.expected_completion.isoformat(),
                },
            )
