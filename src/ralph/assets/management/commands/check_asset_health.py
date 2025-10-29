from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F, Q
from django.utils import timezone

from ralph.assets.models.assets import MaintenanceRecord
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
        "Scan assets and maintenance records for upcoming or overdue actions "
        "and emit notification events via the hook dispatcher."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Look ahead window for upcoming deadlines (default: 7 days).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log findings without dispatching notifications.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional cap on notifications per category to avoid floods.",
        )

    def handle(self, *args, **options):
        window = options["days"]
        dry_run = options["dry_run"]
        limit = options["limit"]

        today = timezone.now().date()
        deadline = today + timedelta(days=window)
        stats = defaultdict(int)

        self.stdout.write(
            f"Scanning maintenance records and assets (deadline <= {deadline})."
        )

        processed_records = set()
        overdue_qs = MaintenanceRecord.objects.overdue().select_related("base_object")
        for record in overdue_qs:
            asset = self._real_asset(record.base_object)
            if asset is None:
                continue
            payload = self._maintenance_payload(record, due_state="overdue")
            self._emit(
                asset,
                AssetEventType.MAINTENANCE_OVERDUE,
                payload,
                stats,
                category="maintenance_overdue",
                dry_run=dry_run,
                limit=limit,
                severity="critical",
            )
            processed_records.add(record.pk)

        upcoming_qs = (
            MaintenanceRecord.objects.due_within(window)
            .exclude(pk__in=processed_records)
            .select_related("base_object")
        )
        for record in upcoming_qs:
            asset = self._real_asset(record.base_object)
            if asset is None:
                continue
            payload = self._maintenance_payload(record, due_state="upcoming")
            self._emit(
                asset,
                AssetEventType.MAINTENANCE_OVERDUE,
                payload,
                stats,
                category="maintenance_upcoming",
                dry_run=dry_run,
                limit=limit,
                severity="warning",
            )

        self._scan_fleet_assets(deadline, window, stats, dry_run, limit)
        self._scan_drones(deadline, stats, dry_run, limit)
        self._scan_heavy_equipment(deadline, stats, dry_run, limit)
        self._scan_sensors(deadline, stats, dry_run, limit)

        total = sum(stats.values())
        verb = "would dispatch" if dry_run else "dispatched"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb.title()} {total} notification(s) across {len(stats)} category(ies)."
            )
        )

    # Maintenance helpers -------------------------------------------------

    def _maintenance_payload(self, record, *, due_state):
        return {
            "record_id": record.pk,
            "record_type": record.get_record_type_display(),
            "status": record.get_status_display(),
            "opened_at": record.opened_at.isoformat()
            if record.opened_at
            else None,
            "expected_completion": record.expected_completion.isoformat()
            if record.expected_completion
            else None,
            "due_state": due_state,
            "out_of_service": record.out_of_service,
        }

    def _real_asset(self, base_object):
        if not base_object:
            return None
        try:
            return base_object.get_real_instance()
        except AttributeError:
            return base_object
        except Exception:  # pragma: no cover - defensive
            return None

    def _emit(
        self,
        asset,
        event_type,
        payload,
        stats,
        *,
        category,
        dry_run,
        limit,
        severity="info",
    ):
        if asset is None:
            return
        if limit is not None and stats[category] >= limit:
            return
        stats[category] += 1
        if dry_run:
            self.stdout.write(f"[DRY-RUN] {category}: {asset} -> {payload}")
            return
        notify_asset_event(
            asset,
            event_type,
            payload=payload,
            severity=severity,
            metadata={"source": "check_asset_health", "category": category},
        )

    # Asset scanners ------------------------------------------------------

    def _scan_fleet_assets(self, deadline, window, stats, dry_run, limit):
        today = timezone.now().date()
        compliance_qs = FleetAsset.compliance_due(within_days=window).select_related(
            "service_env",
            "service_env__service",
            "service_env__environment",
        )
        for asset in compliance_qs:
            for alert in asset.compliance_alerts(within_days=window, reference_date=today):
                payload = {
                    "alert": alert,
                    "due_state": "upcoming"
                    if alert.get("days_until_due", 0) >= 0
                    else "overdue",
                }
                self._emit(
                    asset,
                    AssetEventType.COMPLIANCE_DUE,
                    payload,
                    stats,
                    category="fleet_compliance",
                    dry_run=dry_run,
                    limit=limit,
                    severity="warning",
                )

        service_qs = FleetAsset.objects.exclude(
            status=FleetAssetStatus.retired.id
        ).filter(
            Q(next_service_date__isnull=False, next_service_date__lte=deadline)
            | Q(
                next_service_odometer__isnull=False,
                odometer_km__gte=F("next_service_odometer"),
            )
        )
        for asset in service_qs:
            for alert in asset.service_alerts(reference_date=deadline):
                due_state = (
                    "overdue"
                    if alert.get("days_until_due", 0) < 0
                    or alert.get("overage", 0) > 0
                    else "upcoming"
                )
                payload = {"alert": alert, "due_state": due_state}
                severity = "critical" if due_state == "overdue" else "warning"
                self._emit(
                    asset,
                    AssetEventType.MAINTENANCE_OVERDUE,
                    payload,
                    stats,
                    category="fleet_service",
                    dry_run=dry_run,
                    limit=limit,
                    severity=severity,
                )

    def _scan_drones(self, deadline, stats, dry_run, limit):
        service_qs = DroneAsset.objects.exclude(
            status=DroneAssetStatus.retired.id
        ).filter(
            Q(next_maintenance_date__isnull=False, next_maintenance_date__lte=deadline)
            | Q(
                next_maintenance_flight_hours__isnull=False,
                total_flight_hours__gte=F("next_maintenance_flight_hours"),
            )
        )
        for asset in service_qs:
            for alert in asset.maintenance_alerts(reference_date=deadline):
                due_state = (
                    "overdue"
                    if alert.get("days_until_due", 0) < 0
                    or alert.get("overage", 0) > 0
                    else "upcoming"
                )
                payload = {"alert": alert, "due_state": due_state}
                severity = "critical" if due_state == "overdue" else "warning"
                self._emit(
                    asset,
                    AssetEventType.MAINTENANCE_OVERDUE,
                    payload,
                    stats,
                    category="drone_maintenance",
                    dry_run=dry_run,
                    limit=limit,
                    severity=severity,
                )

        battery_qs = DroneAsset.objects.exclude(
            status=DroneAssetStatus.retired.id
        ).filter(battery_health_percent__isnull=False)
        for asset in battery_qs:
            alert = asset.battery_alert_payload()
            if not alert:
                continue
            payload = {"alert": alert, "due_state": "critical"}
            self._emit(
                asset,
                AssetEventType.THRESHOLD_BREACH,
                payload,
                stats,
                category="drone_battery",
                dry_run=dry_run,
                limit=limit,
                severity="critical",
            )

    def _scan_heavy_equipment(self, deadline, stats, dry_run, limit):
        maintenance_qs = HeavyEquipmentAsset.objects.exclude(
            status=HeavyEquipmentAssetStatus.retired.id
        ).filter(
            Q(next_service_date__isnull=False, next_service_date__lte=deadline)
            | Q(
                next_service_hours__isnull=False,
                hours_used__gte=F("next_service_hours"),
            )
        )
        for asset in maintenance_qs:
            for alert in asset.maintenance_alerts(reference_date=deadline):
                due_state = (
                    "overdue"
                    if alert.get("days_until_due", 0) < 0
                    or alert.get("overage", 0) > 0
                    else "upcoming"
                )
                payload = {"alert": alert, "due_state": due_state}
                severity = "critical" if due_state == "overdue" else "warning"
                self._emit(
                    asset,
                    AssetEventType.MAINTENANCE_OVERDUE,
                    payload,
                    stats,
                    category="heavy_equipment_maintenance",
                    dry_run=dry_run,
                    limit=limit,
                    severity=severity,
                )

        threshold_qs = HeavyEquipmentAsset.objects.exclude(
            status=HeavyEquipmentAssetStatus.retired.id
        ).filter(
            Q(fuel_level_percent__isnull=False)
            | Q(water_level_percent__isnull=False)
            | Q(battery_level_percent__isnull=False)
        )
        for asset in threshold_qs:
            for alert in asset.threshold_alerts():
                payload = {"alert": alert, "due_state": "critical"}
                self._emit(
                    asset,
                    AssetEventType.THRESHOLD_BREACH,
                    payload,
                    stats,
                    category="heavy_equipment_threshold",
                    dry_run=dry_run,
                    limit=limit,
                    severity="critical",
                )

    def _scan_sensors(self, deadline, stats, dry_run, limit):
        maintenance_qs = SensorAsset.objects.exclude(
            status=SensorAssetStatus.retired.id
        ).filter(
            Q(next_calibration_due__isnull=False, next_calibration_due__lte=deadline)
        )
        for asset in maintenance_qs:
            for alert in asset.calibration_alerts(reference_date=deadline):
                due_state = (
                    "overdue"
                    if alert.get("days_until_due", 0) < 0
                    else "upcoming"
                )
                payload = {"alert": alert, "due_state": due_state}
                severity = "critical" if due_state == "overdue" else "warning"
                self._emit(
                    asset,
                    AssetEventType.MAINTENANCE_OVERDUE,
                    payload,
                    stats,
                    category="sensor_calibration",
                    dry_run=dry_run,
                    limit=limit,
                    severity=severity,
                )

        battery_qs = SensorAsset.objects.exclude(
            status=SensorAssetStatus.retired.id
        ).filter(battery_level_percent__isnull=False)
        for asset in battery_qs:
            alert = asset.battery_alert_payload()
            if not alert:
                continue
            payload = {"alert": alert, "due_state": "warning"}
            self._emit(
                asset,
                AssetEventType.THRESHOLD_BREACH,
                payload,
                stats,
                category="sensor_battery",
                dry_run=dry_run,
                limit=limit,
                severity="warning",
            )
