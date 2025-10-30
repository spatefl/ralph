from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from ralph.assets.models.assets import (
    MaintenanceRecord,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
)
from ralph.assets.notifications import AssetEventType, notify_asset_event
from ralph.drones.models import DroneAsset, DroneAssetStatus
from ralph.fleet.models import FleetAsset, FleetAssetStatus
from ralph.heavy_equipment.models import (
    HeavyEquipmentAsset,
    HeavyEquipmentAssetStatus,
)
from ralph.sensors.models import SensorAsset, SensorAssetStatus


class Command(BaseCommand):
    help = (
        "Automatically create maintenance tickets for assets that reach"
        " their service thresholds and emit SLA alerts for overdue work orders."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sla-days",
            type=int,
            default=3,
            help="Number of days after scheduling before SLA is considered overdue.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report actions without persisting changes or sending notifications.",
        )

    def handle(self, *args, **options):
        sla_days = options["sla_days"]
        dry_run = options["dry_run"]
        created = 0

        created += self._schedule_heavy_equipment(sla_days, dry_run)
        created += self._schedule_fleet_assets(sla_days, dry_run)
        created += self._schedule_drones(sla_days, dry_run)
        created += self._schedule_sensors(sla_days, dry_run)

        sla_alerts = self._check_sla_overdue(dry_run)

        verb = "would create" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(f"{verb.title()} {created} maintenance ticket(s)."))
        if sla_alerts:
            self.stdout.write(
                self.style.WARNING(
                    (
                        "{} SLA breach notification(s) {} dispatched."
                        if not dry_run
                        else "{} SLA breach notification(s) would be dispatched."
                    ).format(sla_alerts, "were" if not dry_run else "would be")
                )
            )

    # Scheduling helpers -------------------------------------------------

    def _schedule_heavy_equipment(self, sla_days, dry_run):
        today = timezone.now().date()
        queryset = HeavyEquipmentAsset.objects.exclude(
            status=HeavyEquipmentAssetStatus.retired.id
        ).filter(
            Q(next_service_date__isnull=False, next_service_date__lte=today)
            | Q(
                next_service_hours__isnull=False,
                hours_used__isnull=False,
                hours_used__gte=F("next_service_hours"),
            )
        )
        return sum(
            self._ensure_maintenance_record(
                asset,
                reason="scheduled_service",
                sla_days=sla_days,
                dry_run=dry_run,
                defaults={
                    "expected_completion": asset.next_service_date,
                    "extra_data": {
                        "threshold": {
                            "date": asset.next_service_date.isoformat()
                            if asset.next_service_date
                            else None,
                            "hours": float(asset.next_service_hours or 0),
                        }
                    },
                },
            )
            for asset in queryset
        )

    def _schedule_fleet_assets(self, sla_days, dry_run):
        today = timezone.now().date()
        queryset = FleetAsset.objects.exclude(status=FleetAssetStatus.retired.id).filter(
            Q(next_service_date__isnull=False, next_service_date__lte=today)
            | Q(
                next_service_odometer__isnull=False,
                odometer_km__gte=F("next_service_odometer"),
            )
        )
        return sum(
            self._ensure_maintenance_record(
                asset,
                reason="scheduled_service",
                sla_days=sla_days,
                dry_run=dry_run,
                defaults={
                    "expected_completion": asset.next_service_date,
                    "extra_data": {
                        "threshold": {
                            "date": asset.next_service_date.isoformat()
                            if asset.next_service_date
                            else None,
                            "odometer": asset.next_service_odometer,
                        }
                    },
                },
            )
            for asset in queryset
        )

    def _schedule_drones(self, sla_days, dry_run):
        today = timezone.now().date()
        queryset = DroneAsset.objects.exclude(status=DroneAssetStatus.retired.id).filter(
            Q(next_maintenance_date__isnull=False, next_maintenance_date__lte=today)
            | Q(
                next_maintenance_flight_hours__isnull=False,
                total_flight_hours__gte=F("next_maintenance_flight_hours"),
            )
        )
        return sum(
            self._ensure_maintenance_record(
                asset,
                reason="scheduled_service",
                sla_days=sla_days,
                dry_run=dry_run,
                defaults={
                    "expected_completion": asset.next_maintenance_date,
                    "extra_data": {
                        "threshold": {
                            "date": asset.next_maintenance_date.isoformat()
                            if asset.next_maintenance_date
                            else None,
                            "flight_hours": float(
                                asset.next_maintenance_flight_hours or 0
                            ),
                        }
                    },
                },
            )
            for asset in queryset
        )

    def _schedule_sensors(self, sla_days, dry_run):
        today = timezone.now().date()
        queryset = SensorAsset.objects.exclude(status=SensorAssetStatus.retired.id).filter(
            next_calibration_due__isnull=False,
            next_calibration_due__lte=today,
        )
        return sum(
            self._ensure_maintenance_record(
                asset,
                reason="scheduled_calibration",
                sla_days=sla_days,
                dry_run=dry_run,
                defaults={
                    "expected_completion": asset.next_calibration_due,
                    "record_type": MaintenanceRecordType.calibration.id,
                },
            )
            for asset in queryset
        )

    def _ensure_maintenance_record(self, asset, *, reason, sla_days, dry_run, defaults):
        base_object = getattr(asset, "baseobject_ptr", None) or asset
        open_record = MaintenanceRecord.objects.filter(
            base_object=base_object,
            record_type=defaults.get("record_type", MaintenanceRecordType.maintenance.id),
            status__in=[
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ],
            extra_data__scheduler__exact="auto",
        ).first()
        if open_record:
            return 0

        if dry_run:
            self.stdout.write(f"[DRY-RUN] Would create scheduled maintenance for {asset} ({reason}).")
            return 1

        sla_due = timezone.now() + timedelta(days=sla_days)
        extra = defaults.pop("extra_data", {})
        extra.setdefault("scheduler", "auto")
        with transaction.atomic():
            record = MaintenanceRecord.start_record(
                base_object=base_object,
                record_type=defaults.get(
                    "record_type", MaintenanceRecordType.maintenance.id
                ),
                title="Scheduled maintenance",
                description=f"Automatically generated for {reason.replace('_', ' ')}",
                expected_completion=defaults.get("expected_completion"),
                out_of_service=False,
                reported_by=None,
                performed_by="",
                service_provider=extra.get("service_provider", ""),
                sla_due_at=sla_due,
                extra_data=extra,
            )

        notify_asset_event(
            asset,
            AssetEventType.MAINTENANCE_STARTED,
            payload={
                "record_id": record.pk,
                "auto": True,
                "reason": reason,
                "sla_due_at": sla_due.isoformat(),
            },
            metadata={"source": "schedule_maintenance", "category": reason},
        )
        return 1

    def _check_sla_overdue(self, dry_run):
        now = timezone.now()
        queryset = MaintenanceRecord.objects.filter(
            sla_due_at__isnull=False,
            sla_due_at__lt=now,
            status__in=[
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ],
        ).select_related("base_object")

        alerts = 0
        for record in queryset:
            base_object = record.base_object
            asset = getattr(base_object, "get_real_instance", lambda: base_object)()
            if record.extra_data.get("sla_alerted"):
                continue
            alerts += 1
            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] SLA overdue for {asset} record #{record.pk} (due {record.sla_due_at})."
                )
                continue
        notify_asset_event(
            asset,
            AssetEventType.MAINTENANCE_SLA_OVERDUE,
                payload={
                    "record_id": record.pk,
                    "sla_due_at": record.sla_due_at.isoformat(),
                    "status": record.get_status_display(),
                },
                severity="critical",
                metadata={"source": "schedule_maintenance", "category": "sla"},
            )
            record.extra_data["sla_alerted"] = now.isoformat()
            record.save(update_fields=["extra_data", "modified"])
        return alerts
