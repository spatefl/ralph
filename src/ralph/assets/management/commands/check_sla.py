# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ralph.assets.models import MaintenanceRecord, MaintenanceRecordStatus, SLAPolicy
from ralph.assets.notifications import AssetEventType, notify_asset_event


class Command(BaseCommand):
    help = "Evaluate SLA policies against active maintenance records and emit alerts."

    def handle(self, *args, **options):
        now = timezone.now()
        policies = {policy.pk: policy for policy in SLAPolicy.objects.filter(is_active=True)}
        if not policies:
            self.stdout.write("No SLA policies configured.")
            return

        records = MaintenanceRecord.objects.filter(
            status__in=[
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ]
        ).select_related("base_object")

        breaches = 0
        for record in records:
            asset = record.base_object
            policy = SLAPolicy.for_asset(asset)
            if not policy:
                continue

            opened_delta = (now - record.opened_at).total_seconds() / 3600
            breach = False
            if opened_delta > float(policy.target_resolution_hours or 0):
                breach = True
            elif record.status == MaintenanceRecordStatus.open.id and opened_delta > float(policy.target_response_hours or 0):
                breach = True

            if not breach:
                continue

            extra = record.extra_data or {}
            if extra.get("sla_notified"):
                continue

            extra["sla_notified"] = now.isoformat()
            record.extra_data = extra
            record.save(update_fields=["extra_data", "modified"])
            notify_asset_event(
                asset,
                AssetEventType.MAINTENANCE_SLA_OVERDUE,
                payload={
                    "record_id": record.pk,
                    "policy": policy.name,
                    "hours_open": round(opened_delta, 1),
                },
            )
            breaches += 1
        self.stdout.write(self.style.SUCCESS(f"Processed SLA policies; {breaches} breach notifications issued."))
