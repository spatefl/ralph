from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ralph.assets.models.assets import (
    ComplianceRecord,
    ComplianceRecordStatus,
    ComplianceTemplate,
)
from ralph.drones.models import DroneAsset
from ralph.fleet.models import FleetAsset
from ralph.heavy_equipment.models import HeavyEquipmentAsset
from ralph.sensors.models import SensorAsset
from ralph.assets.notifications import AssetEventType, notify_asset_event


class Command(BaseCommand):
    help = (
        "Emit notifications for due/overdue compliance records and"
        " instantiate template-driven compliance placeholders."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--warning-days",
            type=int,
            default=7,
            help="Look ahead window before compliance expiry to warn operators.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log actions without modifying the database or dispatching events.",
        )

    def handle(self, *args, **options):
        window = options["warning_days"]
        dry_run = options["dry_run"]

        created = self._apply_templates(dry_run)
        warnings, escalations = self._dispatch_alerts(window, dry_run)

        verb = "would create" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(f"{verb.title()} {created} compliance placeholder(s)."))
        if warnings or escalations:
            self.stdout.write(
                self.style.WARNING(
                    (
                        "{warn} warning(s) and {esc} escalation(s) {} dispatched."
                        if not dry_run
                        else "{warn} warning(s) and {esc} escalation(s) would be dispatched."
                    ).format("were" if not dry_run else "would be")
                    .format(warn=warnings, esc=escalations)
                )
            )

    # Template application -----------------------------------------------

    def _apply_templates(self, dry_run):
        created = 0
        now = timezone.now().date()
        templates = ComplianceTemplate.objects.filter(is_active=True)
        available_models = [HeavyEquipmentAsset, FleetAsset, DroneAsset, SensorAsset]
        for template in templates:
            if template.content_type is not None:
                asset_models = [template.content_type.model_class()]
            else:
                asset_models = available_models
            for model in asset_models:
                assets = model.objects.all()
                for asset in assets:
                    base_object = getattr(asset, "baseobject_ptr", None) or asset
                    next_due = self._next_due_date(base_object, template, default=now)
                    if next_due is None:
                        continue
                    if dry_run:
                        self.stdout.write(
                            f"[DRY-RUN] Would ensure compliance placeholder for {asset} via template {template}."
                        )
                        created += 1
                        continue
                    created += self._create_placeholder(base_object, template, next_due)
        return created

    def _next_due_date(self, base_object, template, default):
        if template.frequency_days is None:
            return default
        latest = (
            ComplianceRecord.objects.filter(base_object=base_object, template=template)
            .order_by("-expires_on")
            .first()
        )
        if latest and latest.expires_on:
            return latest.expires_on + timedelta(days=template.frequency_days)
        return default + timedelta(days=template.frequency_days)

    def _create_placeholder(self, base_object, template, next_due):
        record, created = ComplianceRecord.objects.get_or_create(
            base_object=base_object,
            template=template,
            status=ComplianceRecordStatus.due_soon.id,
            defaults={
                "record_type": template.record_type,
                "title": template.title,
                "description": template.description,
                "expires_on": next_due,
                "extra_data": {"scheduler": "template", "frequency": template.frequency_days},
            },
        )
        if created:
            return 1
        return 0

    # Alerts --------------------------------------------------------------

    def _dispatch_alerts(self, window, dry_run):
        today = timezone.now().date()
        deadline = today + timedelta(days=window)
        warnings = 0
        escalations = 0

        qs = ComplianceRecord.objects.filter(
            status__in=[
                ComplianceRecordStatus.compliant.id,
                ComplianceRecordStatus.due_soon.id,
                ComplianceRecordStatus.overdue.id,
            ]
        ).select_related("base_object")

        for record in qs:
            if not record.expires_on:
                continue
            base_object = record.base_object
            asset = getattr(base_object, "get_real_instance", lambda: base_object)()
            if record.expires_on < today:
                escalations += self._trigger_alert(record, asset, "overdue", dry_run, severity="critical")
            elif record.expires_on <= deadline:
                warnings += self._trigger_alert(record, asset, "upcoming", dry_run, severity="warning")
        return warnings, escalations

    def _trigger_alert(self, record, asset, state, dry_run, *, severity):
        extra_key = "compliance_alerted"
        if record.extra_data.get(extra_key) == state:
            return 0
        payload = {
            "record_id": record.pk,
            "status": record.get_status_display(),
            "title": record.title,
            "due_state": state,
            "expires_on": record.expires_on.isoformat() if record.expires_on else None,
        }
        if dry_run:
            self.stdout.write(
                f"[DRY-RUN] Compliance {state} alert for {asset} record #{record.pk}."
            )
            return 1
        notify_asset_event(
            asset,
            AssetEventType.COMPLIANCE_DUE,
            payload=payload,
            severity=severity,
            metadata={"source": "check_compliance", "state": state},
        )
        record.extra_data["compliance_alerted"] = state
        record.save(update_fields=["extra_data", "modified"])
        return 1
