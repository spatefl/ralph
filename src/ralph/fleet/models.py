from decimal import Decimal
from datetime import date, timedelta

from collections import defaultdict

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.accounts.models import Regionalizable
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


class FleetVehicleType(models.TextChoices):
    CAR = "car", _("Car")
    TRUCK = "truck", _("Truck")
    VAN = "van", _("Van")
    SUV = "suv", _("SUV")
    HEAVY = "heavy", _("Heavy equipment")
    AMBULANCE = "ambulance", _("Ambulance")
    FIRE = "fire", _("Fire / Rescue vehicle")
    COMMAND = "command", _("Command / Support unit")
    BUS = "bus", _("Bus / Shuttle")
    OTHER = "other", _("Other")


class FuelType(models.TextChoices):
    GASOLINE = "gasoline", _("Gasoline")
    DIESEL = "diesel", _("Diesel")
    HYBRID = "hybrid", _("Hybrid")
    ELECTRIC = "electric", _("Electric")
    OTHER = "other", _("Other")


class FleetAssetStatus(Choices):
    _ = Choices.Choice

    new = _("new")
    in_use = _("in use")
    under_maintenance = _("under maintenance")
    damaged = _("damaged")
    retired = _("retired")


class FleetAssetFunctionalGroup(Choices):
    _ = Choices.Choice

    light = _("Light vehicles")
    trucks = _("Trucks & haulers")
    utility = _("Utility & vans")
    emergency = _("Emergency response vehicles")
    passenger = _("Passenger transport")
    specialty = _("Specialty & other vehicles")


FLEET_GROUP_MAP = {
    FleetAssetFunctionalGroup.light.id: {
        FleetVehicleType.CAR,
        FleetVehicleType.SUV,
    },
    FleetAssetFunctionalGroup.trucks.id: {
        FleetVehicleType.TRUCK,
        FleetVehicleType.HEAVY,
    },
    FleetAssetFunctionalGroup.utility.id: {
        FleetVehicleType.VAN,
        FleetVehicleType.COMMAND,
    },
    FleetAssetFunctionalGroup.emergency.id: {
        FleetVehicleType.AMBULANCE,
        FleetVehicleType.FIRE,
    },
    FleetAssetFunctionalGroup.passenger.id: {
        FleetVehicleType.BUS,
    },
    FleetAssetFunctionalGroup.specialty.id: {
        FleetVehicleType.OTHER,
    },
}


class FleetAssetGroupManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        return self.model.filtered_queryset(queryset)


class FleetAsset(Regionalizable, Asset):
    _allow_in_dashboard = True
    MAINTENANCE_APPROVAL_THRESHOLD = Decimal("3000.00")
    APPROVE_MAINTENANCE_PERMISSION = "fleet.approve_fleet_maintenance"
    APPROVE_RETIREMENT_PERMISSION = "fleet.approve_fleet_retirement"

    license_plate = NullableCharField(
        max_length=32,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("license plate"),
    )
    vin = NullableCharField(
        max_length=32,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("vehicle identification number (VIN)"),
    )
    vehicle_type = models.CharField(
        max_length=32,
        choices=FleetVehicleType.choices,
        default=FleetVehicleType.OTHER,
        verbose_name=_("vehicle type"),
    )
    make = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("make"),
    )
    vehicle_model = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("vehicle model"),
    )
    body_style = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("body style"),
    )
    drivetrain = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("drivetrain"),
    )
    color = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("color"),
    )
    seating_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("seating capacity"),
    )
    gross_vehicle_weight_rating_kg = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("GVWR (kg)"),
    )
    manufacture_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("manufacture year"),
    )
    fuel_type = models.CharField(
        max_length=16,
        choices=FuelType.choices,
        default=FuelType.GASOLINE,
        verbose_name=_("fuel type"),
    )
    odometer_km = models.PositiveIntegerField(
        default=0,
        verbose_name=_("odometer (km)"),
    )
    hours_used = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("hours used"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="fleet_assets_as_owner",
        on_delete=models.CASCADE,
        verbose_name=_("asset owner"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="fleet_assets_as_driver",
        on_delete=models.CASCADE,
        verbose_name=_("assigned driver"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("assigned location"),
    )
    registration_expiry = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("registration expiry"),
    )
    inspection_due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("inspection due date"),
    )
    insurance_expiry = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("insurance expiry"),
    )
    insurance_policy_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("insurance policy number"),
    )
    insurance_provider = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("insurance provider"),
    )
    registration_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("registration number"),
    )
    registration_state = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("registration state / region"),
    )
    registration_authority = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("registration authority"),
    )
    emissions_class = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("emissions class"),
    )
    roadworthiness_certificate_expiry = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("roadworthiness certificate expiry"),
    )
    fuel_card_identifier = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("fuel card ID"),
    )
    status = TransitionField(
        default=FleetAssetStatus.new.id,
        choices=FleetAssetStatus(),
    )
    last_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last service date"),
    )
    next_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("next service date"),
    )
    next_service_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("next service odometer (km)"),
    )
    last_status_change = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last status change"),
    )
    last_telematics_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("last telematics update"),
    )
    telematics_device_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("telematics device ID"),
    )
    telematics_provider = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("telematics provider"),
    )
    last_telematics_status = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("last telematics status"),
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
    last_known_heading_deg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(360)],
        verbose_name=_("last known heading (deg)"),
    )
    last_known_speed_kmh = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("last known speed (km/h)"),
    )
    fuel_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("fuel level (%)"),
    )
    engine_hours = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("engine hours"),
    )
    emergency_equipment_inventory = models.TextField(
        blank=True,
        verbose_name=_("emergency equipment inventory"),
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
        verbose_name = _("Fleet asset")
        verbose_name_plural = _("Fleet assets")
        permissions = [
            (
                "approve_fleet_maintenance",
                _("Can approve fleet maintenance"),
            ),
            (
                "approve_fleet_retirement",
                _("Can approve fleet retirement"),
            ),
        ]

    def __str__(self):
        identifier = self.license_plate or self.hostname or self.barcode or "-"
        return "{} ({})".format(identifier, self.get_vehicle_type_display())

    @classmethod
    def compliance_due(cls, within_days=7):
        today = timezone.now().date()
        deadline = today + timedelta(days=within_days)
        return cls.objects.exclude(status=FleetAssetStatus.retired.id).filter(
            models.Q(
                registration_expiry__isnull=False,
                registration_expiry__lte=deadline,
            )
            | models.Q(
                inspection_due_date__isnull=False,
                inspection_due_date__lte=deadline,
            )
            | models.Q(
                insurance_expiry__isnull=False,
                insurance_expiry__lte=deadline,
            )
        )

    def compliance_deadlines(self):
        deadlines = []
        if self.registration_expiry:
            deadlines.append((_("registration"), self.registration_expiry))
        if self.inspection_due_date:
            deadlines.append((_("inspection"), self.inspection_due_date))
        if self.insurance_expiry:
            deadlines.append((_("insurance"), self.insurance_expiry))
        return deadlines

    def compliance_alerts(self, within_days=7, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        deadline = reference_date + timedelta(days=within_days)
        alerts = []
        for label, due_date in self.compliance_deadlines():
            if due_date <= deadline and self.status != FleetAssetStatus.retired.id:
                alerts.append(
                    {
                        "metric": f"{label}",
                        "value": due_date.isoformat(),
                        "threshold": deadline.isoformat(),
                        "days_until_due": (due_date - reference_date).days,
                    }
                )
        return alerts

    @property
    def disposal_status_display(self):
        record = getattr(self, "disposal_record", None)
        if not record:
            return ""
        return DisposalStatus.from_id(record.status).desc


class FleetAssetGroupProxyMixin:
    functional_group_filter = None
    objects = FleetAssetGroupManager()

    @classmethod
    def filtered_queryset(cls, queryset):
        group = cls.functional_group_filter
        if not group:
            return queryset
        vehicle_values = FLEET_GROUP_MAP.get(group, set())
        if not vehicle_values:
            return queryset.none()
        return queryset.filter(vehicle_type__in=vehicle_values)


class FleetLightVehicle(FleetAssetGroupProxyMixin, FleetAsset):
    functional_group_filter = FleetAssetFunctionalGroup.light.id

    class Meta:
        proxy = True
        verbose_name = _("Light vehicle")
        verbose_name_plural = _("Light vehicles")


class FleetTruckHauler(FleetAssetGroupProxyMixin, FleetAsset):
    functional_group_filter = FleetAssetFunctionalGroup.trucks.id

    class Meta:
        proxy = True
        verbose_name = _("Truck or hauler")
        verbose_name_plural = _("Trucks & haulers")


class FleetUtilityVehicle(FleetAssetGroupProxyMixin, FleetAsset):
    functional_group_filter = FleetAssetFunctionalGroup.utility.id

    class Meta:
        proxy = True
        verbose_name = _("Utility vehicle")
        verbose_name_plural = _("Utility vehicles")


class FleetEmergencyVehicle(FleetAssetGroupProxyMixin, FleetAsset):
    functional_group_filter = FleetAssetFunctionalGroup.emergency.id

    class Meta:
        proxy = True
        verbose_name = _("Emergency response vehicle")
        verbose_name_plural = _("Emergency response vehicles")


class FleetPassengerVehicle(FleetAssetGroupProxyMixin, FleetAsset):
    functional_group_filter = FleetAssetFunctionalGroup.passenger.id

    class Meta:
        proxy = True
        verbose_name = _("Passenger transport vehicle")
        verbose_name_plural = _("Passenger transport vehicles")

    def service_alerts(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        today = timezone.now().date()
        alerts = []
        if (
            self.next_service_date
            and self.next_service_date <= reference_date
            and self.status != FleetAssetStatus.retired.id
        ):
            days_until = (self.next_service_date - today).days
            alerts.append(
                {
                    "metric": "next_service_date",
                    "value": self.next_service_date.isoformat(),
                    "threshold": reference_date.isoformat(),
                    "days_until_due": days_until,
                }
            )
        if (
            self.next_service_odometer is not None
            and self.odometer_km >= self.next_service_odometer
            and self.status != FleetAssetStatus.retired.id
        ):
            overage = self.odometer_km - self.next_service_odometer
            alerts.append(
                {
                    "metric": "next_service_odometer",
                    "value": self.odometer_km,
                    "threshold": self.next_service_odometer,
                    "overage": overage,
                }
            )
        return alerts

    @property
    def functional_group(self):
        for group, types in FLEET_GROUP_MAP.items():
            if self.vehicle_type in types:
                return group
        return FleetAssetFunctionalGroup.specialty.id

    def get_functional_group_display(self):
        choice = FleetAssetFunctionalGroup.from_id(self.functional_group)
        return choice.desc if choice else ""

    @classmethod
    @transition_action(
        verbose_name=_("Activate asset"),
        form_fields={
            "user": {
                "field": forms.CharField(
                    label=_("Assigned driver"),
                    required=False,
                ),
                "autocomplete_field": "user",
            },
            "assigned_location": {
                "field": forms.CharField(
                    label=_("Assigned location"),
                    required=False,
                ),
            },
            "initial_odometer": {
                "field": forms.IntegerField(
                    label=_("Current odometer (km)"),
                    required=False,
                    min_value=0,
                )
            },
        },
    )
    def activate_fleet_asset(cls, instances, **kwargs):
        user = None
        user_id = kwargs.get("user")
        requester = kwargs.get("requester")
        if user_id:
            user = get_user_model().objects.get(pk=int(user_id))
        location = kwargs.get("assigned_location")
        initial_odometer = kwargs.get("initial_odometer")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if user is not None:
                instance.user = user
                history[_("Driver")] = str(user)
            if location is not None:
                instance.assigned_location = location or ""
                if location:
                    history[_("Location")] = location
            if initial_odometer is not None:
                instance.odometer_km = initial_odometer
                history[_("Odometer (km)")] = initial_odometer
            instance.status = FleetAssetStatus.in_use.id
            instance.last_status_change = timezone.now().date()
            notify_asset_event(
                instance,
                AssetEventType.STATUS_ACTIVATED,
                payload={
                    "assigned_user": user.pk if user else None,
                    "assigned_location": instance.assigned_location or None,
                    "odometer_km": instance.odometer_km,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "activate_fleet_asset",
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
    def start_fleet_maintenance(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        expected_completion = kwargs.get("expected_completion")
        note = kwargs.get("maintenance_note")
        performed_by = kwargs.get("performed_by") or ""
        estimated_cost = kwargs.get("estimated_cost")
        approval_flag = kwargs.get("requires_approval") or False
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if expected_completion:
                history[_("Expected completion")] = expected_completion
                instance.next_service_date = expected_completion
            if note:
                history[_("Note")] = note
            if performed_by:
                history[_("Performed by")] = performed_by
            if estimated_cost is not None:
                history[_("Estimated cost")] = float(estimated_cost)
            instance.status = FleetAssetStatus.under_maintenance.id
            instance.last_status_change = timezone.now().date()
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
                expected_completion=expected_completion,
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
                        "transition": "start_fleet_maintenance",
                    },
                )
            notify_asset_event(
                instance,
                AssetEventType.MAINTENANCE_STARTED,
                payload={
                    "record_id": record.pk,
                    "expected_completion": expected_completion.isoformat()
                    if expected_completion
                    else None,
                    "note": note or "",
                    "estimated_cost": float(estimated_cost)
                    if estimated_cost is not None
                    else None,
                    "approval_required": bool(needs_manager),
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "performed_by": performed_by,
                    "transition": "start_fleet_maintenance",
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
            "odometer_after_service": {
                "field": forms.IntegerField(
                    label=_("Odometer after service (km)"),
                    required=False,
                    min_value=0,
                )
            },
            "next_service_date": {
                "field": forms.DateField(
                    label=_("Next service date"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "next_service_odometer": {
                "field": forms.IntegerField(
                    label=_("Next service odometer (km)"),
                    required=False,
                    min_value=0,
                )
            },
            "maintenance_summary": {
                "field": forms.CharField(
                    label=_("Maintenance summary"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
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
            "performed_by": {
                "field": forms.CharField(
                    label=_("Performed by"),
                    required=False,
                )
            },
        },
    )
    def complete_fleet_maintenance(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        completed_on = kwargs.get("completed_on") or timezone.now().date()
        odometer = kwargs.get("odometer_after_service")
        next_date = kwargs.get("next_service_date")
        next_odometer = kwargs.get("next_service_odometer")
        summary = kwargs.get("maintenance_summary")
        performed_by = kwargs.get("performed_by")
        cost = kwargs.get("maintenance_cost")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Completed on")] = completed_on
            instance.last_service_date = completed_on
            if odometer is not None:
                instance.odometer_km = odometer
                history[_("Odometer (km)")] = odometer
            if next_date:
                instance.next_service_date = next_date
                history[_("Next service date")] = next_date
            if next_odometer is not None:
                instance.next_service_odometer = next_odometer
                history[_("Next service odometer (km)")] = next_odometer
            if summary:
                history[_("Summary")] = summary
            if cost is not None:
                history[_("Cost")] = float(cost)
            if performed_by:
                history[_("Performed by")] = performed_by
            instance.status = FleetAssetStatus.in_use.id
            instance.last_status_change = timezone.now().date()
            extra = {
                "completed_on": completed_on.isoformat(),
                "odometer_km": odometer,
                "next_service_date": next_date.isoformat()
                if next_date
                else None,
                "next_service_odometer": next_odometer,
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
                    "next_service_date": next_date.isoformat()
                    if next_date
                    else None,
                    "next_service_odometer": next_odometer,
                    "odometer_km": odometer,
                    "cost": float(cost) if cost is not None else None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "performed_by": performed_by,
                    "transition": "complete_fleet_maintenance",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Report damage"),
        form_fields={
            "damage_note": {
                "field": forms.CharField(
                    label=_("Damage description"),
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
    def flag_fleet_damage(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        note = kwargs.get("damage_note")
        estimated_cost = kwargs.get("estimated_cost")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if note:
                history[_("Damage note")] = note
            if estimated_cost is not None:
                history[_("Estimated cost")] = float(estimated_cost)
            instance.status = FleetAssetStatus.damaged.id
            instance.last_status_change = timezone.now().date()
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
                description=note or "",
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
                        "action": "damage_report",
                        "record_id": record.pk,
                        "estimated_cost": float(estimated_cost),
                    },
                    metadata={
                        "requester": requester.pk if requester else None,
                        "transition": "flag_fleet_damage",
                    },
                )
            notify_asset_event(
                instance,
                AssetEventType.INCIDENT_DAMAGE,
                payload={
                    "record_id": record.pk,
                    "note": note or "",
                    "estimated_cost": float(estimated_cost)
                    if estimated_cost is not None
                    else None,
                },
                severity="warning",
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "flag_fleet_damage",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Retire asset"),
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
    def retire_fleet_asset(cls, instances, **kwargs):
        retired_on = kwargs.get("retired_on") or timezone.now().date()
        reason = kwargs.get("retirement_reason")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Retired on")] = retired_on
            instance.last_status_change = retired_on
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
                    extra={"requested_state": FleetAssetStatus.retired.id},
                )
                history[_("Approval requested")] = _("Pending managerial approval")
            instance.status = FleetAssetStatus.retired.id
            instance.user = None
            instance.owner = None
            instance.assigned_location = ""
            if not approval_needed:
                MaintenanceRecord.close_open_records(
                    instance,
                    record_type=MaintenanceRecordType.approval.id,
                    resolution=reason or _("Retirement approved"),
                    performed_by=requester,
                )
            MaintenanceRecord.close_open_records(
                instance,
                resolution=reason or _("Asset retired"),
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
                    "transition": "retire_fleet_asset",
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
                    "transition": "retire_fleet_asset",
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
                        "transition": "retire_fleet_asset",
                    },
                )


class VehicleQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status=VehicleStatus.DECOMMISSIONED)

    def due_for_service(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        return self.filter(
            Q(next_service_date__isnull=False, next_service_date__lte=reference_date)
            | Q(
                next_service_odometer__isnull=False,
                odometer_km__gte=F("next_service_odometer"),
            )
        )


class VehicleStatus(models.TextChoices):
    ORDERED = "ordered", _("Ordered / Purchased")
    IN_SERVICE = "in_service", _("In Service")
    UNDER_MAINTENANCE = "under_maintenance", _("Under Maintenance")
    DECOMMISSIONED = "decommissioned", _("Decommissioned")


class Vehicle(LifecycleStatusMixin, AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vin = models.CharField(
        max_length=17,
        unique=True,
        verbose_name=_("VIN"),
    )
    license_plate = models.CharField(
        max_length=32,
        unique=True,
        verbose_name=_("License plate"),
    )
    make = models.CharField(
        max_length=64,
        verbose_name=_("Make"),
    )
    model_name = models.CharField(
        max_length=64,
        verbose_name=_("Model"),
    )
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2100)],
        verbose_name=_("Year"),
    )
    fuel_type = models.CharField(
        max_length=16,
        choices=FuelType.choices,
        default=FuelType.GASOLINE,
        verbose_name=_("Fuel type"),
    )
    seating_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Seating capacity"),
    )
    cargo_capacity_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cargo capacity (kg)"),
    )
    telematics_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Telematics ID"),
    )
    odometer_km = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Odometer (km)"),
    )
    average_fuel_consumption = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fuel consumption (L/100km)"),
    )
    status = models.CharField(
        max_length=32,
        choices=VehicleStatus.choices,
        default=VehicleStatus.ORDERED,
        verbose_name=_("Status"),
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="fleet_vehicles",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned user"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Assigned location"),
    )
    acquisition_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Acquisition date"),
    )
    purchase_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Purchase cost"),
    )
    depreciation_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Depreciation rate (%)"),
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
    maintenance_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Service interval (days)"),
    )
    maintenance_interval_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Service interval (km)"),
    )
    next_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next service date"),
    )
    next_service_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Next service odometer (km)"),
    )
    decommissioned_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Decommissioned at"),
    )

    STATUS_TRANSITIONS = {
        VehicleStatus.ORDERED: {VehicleStatus.IN_SERVICE, VehicleStatus.DECOMMISSIONED},
        VehicleStatus.IN_SERVICE: {
            VehicleStatus.UNDER_MAINTENANCE,
            VehicleStatus.DECOMMISSIONED,
        },
        VehicleStatus.UNDER_MAINTENANCE: {
            VehicleStatus.IN_SERVICE,
            VehicleStatus.DECOMMISSIONED,
        },
        VehicleStatus.DECOMMISSIONED: set(),
    }

    objects = VehicleQuerySet.as_manager()

    class Meta:
        verbose_name = _("Vehicle")
        verbose_name_plural = _("Vehicles")
        ordering = ("make", "model_name", "license_plate")

    def __str__(self):
        return "{} {} ({})".format(self.make, self.model_name, self.license_plate)

    def pre_status_change(self, old_status, new_status, user, note="", metadata=None):
        metadata = metadata or {}
        updates = []
        if new_status == VehicleStatus.DECOMMISSIONED:
            if self.assigned_user_id:
                self.assigned_user = None
                updates.append("assigned_user")
            self.decommissioned_at = metadata.get("decommissioned_at", date.today())
            updates.append("decommissioned_at")
        if metadata.get("next_service_date"):
            self.next_service_date = metadata["next_service_date"]
            updates.append("next_service_date")
        if metadata.get("next_service_odometer") is not None:
            self.next_service_odometer = metadata["next_service_odometer"]
            updates.append("next_service_odometer")
        return updates

    def create_status_log(self, user, old_status, new_status, note="", metadata=None):
        VehicleStatusLog.objects.create(
            vehicle=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=user,
            note=note,
            metadata=metadata or {},
        )

    def assign_to(self, assignee=None, location="", assigned_by=None, note=""):
        if self.status == VehicleStatus.DECOMMISSIONED:
            raise ValidationError(_("Cannot assign a decommissioned vehicle."))
        with transaction.atomic():
            VehicleAssignment.close_open_assignments(self, assigned_by)
            VehicleAssignment.objects.create(
                vehicle=self,
                assignee=assignee,
                location=location or "",
                assigned_by=assigned_by,
                note=note,
            )
            updated_fields = []
            if assignee is not None or self.assigned_user_id:
                self.assigned_user = assignee
                updated_fields.append("assigned_user")
            if location is not None:
                self.assigned_location = location or ""
                updated_fields.append("assigned_location")
            if updated_fields:
                updated_fields.append("modified")
                self.save(update_fields=updated_fields)

    def unassign(self, unassigned_by=None, note=""):
        if not self.assigned_user and not self.assigned_location:
            return False
        with transaction.atomic():
            VehicleAssignment.close_open_assignments(self, unassigned_by, note=note)
            self.assigned_user = None
            self.assigned_location = ""
            self.save(update_fields=["assigned_user", "assigned_location", "modified"])
        return True

    def is_service_overdue(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        due_date = self.next_service_date
        due_odometer = self.next_service_odometer
        if due_date and due_date <= reference_date:
            return True
        if due_odometer is not None and self.odometer_km >= due_odometer:
            return True
        return False

    @property
    def total_cost_of_ownership(self):
        cost = Decimal(self.purchase_cost or 0)
        return cost + Decimal(self.total_maintenance_cost) + Decimal(
            self.total_operational_cost
        )


class VehicleStatusLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="status_logs",
        on_delete=models.CASCADE,
    )
    previous_status = models.CharField(
        max_length=32,
        choices=VehicleStatus.choices,
        verbose_name=_("Previous status"),
    )
    new_status = models.CharField(
        max_length=32,
        choices=VehicleStatus.choices,
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
        verbose_name = _("Vehicle status log entry")
        verbose_name_plural = _("Vehicle status log entries")
        ordering = ("-created",)

    def __str__(self):
        return "{}: {} → {}".format(self.vehicle, self.previous_status, self.new_status)


class VehicleMaintenanceLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="maintenance_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Maintenance date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    mileage_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Odometer at service (km)"),
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
    next_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next service date"),
    )
    next_service_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Next service odometer (km)"),
    )

    class Meta:
        verbose_name = _("Vehicle maintenance log")
        verbose_name_plural = _("Vehicle maintenance logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.vehicle, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        vehicle = self.vehicle
        updates = set()
        if self.next_service_date:
            vehicle.next_service_date = self.next_service_date
            updates.add("next_service_date")
        elif vehicle.maintenance_interval_days and self.date:
            vehicle.next_service_date = self.date + timedelta(
                days=vehicle.maintenance_interval_days
            )
            updates.add("next_service_date")

        if self.next_service_odometer is not None:
            vehicle.next_service_odometer = self.next_service_odometer
            updates.add("next_service_odometer")
        elif (
            vehicle.maintenance_interval_km
            and self.mileage_km is not None
        ):
            vehicle.next_service_odometer = (
                self.mileage_km + vehicle.maintenance_interval_km
            )
            updates.add("next_service_odometer")

        if self.mileage_km is not None and self.mileage_km >= vehicle.odometer_km:
            vehicle.odometer_km = self.mileage_km
            updates.add("odometer_km")

        if updates:
            updates.add("modified")
            vehicle.save(update_fields=list(updates))

        aggregates = vehicle.maintenance_logs.aggregate(total_cost=Sum("cost"))
        total = aggregates.get("total_cost") or Decimal("0.00")
        if vehicle.total_maintenance_cost != total:
            vehicle.total_maintenance_cost = total
            vehicle.save(update_fields=["total_maintenance_cost", "modified"])


class VehicleAssignment(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="assignments",
        on_delete=models.CASCADE,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="vehicle_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Assignee"),
    )
    location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Location"),
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_created",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned by"),
    )
    unassigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_closed",
        on_delete=models.SET_NULL,
        verbose_name=_("Unassigned by"),
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Vehicle assignment")
        verbose_name_plural = _("Vehicle assignments")
        ordering = ("-assigned_at",)

    @classmethod
    def close_open_assignments(cls, vehicle, user=None, note=""):
        assignments = (
            cls.objects.select_for_update()
            .filter(vehicle=vehicle, unassigned_at__isnull=True)
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

    def __str__(self):
        return "{} → {}".format(self.vehicle, self.assignee or self.location or "-")


class VehicleUsageLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="usage_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Usage date"))
    odometer_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Odometer reading (km)"),
    )
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Distance (km)"),
    )
    fuel_volume_l = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fuel used (L)"),
    )
    fuel_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fuel cost"),
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
        verbose_name = _("Vehicle usage log")
        verbose_name_plural = _("Vehicle usage logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.vehicle, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        vehicle = self.vehicle
        updates = set()
        if self.odometer_km is not None and self.odometer_km >= vehicle.odometer_km:
            vehicle.odometer_km = self.odometer_km
            updates.add("odometer_km")
        if self.distance_km and self.fuel_volume_l and self.distance_km > 0:
            fuel_per_100 = (self.fuel_volume_l / self.distance_km) * Decimal("100")
            vehicle.average_fuel_consumption = fuel_per_100
            updates.add("average_fuel_consumption")
        if updates:
            updates.add("modified")
            vehicle.save(update_fields=list(updates))

        aggregates = vehicle.usage_logs.aggregate(
            total_distance=Sum("distance_km"), total_fuel=Sum("fuel_volume_l")
        )
        total_distance = aggregates.get("total_distance")
        total_fuel = aggregates.get("total_fuel")
        if total_distance and total_fuel and total_distance > 0:
            avg = (total_fuel / total_distance) * Decimal("100")
            if vehicle.average_fuel_consumption != avg:
                vehicle.average_fuel_consumption = avg
                vehicle.save(update_fields=["average_fuel_consumption", "modified"])

        op_aggregates = vehicle.usage_logs.aggregate(total_cost=Sum("fuel_cost"))
        total_cost = op_aggregates.get("total_cost") or Decimal("0.00")
        if vehicle.total_operational_cost != total_cost:
            vehicle.total_operational_cost = total_cost
            vehicle.save(update_fields=["total_operational_cost", "modified"])
