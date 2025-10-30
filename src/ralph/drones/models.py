from decimal import Decimal
from datetime import date, timedelta

from collections import defaultdict

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q, Count, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.accounts.models import Regionalizable, Team
from ralph.assets.models.assets import (
    Asset,
    MaintenanceRecord,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
    DisposalRecord,
    DisposalStatus,
)
from ralph.assets.notifications import AssetEventType, notify_asset_event
from ralph.lib.dj_choices import Choices
from ralph.lib.lifecycle import LifecycleStatusMixin
from ralph.lib.mixins.fields import NullableCharField
from ralph.lib.mixins.models import AdminAbsoluteUrlMixin, TimeStampMixin
from ralph.lib.transitions.decorators import transition_action
from ralph.lib.transitions.fields import TransitionField


def _history_entry(kwargs, instance):
    history_kwargs = kwargs.get("history_kwargs")
    if history_kwargs is None:
        history_kwargs = kwargs["history_kwargs"] = defaultdict(dict)
    history_kwargs.setdefault(instance.pk, {})
    return history_kwargs[instance.pk]


class DroneType(models.TextChoices):
    QUADCOPTER = "quadcopter", _("Quadcopter")
    FIXED_WING = "fixed_wing", _("Fixed-wing")
    VTOL = "vtol", _("VTOL")
    HEXACOPTER = "hexacopter", _("Hexacopter")
    OTHER = "other", _("Other")


class DroneStatus(models.TextChoices):
    OPERATIONAL = "operational", _("Operational")
    GROUNDED = "grounded", _("Grounded")
    AWAITING_CERTIFICATION = "awaiting_certification", _("Awaiting Certification")
    RETIRED = "retired", _("Retired")


class DroneAssetStatus(Choices):
    _ = Choices.Choice

    new = _("new")
    active = _("active")
    under_maintenance = _("under maintenance")
    grounded = _("grounded")
    retired = _("retired")


class DroneMissionProfile(models.TextChoices):
    SURVEY = "survey", _("Survey & mapping")
    SURVEILLANCE = "surveillance", _("Surveillance & security")
    DELIVERY = "delivery", _("Delivery & logistics")
    INSPECTION = "inspection", _("Inspection & maintenance")
    TRAINING = "training", _("Training & testing")
    MULTI_ROLE = "multi_role", _("Multi-role / other")


class DroneAsset(Regionalizable, Asset):
    _allow_in_dashboard = True
    MAINTENANCE_APPROVAL_THRESHOLD = Decimal("2000.00")
    APPROVE_MAINTENANCE_PERMISSION = "drones.approve_drone_maintenance"
    APPROVE_RETIREMENT_PERMISSION = "drones.approve_drone_retirement"

    identifier = NullableCharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("drone identifier"),
    )
    serial_number = NullableCharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("serial number"),
    )
    manufacturer = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("manufacturer"),
    )
    model_name = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("model"),
    )
    drone_type = models.CharField(
        max_length=32,
        choices=DroneType.choices,
        default=DroneType.QUADCOPTER,
        verbose_name=_("type"),
    )
    registration_id = NullableCharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("registration ID"),
    )
    registration_authority = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("registration authority"),
    )
    registration_expires_on = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("registration expiry"),
    )
    airworthiness_certificate_id = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("airworthiness certificate ID"),
    )
    airworthiness_expires_on = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("airworthiness expiry"),
    )
    mission_profile = models.CharField(
        max_length=32,
        choices=DroneMissionProfile.choices,
        default=DroneMissionProfile.MULTI_ROLE,
        verbose_name=_("mission profile"),
    )
    firmware_version = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("firmware version"),
    )
    last_firmware_update = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last firmware update"),
    )
    communication_link_type = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("communication link type"),
    )
    manufacture_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("manufacture year"),
    )
    battery_capacity_mah = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("battery capacity (mAh)"),
    )
    battery_health_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("battery health (%)"),
    )
    battery_low_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("low battery threshold (%)"),
    )
    flight_time_limit_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("flight time limit (minutes)"),
    )
    max_range_km = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("maximum range (km)"),
    )
    max_endurance_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("maximum endurance (minutes)"),
    )
    total_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        default=0,
        verbose_name=_("total flight hours"),
    )
    flight_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("flight count"),
    )
    current_mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("current mission"),
    )
    mission_payload_description = models.CharField(
        max_length=256,
        blank=True,
        verbose_name=_("payload description"),
    )
    max_payload_weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("maximum payload (kg)"),
    )
    airframe_weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("airframe weight (kg)"),
    )
    battery_cycle_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("battery cycle count"),
    )
    payload_mounting = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("payload mount"),
    )
    payload_power_requirements = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("payload power requirements"),
    )
    operator_certificate_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("operator certificate number"),
    )
    pilot_license_required = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("pilot license requirement"),
    )
    insurance_policy_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("insurance policy number"),
    )
    insurance_provider = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("insurance provider"),
    )
    insurance_expiry = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("insurance expiry"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assets_as_owner",
        on_delete=models.CASCADE,
        verbose_name=_("asset owner"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assets_as_operator",
        on_delete=models.CASCADE,
        verbose_name=_("assigned operator"),
    )
    assigned_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="drone_assets",
        on_delete=models.SET_NULL,
        verbose_name=_("assigned team"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("assigned location"),
    )
    last_known_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("last known latitude"),
    )
    last_known_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("last known longitude"),
    )
    last_known_altitude_m = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("last known altitude (m)"),
    )
    home_location_description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("home location"),
    )
    failsafe_behavior = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("failsafe behavior"),
    )
    status = TransitionField(
        default=DroneAssetStatus.new.id,
        choices=DroneAssetStatus(),
    )
    last_status_change = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last status change"),
    )
    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("next maintenance date"),
    )
    last_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last service date"),
    )
    next_maintenance_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("next maintenance flight hours"),
    )
    battery_health_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("battery health threshold (%)"),
    )
    last_inspection_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last inspection date"),
    )
    next_inspection_due = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("next inspection due"),
    )

    @staticmethod
    def _requires_permission(requester, permission_code):
        return requester is not None and not requester.has_perm(permission_code)

    def ensure_approval_ticket(self, action, *, requester=None, description="", extra=None):
        record, created = MaintenanceRecord.ensure_approval_record(
            base_object=self,
            action=action,
            description=description,
            requester=requester,
            extra=extra,
        )
        return record, created

    class Meta:
        verbose_name = _("Drone asset")
        verbose_name_plural = _("Drone assets")
        permissions = [
            (
                "approve_drone_maintenance",
                _("Can approve drone maintenance"),
            ),
            (
                "approve_drone_retirement",
                _("Can approve drone retirement"),
            ),
        ]

    def __str__(self):
        identifier = self.identifier or self.hostname or self.barcode or "-"
        return "{} ({})".format(identifier, self.get_drone_type_display())

    def battery_threshold(self):
        return (
            self.battery_health_threshold_percent
            if self.battery_health_threshold_percent is not None
            else Decimal("20.00")
        )

    def battery_alert_payload(self):
        if self.battery_health_percent is None:
            return None
        threshold = self.battery_threshold()
        if self.battery_health_percent <= threshold:
            return {
                "metric": "battery_health_percent",
                "value": float(self.battery_health_percent),
                "threshold": float(threshold),
            }
        return None

    @property
    def mission_group(self):
        return self.mission_profile or DroneMissionProfile.MULTI_ROLE

    def get_mission_profile_display_value(self):
        try:
            return DroneMissionProfile(self.mission_group).label
        except ValueError:
            return ""

    def maintenance_alerts(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        today = timezone.now().date()
        alerts = []
        if (
            self.next_maintenance_date
            and self.next_maintenance_date <= reference_date
            and self.status != DroneAssetStatus.retired.id
        ):
            days_until = (self.next_maintenance_date - today).days
            alerts.append(
                {
                    "metric": "next_maintenance_date",
                    "value": self.next_maintenance_date.isoformat(),
                    "threshold": reference_date.isoformat(),
                    "days_until_due": days_until,
                }
            )
        if (
            self.next_maintenance_flight_hours is not None
            and self.total_flight_hours >= self.next_maintenance_flight_hours
            and self.status != DroneAssetStatus.retired.id
        ):
            overage = float(self.total_flight_hours - self.next_maintenance_flight_hours)
            alerts.append(
                {
                    "metric": "next_maintenance_flight_hours",
                    "value": float(self.total_flight_hours),
                    "threshold": float(self.next_maintenance_flight_hours),
                    "overage": overage,
                }
            )
        return alerts

    @property
    def disposal_status_display(self):
        record = getattr(self, "disposal_record", None)
        if not record:
            return ""
        return DisposalStatus.from_id(record.status).desc

    @classmethod
    @transition_action(
        verbose_name=_("Activate drone"),
        form_fields={
            "user": {
                "field": forms.CharField(
                    label=_("Assigned operator"),
                    required=False,
                ),
                "autocomplete_field": "user",
            },
            "team": {
                "field": forms.CharField(
                    label=_("Assigned team"),
                    required=False,
                ),
                "autocomplete_field": "assigned_team",
            },
            "assigned_location": {
                "field": forms.CharField(
                    label=_("Assigned location"),
                    required=False,
                )
            },
            "mission": {
                "field": forms.CharField(
                    label=_("Current mission"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )
            },
        },
    )
    def activate_drone_asset(cls, instances, **kwargs):
        user = None
        team = None
        user_id = kwargs.get("user")
        team_id = kwargs.get("team")
        requester = kwargs.get("requester")
        if user_id:
            user = get_user_model().objects.get(pk=int(user_id))
        if team_id:
            team = Team.objects.get(pk=int(team_id))
        location = kwargs.get("assigned_location")
        mission = kwargs.get("mission")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if user is not None:
                instance.user = user
                history[_("Operator")] = str(user)
            if team is not None:
                instance.assigned_team = team
                history[_("Team")] = str(team)
            if location is not None:
                instance.assigned_location = location or ""
                if location:
                    history[_("Location")] = location
            if mission is not None:
                instance.current_mission = mission or ""
                if mission:
                    history[_("Mission")] = mission
            instance.status = DroneAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            notify_asset_event(
                instance,
                AssetEventType.STATUS_ACTIVATED,
                payload={
                    "assigned_user": user.pk if user else None,
                    "assigned_team": team.pk if team else None,
                    "assigned_location": instance.assigned_location or None,
                    "mission": instance.current_mission or None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "activate_drone_asset",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Begin maintenance"),
        form_fields={
            "expected_completion": {
                "field": forms.DateField(
                    label=_("Expected completion date"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "maintenance_note": {
                "field": forms.CharField(
                    label=_("Maintenance note"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
            "performed_by": {
                "field": forms.CharField(
                    label=_("Performed by"),
                    required=False,
                )
            },
            "estimated_cost": {
                "field": forms.DecimalField(
                    label=_("Estimated cost"),
                    required=False,
                    max_digits=12,
                    decimal_places=2,
                    min_value=0,
                )
            },
            "requires_approval": {
                "field": forms.BooleanField(
                    label=_("Flag for manager approval"),
                    required=False,
                )
            },
        },
    )
    def start_drone_maintenance(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        expected = kwargs.get("expected_completion")
        note = kwargs.get("maintenance_note")
        performed_by = kwargs.get("performed_by") or ""
        estimated_cost = kwargs.get("estimated_cost")
        approval_flag = kwargs.get("requires_approval") or False
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if expected:
                history[_("Expected completion")] = expected
                instance.next_maintenance_date = expected
            if note:
                history[_("Note")] = note
            if performed_by:
                history[_("Performed by")] = performed_by
            if estimated_cost is not None:
                history[_("Estimated cost")] = float(estimated_cost)
            instance.status = DroneAssetStatus.under_maintenance.id
            instance.last_status_change = timezone.now().date()
            instance.current_mission = ""
            approval_required = approval_flag
            if (
                estimated_cost is not None
                and estimated_cost >= cls.MAINTENANCE_APPROVAL_THRESHOLD
            ):
                approval_required = True
            needs_manager = approval_required and cls._requires_permission(
                requester, cls.APPROVE_MAINTENANCE_PERMISSION
            )
            record_status = (
                MaintenanceRecordStatus.open.id
                if needs_manager
                else MaintenanceRecordStatus.in_progress.id
            )
            record_extra = {}
            if estimated_cost is not None:
                record_extra["estimated_cost"] = float(estimated_cost)
            record_extra["approval_required"] = bool(needs_manager)
            if performed_by:
                record_extra["performed_by"] = performed_by
            record = MaintenanceRecord.start_record(
                base_object=instance,
                record_type=MaintenanceRecordType.maintenance.id,
                status=record_status,
                description=note or "",
                expected_completion=expected,
                out_of_service=True,
                reported_by=requester,
                performed_by=performed_by,
                extra_data=record_extra,
            )
            history[_("Maintenance record")] = str(record.pk)
            if needs_manager:
                notify_asset_event(
                    instance,
                    AssetEventType.APPROVAL_REQUIRED,
                    payload={
                        "action": "maintenance",
                        "record_id": record.pk,
                        "estimated_cost": float(estimated_cost)
                        if estimated_cost is not None
                        else None,
                    },
                    metadata={
                        "requester": requester.pk if requester else None,
                        "transition": "start_drone_maintenance",
                    },
                )
            notify_asset_event(
                instance,
                AssetEventType.MAINTENANCE_STARTED,
                payload={
                    "record_id": record.pk,
                    "expected_completion": expected.isoformat() if expected else None,
                    "note": note or "",
                    "estimated_cost": float(estimated_cost)
                    if estimated_cost is not None
                    else None,
                    "approval_required": bool(needs_manager),
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "performed_by": performed_by,
                    "transition": "start_drone_maintenance",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Complete maintenance"),
        form_fields={
            "completed_on": {
                "field": forms.DateField(
                    label=_("Completed on"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "flight_hours_after": {
                "field": forms.DecimalField(
                    label=_("Flight hours after service"),
                    required=False,
                    max_digits=7,
                    decimal_places=1,
                    min_value=Decimal("0"),
                )
            },
            "next_maintenance_date": {
                "field": forms.DateField(
                    label=_("Next maintenance date"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "next_maintenance_hours": {
                "field": forms.DecimalField(
                    label=_("Next maintenance flight hours"),
                    required=False,
                    max_digits=7,
                    decimal_places=1,
                    min_value=Decimal("0"),
                )
            },
            "firmware_version": {
                "field": forms.CharField(
                    label=_("Firmware version"),
                    required=False,
                )
            },
            "last_firmware_update": {
                "field": forms.DateField(
                    label=_("Firmware updated on"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "maintenance_summary": {
                "field": forms.CharField(
                    label=_("Maintenance summary"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
            "performed_by": {
                "field": forms.CharField(
                    label=_("Performed by"),
                    required=False,
                )
            },
            "maintenance_cost": {
                "field": forms.DecimalField(
                    label=_("Actual cost"),
                    required=False,
                    max_digits=12,
                    decimal_places=2,
                    min_value=0,
                )
            },
        },
    )
    def complete_drone_maintenance(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        completed_on = kwargs.get("completed_on") or timezone.now().date()
        hours_after = kwargs.get("flight_hours_after")
        next_date = kwargs.get("next_maintenance_date")
        next_hours = kwargs.get("next_maintenance_hours")
        firmware_version = kwargs.get("firmware_version")
        firmware_update = kwargs.get("last_firmware_update")
        summary = kwargs.get("maintenance_summary")
        performed_by = kwargs.get("performed_by")
        cost = kwargs.get("maintenance_cost")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Completed on")] = completed_on
            instance.last_service_date = completed_on
            if hours_after is not None:
                instance.total_flight_hours = hours_after
                history[_("Flight hours")] = float(hours_after)
            if next_date:
                instance.next_maintenance_date = next_date
                history[_("Next maintenance date")] = next_date
            if next_hours is not None:
                instance.next_maintenance_flight_hours = next_hours
                history[_("Next maintenance hours")] = float(next_hours)
            if firmware_version:
                instance.firmware_version = firmware_version
                history[_("Firmware")] = firmware_version
            if firmware_update:
                instance.last_firmware_update = firmware_update
                history[_("Firmware updated on")] = firmware_update
            if summary:
                history[_("Summary")] = summary
            if cost is not None:
                history[_("Cost")] = float(cost)
            if performed_by:
                history[_("Performed by")] = performed_by
            instance.status = DroneAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            extra = {
                "completed_on": completed_on.isoformat(),
                "flight_hours": float(hours_after)
                if hours_after is not None
                else None,
                "next_maintenance_date": next_date.isoformat()
                if next_date
                else None,
                "next_maintenance_hours": float(next_hours)
                if next_hours is not None
                else None,
                "firmware_version": firmware_version,
            }
            if cost is not None:
                extra["actual_cost"] = float(cost)
            record = MaintenanceRecord.close_latest(
                instance,
                record_type=MaintenanceRecordType.maintenance.id,
                resolution=summary,
                extra_data=extra,
                cost=cost,
                performed_by=performed_by
                or (requester.get_full_name() if requester else None),
            )
            notify_asset_event(
                instance,
                AssetEventType.MAINTENANCE_COMPLETED,
                payload={
                    "record_id": record.pk if record else None,
                    "completed_on": completed_on.isoformat(),
                    "summary": summary or "",
                    "next_maintenance_date": next_date.isoformat()
                    if next_date
                    else None,
                    "next_maintenance_hours": float(next_hours)
                    if next_hours is not None
                    else None,
                    "firmware_version": firmware_version,
                    "total_flight_hours": float(hours_after)
                    if hours_after is not None
                    else None,
                    "cost": float(cost) if cost is not None else None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "performed_by": performed_by,
                    "transition": "complete_drone_maintenance",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Ground drone"),
        form_fields={
            "grounding_reason": {
                "field": forms.CharField(
                    label=_("Reason"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
            "estimated_cost": {
                "field": forms.DecimalField(
                    label=_("Estimated repair cost"),
                    required=False,
                    max_digits=12,
                    decimal_places=2,
                    min_value=0,
                )
            },
        },
    )
    def ground_drone_asset(cls, instances, **kwargs):
        reason = kwargs.get("grounding_reason")
        requester = kwargs.get("requester")
        estimated_cost = kwargs.get("estimated_cost")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if reason:
                history[_("Reason")] = reason
            if estimated_cost is not None:
                history[_("Estimated cost")] = float(estimated_cost)
            instance.status = DroneAssetStatus.grounded.id
            instance.last_status_change = timezone.now().date()
            instance.current_mission = ""
            record_extra = {}
            if estimated_cost is not None:
                record_extra["estimated_cost"] = float(estimated_cost)
            needs_manager = (
                estimated_cost is not None
                and estimated_cost >= cls.MAINTENANCE_APPROVAL_THRESHOLD
                and cls._requires_permission(
                    requester, cls.APPROVE_MAINTENANCE_PERMISSION
                )
            )
            record_extra["approval_required"] = bool(needs_manager)
            record = MaintenanceRecord.start_record(
                base_object=instance,
                record_type=MaintenanceRecordType.repair.id,
                status=MaintenanceRecordStatus.open.id,
                description=reason or "",
                out_of_service=True,
                reported_by=requester,
                extra_data=record_extra,
            )
            history[_("Maintenance record")] = str(record.pk)
            if needs_manager:
                notify_asset_event(
                    instance,
                    AssetEventType.APPROVAL_REQUIRED,
                    payload={
                        "action": "ground",
                        "record_id": record.pk,
                        "estimated_cost": float(estimated_cost),
                    },
                    metadata={
                        "requester": requester.pk if requester else None,
                        "transition": "ground_drone_asset",
                    },
                )
            notify_asset_event(
                instance,
                AssetEventType.INCIDENT_DAMAGE,
                payload={
                    "record_id": record.pk,
                    "reason": reason or "",
                    "estimated_cost": float(estimated_cost)
                    if estimated_cost is not None
                    else None,
                },
                severity="warning",
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "ground_drone_asset",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Return to service"),
        form_fields={
            "mission": {
                "field": forms.CharField(
                    label=_("Updated mission"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )
            }
        },
    )
    def return_drone_to_service(cls, instances, **kwargs):
        mission = kwargs.get("mission")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if mission is not None:
                instance.current_mission = mission or ""
                if mission:
                    history[_("Mission")] = mission
            instance.status = DroneAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            MaintenanceRecord.close_open_records(
                instance,
                record_type=MaintenanceRecordType.repair.id,
                resolution=mission or _("Returned to service"),
                performed_by=requester,
            )
            notify_asset_event(
                instance,
                AssetEventType.STATUS_ACTIVATED,
                payload={
                    "mission": mission or "",
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "return_drone_to_service",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Retire drone"),
        form_fields={
            "retired_on": {
                "field": forms.DateField(
                    label=_("Retired on"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "retirement_reason": {
                "field": forms.CharField(
                    label=_("Retirement reason"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
        },
    )
    def retire_drone_asset(cls, instances, **kwargs):
        retired_on = kwargs.get("retired_on") or timezone.now().date()
        reason = kwargs.get("retirement_reason")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Retired on")] = retired_on
            if reason:
                history[_("Reason")] = reason
            approval_needed = cls._requires_permission(
                requester, cls.APPROVE_RETIREMENT_PERMISSION
            )
            approval_record = None
            if approval_needed:
                approval_record, _ = instance.ensure_approval_ticket(
                    action="retire",
                    requester=requester,
                    description=reason or _("Retirement approval requested"),
                    extra={"requested_state": DroneAssetStatus.retired.id},
                )
                history[_("Approval requested")] = _("Pending managerial approval")
            instance.status = DroneAssetStatus.retired.id
            instance.last_status_change = retired_on
            instance.user = None
            instance.assigned_team = None
            instance.assigned_location = ""
            instance.current_mission = ""
            if not approval_needed:
                MaintenanceRecord.close_open_records(
                    instance,
                    record_type=MaintenanceRecordType.approval.id,
                    resolution=reason or _("Retirement approved"),
                    performed_by=requester,
                )
            MaintenanceRecord.close_open_records(
                instance,
                resolution=reason or _("Drone retired"),
                performed_by=requester,
            )
            disposal_record = DisposalRecord.ensure_for_asset(instance)
            history[_("Disposal tasks")] = [
                task.name for task in disposal_record.tasks.filter(is_completed=False)
            ]
            notify_asset_event(
                instance,
                AssetEventType.DISPOSAL_PENDING,
                payload={
                    "disposal_record_id": disposal_record.pk,
                    "status": DisposalStatus.from_id(disposal_record.status).desc,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "retire_drone_asset",
                },
            )
            notify_asset_event(
                instance,
                AssetEventType.STATUS_RETIRED,
                payload={
                    "retired_on": retired_on.isoformat(),
                    "reason": reason or "",
                    "approval_required": approval_needed,
                    "approval_record_id": approval_record.pk if approval_record else None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "retire_drone_asset",
                },
            )
            if approval_needed and approval_record:
                notify_asset_event(
                    instance,
                    AssetEventType.APPROVAL_REQUIRED,
                    payload={
                        "action": "retire",
                        "record_id": approval_record.pk,
                        "reason": reason or "",
                    },
                    metadata={
                        "requester": requester.pk if requester else None,
                        "transition": "retire_drone_asset",
                    },
                )


class DroneAssetMissionManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        return self.model.filtered_queryset(queryset)


class DroneAssetMissionProxyMixin:
    mission_profile_filter = None
    objects = DroneAssetMissionManager()

    @classmethod
    def filtered_queryset(cls, queryset):
        profile = cls.mission_profile_filter
        if not profile:
            return queryset
        return queryset.filter(mission_profile=profile)


class SurveyDroneAsset(DroneAssetMissionProxyMixin, DroneAsset):
    mission_profile_filter = DroneMissionProfile.SURVEY

    class Meta:
        proxy = True
        verbose_name = _("Survey & mapping drone")
        verbose_name_plural = _("Survey & mapping drones")


class SurveillanceDroneAsset(DroneAssetMissionProxyMixin, DroneAsset):
    mission_profile_filter = DroneMissionProfile.SURVEILLANCE

    class Meta:
        proxy = True
        verbose_name = _("Surveillance & security drone")
        verbose_name_plural = _("Surveillance & security drones")


class DeliveryDroneAsset(DroneAssetMissionProxyMixin, DroneAsset):
    mission_profile_filter = DroneMissionProfile.DELIVERY

    class Meta:
        proxy = True
        verbose_name = _("Delivery drone")
        verbose_name_plural = _("Delivery drones")


class InspectionDroneAsset(DroneAssetMissionProxyMixin, DroneAsset):
    mission_profile_filter = DroneMissionProfile.INSPECTION

    class Meta:
        proxy = True
        verbose_name = _("Inspection & maintenance drone")
        verbose_name_plural = _("Inspection & maintenance drones")


class TrainingDroneAsset(DroneAssetMissionProxyMixin, DroneAsset):
    mission_profile_filter = DroneMissionProfile.TRAINING

    class Meta:
        proxy = True
        verbose_name = _("Training & testing drone")
        verbose_name_plural = _("Training & testing drones")


class DroneQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=DroneStatus.OPERATIONAL)

    def due_for_maintenance(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        return self.filter(
            Q(next_maintenance_date__isnull=False, next_maintenance_date__lte=reference_date)
            | Q(
                next_maintenance_flight_hours__isnull=False,
                flight_hours__gte=F("next_maintenance_flight_hours"),
            )
        )


class Drone(LifecycleStatusMixin, AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    identifier = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_("Identifier"),
    )
    model_name = models.CharField(
        max_length=128,
        verbose_name=_("Model"),
    )
    drone_type = models.CharField(
        max_length=32,
        choices=DroneType.choices,
        default=DroneType.QUADCOPTER,
        verbose_name=_("Type"),
    )
    serial_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Serial number"),
    )
    firmware_version = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Firmware version"),
    )
    last_firmware_update = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Last firmware update"),
    )
    status = models.CharField(
        max_length=32,
        choices=DroneStatus.choices,
        default=DroneStatus.AWAITING_CERTIFICATION,
        verbose_name=_("Status"),
    )
    payload_capacity_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Payload capacity (kg)"),
    )
    payload_description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Payload details"),
    )
    flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        default=0,
        verbose_name=_("Flight hours"),
    )
    flight_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Flight count"),
    )
    battery_cycle_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Battery cycle count"),
    )
    last_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Last service date"),
    )
    maintenance_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Maintenance interval (days)"),
    )
    maintenance_interval_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Maintenance interval (flight hours)"),
    )
    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next maintenance date"),
    )
    next_maintenance_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Next maintenance flight hours"),
    )
    registration_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Registration number"),
    )
    pilot_license_required = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Required pilot license"),
    )
    assigned_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="drones",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned team"),
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drones",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned user"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Assigned location"),
    )
    current_mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Current mission"),
    )
    retired_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Retired at"),
    )
    acquisition_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Acquisition date"),
    )
    acquisition_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Acquisition cost"),
    )
    total_maintenance_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total maintenance cost"),
    )
    total_operational_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total operational cost"),
    )
    warranty_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Warranty expiration"),
    )
    service_contract_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Service contract expiration"),
    )
    cost_center = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Cost center"),
    )

    STATUS_TRANSITIONS = {
        DroneStatus.OPERATIONAL: {DroneStatus.GROUNDED, DroneStatus.RETIRED},
        DroneStatus.GROUNDED: {
            DroneStatus.OPERATIONAL,
            DroneStatus.AWAITING_CERTIFICATION,
            DroneStatus.RETIRED,
        },
        DroneStatus.AWAITING_CERTIFICATION: {
            DroneStatus.OPERATIONAL,
            DroneStatus.RETIRED,
        },
        DroneStatus.RETIRED: set(),
    }

    objects = DroneQuerySet.as_manager()

    class Meta:
        verbose_name = _("Drone")
        verbose_name_plural = _("Drones")
        ordering = ("identifier",)

    def __str__(self):
        return "{} ({})".format(self.identifier, self.model_name)

    def pre_status_change(self, old_status, new_status, user, note="", metadata=None):
        metadata = metadata or {}
        updates = []
        if new_status == DroneStatus.RETIRED:
            if self.assigned_user_id:
                self.assigned_user = None
                updates.append("assigned_user")
            self.retired_at = metadata.get("retired_at", date.today())
            updates.append("retired_at")
        if metadata.get("next_maintenance_date"):
            self.next_maintenance_date = metadata["next_maintenance_date"]
            updates.append("next_maintenance_date")
        if metadata.get("next_maintenance_flight_hours") is not None:
            self.next_maintenance_flight_hours = metadata["next_maintenance_flight_hours"]
            updates.append("next_maintenance_flight_hours")
        if metadata.get("firmware_version"):
            self.firmware_version = metadata["firmware_version"]
            updates.append("firmware_version")
            if metadata.get("last_firmware_update"):
                self.last_firmware_update = metadata["last_firmware_update"]
                updates.append("last_firmware_update")
        return updates

    def create_status_log(self, user, old_status, new_status, note="", metadata=None):
        DroneStatusLog.objects.create(
            drone=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=user,
            note=note,
            metadata=metadata or {},
        )

    def assign_to(
        self,
        user=None,
        team=None,
        location="",
        mission="",
        assigned_by=None,
        note="",
    ):
        if self.status != DroneStatus.OPERATIONAL:
            raise ValidationError(
                _("Drone must be operational before assignment.")
            )
        with transaction.atomic():
            DroneAssignment.close_open_assignments(self, assigned_by)
            DroneAssignment.objects.create(
                drone=self,
                assignee=user,
                team=team,
                location=location or "",
                mission=mission or "",
                assigned_by=assigned_by,
                note=note,
            )
            update_fields = []
            if user is not None or self.assigned_user_id:
                self.assigned_user = user
                update_fields.append("assigned_user")
            if team is not None or self.assigned_team_id:
                self.assigned_team = team
                update_fields.append("assigned_team")
            if location is not None:
                self.assigned_location = location or ""
                update_fields.append("assigned_location")
            if mission is not None:
                self.current_mission = mission or ""
                update_fields.append("current_mission")
            if update_fields:
                update_fields.append("modified")
                self.save(update_fields=update_fields)

    def unassign(self, unassigned_by=None, note=""):
        if (
            not self.assigned_user
            and not self.assigned_team
            and not self.assigned_location
            and not self.current_mission
        ):
            return False
        with transaction.atomic():
            DroneAssignment.close_open_assignments(self, unassigned_by, note=note)
            self.assigned_user = None
            self.assigned_team = None
            self.assigned_location = ""
            self.current_mission = ""
            self.save(
                update_fields=[
                    "assigned_user",
                    "assigned_team",
                    "assigned_location",
                    "current_mission",
                    "modified",
                ]
            )
        return True

    def is_maintenance_overdue(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        if self.next_maintenance_date and self.next_maintenance_date <= reference_date:
            return True
        if (
            self.next_maintenance_flight_hours is not None
            and self.flight_hours >= self.next_maintenance_flight_hours
        ):
            return True
        return False

    @property
    def total_cost_of_ownership(self):
        cost = Decimal(self.acquisition_cost or 0)
        return cost + Decimal(self.total_maintenance_cost) + Decimal(
            self.total_operational_cost
        )

class DroneStatusLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="status_logs",
        on_delete=models.CASCADE,
    )
    previous_status = models.CharField(
        max_length=32,
        choices=DroneStatus.choices,
        verbose_name=_("Previous status"),
    )
    new_status = models.CharField(
        max_length=32,
        choices=DroneStatus.choices,
        verbose_name=_("New status"),
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Changed by"),
    )
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Drone status log entry")
        verbose_name_plural = _("Drone status log entries")
        ordering = ("-created",)

    def __str__(self):
        return "{}: {} → {}".format(self.drone, self.previous_status, self.new_status)


class DroneMaintenanceLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="maintenance_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Maintenance date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Flight hours at service"),
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cost"),
    )
    reference = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Reference / ticket"),
    )
    performed_by = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Performed by"),
    )
    firmware_version = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Firmware version"),
    )
    battery_cycles = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Battery cycles"),
    )
    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next maintenance date"),
    )
    next_maintenance_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Next maintenance flight hours"),
    )

    class Meta:
        verbose_name = _("Drone maintenance log")
        verbose_name_plural = _("Drone maintenance logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.drone, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        drone = self.drone
        updates = set()
        if self.next_maintenance_date:
            drone.next_maintenance_date = self.next_maintenance_date
            updates.add("next_maintenance_date")
        elif drone.maintenance_interval_days and self.date:
            drone.next_maintenance_date = self.date + timedelta(
                days=drone.maintenance_interval_days
            )
            updates.add("next_maintenance_date")

        if self.next_maintenance_flight_hours is not None:
            drone.next_maintenance_flight_hours = self.next_maintenance_flight_hours
            updates.add("next_maintenance_flight_hours")
        elif (
            drone.maintenance_interval_flight_hours is not None
            and self.flight_hours is not None
        ):
            drone.next_maintenance_flight_hours = (
                self.flight_hours + drone.maintenance_interval_flight_hours
            )
            updates.add("next_maintenance_flight_hours")

        if self.flight_hours is not None:
            drone.flight_hours = self.flight_hours
            updates.add("flight_hours")

        if self.battery_cycles is not None:
            drone.battery_cycle_count = self.battery_cycles
            updates.add("battery_cycle_count")

        if updates:
            updates.add("modified")
            drone.last_service_date = self.date
            updates.add("last_service_date")
            drone.save(update_fields=list(updates))

        aggregates = drone.maintenance_logs.aggregate(total_cost=Sum("cost"))
        total_cost = aggregates.get("total_cost") or Decimal("0.00")
        if drone.total_maintenance_cost != total_cost:
            drone.total_maintenance_cost = total_cost
            drone.save(update_fields=["total_maintenance_cost", "modified"])


class DroneAssignment(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="assignments",
        on_delete=models.CASCADE,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Assignee"),
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="drone_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Team"),
    )
    location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Location"),
    )
    mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Mission"),
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assignments_created",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned by"),
    )
    unassigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assignments_closed",
        on_delete=models.SET_NULL,
        verbose_name=_("Unassigned by"),
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Drone assignment")
        verbose_name_plural = _("Drone assignments")
        ordering = ("-assigned_at",)

    def __str__(self):
        target = self.assignee or self.team or self.location or "-"
        return "{} → {}".format(self.drone, target)

    @classmethod
    def close_open_assignments(cls, drone, user=None, note=""):
        assignments = (
            cls.objects.select_for_update()
            .filter(drone=drone, unassigned_at__isnull=True)
        )
        now = timezone.now()
        for assignment in assignments:
            assignment.unassigned_at = now
            assignment.unassigned_by = user
            if note:
                assignment.note = (
                    assignment.note + "\n" if assignment.note else ""
                ) + note
            assignment.save(
                update_fields=["unassigned_at", "unassigned_by", "note", "modified"]
            )


class DroneFlightLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="flight_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Flight date"))
    duration_minutes = models.PositiveIntegerField(
        verbose_name=_("Duration (minutes)"),
    )
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Distance (km)"),
    )
    mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Mission"),
    )
    battery_cycles_used = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Battery cycles used"),
    )
    operational_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Operational cost"),
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Recorded by"),
    )

    class Meta:
        verbose_name = _("Drone flight log")
        verbose_name_plural = _("Drone flight logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.drone, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        drone = self.drone
        updates = {"flight_hours", "flight_count", "modified"}
        if self.battery_cycles_used is not None:
            new_cycles = max(drone.battery_cycle_count or 0, self.battery_cycles_used)
            if drone.battery_cycle_count != new_cycles:
                drone.battery_cycle_count = new_cycles
                updates.add("battery_cycle_count")
        aggregates = drone.flight_logs.aggregate(
            total_minutes=Sum("duration_minutes"),
            flights=Count("id"),
        )
        total_minutes = aggregates.get("total_minutes") or 0
        flights = aggregates.get("flights") or 0
        drone.flight_hours = (
            (Decimal(total_minutes) / Decimal("60")) if total_minutes else Decimal("0")
        )
        drone.flight_count = flights
        drone.save(update_fields=list(updates))

        op_aggregates = drone.flight_logs.aggregate(total_cost=Sum("operational_cost"))
        total_cost = op_aggregates.get("total_cost") or Decimal("0.00")
        if drone.total_operational_cost != total_cost:
            drone.total_operational_cost = total_cost
            drone.save(update_fields=["total_operational_cost", "modified"])
