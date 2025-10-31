from collections import defaultdict
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.accounts.models import Regionalizable
from ralph.assets.models.assets import (
    Asset,
    AssetIncidentSeverity,
    MaintenanceRecord,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
    DisposalRecord,
    DisposalStatus,
    SafetyChecklistTrigger,
)
from ralph.assets.notifications import AssetEventType, notify_asset_event
from ralph.assets.services.safety import enforce_checklist, ensure_operator_certification, log_incident
from ralph.lib.dj_choices import Choices
from ralph.lib.mixins.fields import NullableCharField
from ralph.lib.transitions.decorators import transition_action
from ralph.lib.transitions.fields import TransitionField


def _history_entry(kwargs, instance):
    history_kwargs = kwargs.get("history_kwargs")
    if history_kwargs is None:
        history_kwargs = kwargs["history_kwargs"] = defaultdict(dict)
    history_kwargs.setdefault(instance.pk, {})
    return history_kwargs[instance.pk]


class HeavyEquipmentType(models.TextChoices):
    GENERATOR = "generator", _("Generator")
    TRAILER = "trailer", _("Trailer")
    EXCAVATOR = "excavator", _("Excavator")
    BULLDOZER = "bulldozer", _("Bulldozer")
    LOADER = "loader", _("Loader / Skid steer")
    CRANE = "crane", _("Crane")
    FORKLIFT = "forklift", _("Forklift or telehandler")
    LIGHT_TOWER = "light_tower", _("Light tower")
    PUMP = "pump", _("Pump")
    TANK = "tank", _("Tank / Water system")
    OTHER = "other", _("Other")


HEAVY_EQUIPMENT_MACHINERY_TYPES = {
    HeavyEquipmentType.EXCAVATOR,
    HeavyEquipmentType.BULLDOZER,
    HeavyEquipmentType.LOADER,
    HeavyEquipmentType.CRANE,
    HeavyEquipmentType.FORKLIFT,
    HeavyEquipmentType.OTHER,
}

HEAVY_EQUIPMENT_TRAILER_TYPES = {
    HeavyEquipmentType.TRAILER,
    HeavyEquipmentType.TANK,
}

HEAVY_EQUIPMENT_POWER_TYPES = {
    HeavyEquipmentType.GENERATOR,
    HeavyEquipmentType.LIGHT_TOWER,
    HeavyEquipmentType.PUMP,
}


class HeavyEquipmentAssetStatus(Choices):
    _ = Choices.Choice

    new = _("new")
    standby = _("standby")
    active = _("active")
    under_maintenance = _("under maintenance")
    damaged = _("damaged")
    retired = _("retired")


class HeavyEquipmentFunctionalGroup(Choices):
    _ = Choices.Choice

    debris_removal = _("Earthmoving equipment")
    material_handling = _("Material handling & lifting")
    other = _("Miscellaneous heavy equipment")


class HeavyEquipmentOwnershipType(models.TextChoices):
    OWNED = "owned", _("Owned")
    LEASED = "leased", _("Leased")
    RENTED = "rented", _("Rented")
    BORROWED = "borrowed", _("Borrowed / mutual aid")


class HeavyEquipmentDeploymentStatus(models.TextChoices):
    STAGED = "staged", _("Staged / ready")
    DEPLOYED = "deployed", _("Deployed / on-site")
    RETURNING = "returning", _("Returning / demobilizing")
    STORED = "stored", _("Stored / warehouse")


HEAVY_EQUIPMENT_GROUP_MAP = {
    HeavyEquipmentFunctionalGroup.debris_removal.id: {
        HeavyEquipmentType.EXCAVATOR,
        HeavyEquipmentType.BULLDOZER,
        HeavyEquipmentType.LOADER,
    },
    HeavyEquipmentFunctionalGroup.material_handling.id: {
        HeavyEquipmentType.CRANE,
        HeavyEquipmentType.FORKLIFT,
    },
    HeavyEquipmentFunctionalGroup.other.id: {
        HeavyEquipmentType.OTHER,
    },
}


class HeavyEquipmentGroupManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        return self.model.filtered_queryset(queryset)


class HeavyEquipmentAsset(Regionalizable, Asset):
    _allow_in_dashboard = True
    MAINTENANCE_APPROVAL_THRESHOLD = Decimal("5000.00")
    APPROVE_MAINTENANCE_PERMISSION = "heavy_equipment.approve_heavyequipment_maintenance"
    APPROVE_RETIREMENT_PERMISSION = "heavy_equipment.approve_heavyequipment_retirement"

    MACHINERY_TYPES = HEAVY_EQUIPMENT_MACHINERY_TYPES
    TRAILER_TYPES = HEAVY_EQUIPMENT_TRAILER_TYPES
    POWER_TYPES = HEAVY_EQUIPMENT_POWER_TYPES

    equipment_identifier = NullableCharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("equipment identifier"),
    )
    equipment_type = models.CharField(
        max_length=32,
        choices=HeavyEquipmentType.choices,
        default=HeavyEquipmentType.OTHER,
        verbose_name=_("equipment type"),
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
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="heavy_equipment_assets_as_owner",
        on_delete=models.CASCADE,
        verbose_name=_("asset owner"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="heavy_equipment_assets_as_operator",
        on_delete=models.CASCADE,
        verbose_name=_("assigned operator"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("assigned location"),
    )
    fuel_capacity_liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("fuel capacity (L)"),
    )
    fuel_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("fuel level (%)"),
    )
    water_tank_capacity_liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("water tank capacity (L)"),
    )
    water_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("water level (%)"),
    )
    battery_capacity_kwh = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("battery capacity (kWh)"),
    )
    battery_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("battery level (%)"),
    )
    fuel_level_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("fuel level threshold (%)"),
    )
    water_level_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("water level threshold (%)"),
    )
    battery_level_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("battery level threshold (%)"),
    )
    hours_used = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name=_("hours used"),
    )
    odometer_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("odometer (km)"),
    )
    maintenance_interval_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("maintenance interval (hours)"),
    )
    maintenance_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("maintenance interval (days)"),
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
    next_service_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("next service hours"),
    )
    power_output_kw = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("power output (kW)"),
    )
    waste_tank_capacity_liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("waste tank capacity (L)"),
    )
    waste_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("waste level (%)"),
    )
    hydraulic_oil_capacity_liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("hydraulic oil capacity (L)"),
    )
    hydraulic_oil_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("hydraulic oil level (%)"),
    )
    ownership_type = models.CharField(
        max_length=16,
        choices=HeavyEquipmentOwnershipType.choices,
        default=HeavyEquipmentOwnershipType.OWNED,
        verbose_name=_("ownership type"),
    )
    acquisition_vendor = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("acquisition vendor"),
    )
    acquired_on = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("acquired on"),
    )
    acquisition_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("acquisition cost"),
    )
    lease_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("lease expiration"),
    )
    warranty_expiry = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("warranty expiry"),
    )
    deployment_status = models.CharField(
        max_length=16,
        choices=HeavyEquipmentDeploymentStatus.choices,
        default=HeavyEquipmentDeploymentStatus.STAGED,
        verbose_name=_("deployment status"),
    )
    deployment_site = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("deployment site / project"),
    )
    deployed_on = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("last deployed on"),
    )
    deployment_notes = models.TextField(
        blank=True,
        verbose_name=_("deployment notes"),
    )
    status = TransitionField(
        default=HeavyEquipmentAssetStatus.new.id,
        choices=HeavyEquipmentAssetStatus(),
    )
    last_status_change = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last status change"),
    )

    def clean(self):
        super().clean()
        if self.__class__ is HeavyEquipmentAsset and self.equipment_type not in self.MACHINERY_TYPES:
            raise ValidationError(
                {
                    "equipment_type": _(
                        "Use the Trailers or Power & Lighting category for this asset type."
                    )
                }
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
        verbose_name = _("Heavy equipment asset")
        verbose_name_plural = _("Heavy equipment assets")
        permissions = [
            (
                "approve_heavyequipment_maintenance",
                _("Can approve heavy equipment maintenance"),
            ),
            (
                "approve_heavyequipment_retirement",
                _("Can approve heavy equipment retirement"),
            ),
        ]

    def __str__(self):
        identifier = self.equipment_identifier or self.hostname or self.barcode or "-"
        return "{} ({})".format(identifier, self.get_equipment_type_display())

    def fuel_threshold(self):
        return (
            self.fuel_level_threshold_percent
            if self.fuel_level_threshold_percent is not None
            else Decimal("15.00")
        )

    def water_threshold(self):
        return (
            self.water_level_threshold_percent
            if self.water_level_threshold_percent is not None
            else Decimal("20.00")
        )

    def battery_threshold(self):
        return (
            self.battery_level_threshold_percent
            if self.battery_level_threshold_percent is not None
            else Decimal("20.00")
        )

    @property
    def functional_group(self):
        for group, types in HEAVY_EQUIPMENT_GROUP_MAP.items():
            if self.equipment_type in types:
                return group
        return HeavyEquipmentFunctionalGroup.other.id

    def get_functional_group_display(self):
        choice = HeavyEquipmentFunctionalGroup.from_id(self.functional_group)
        return choice.desc if choice else ""

    def threshold_alerts(self):
        alerts = []
        if self.fuel_level_percent is not None:
            threshold = self.fuel_threshold()
            if self.fuel_level_percent <= threshold:
                alerts.append(
                    {
                        "metric": "fuel_level_percent",
                        "value": float(self.fuel_level_percent),
                        "threshold": float(threshold),
                    }
                )
        if self.water_level_percent is not None:
            threshold = self.water_threshold()
            if self.water_level_percent <= threshold:
                alerts.append(
                    {
                        "metric": "water_level_percent",
                        "value": float(self.water_level_percent),
                        "threshold": float(threshold),
                    }
                )
        if self.battery_level_percent is not None:
            threshold = self.battery_threshold()
            if self.battery_level_percent <= threshold:
                alerts.append(
                    {
                        "metric": "battery_level_percent",
                        "value": float(self.battery_level_percent),
                        "threshold": float(threshold),
                    }
                )
        return alerts

    def maintenance_alerts(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        today = timezone.now().date()
        alerts = []
        if (
            self.next_service_date
            and self.next_service_date <= reference_date
            and self.status != HeavyEquipmentAssetStatus.retired.id
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
            self.next_service_hours is not None
            and self.hours_used is not None
            and self.hours_used >= self.next_service_hours
            and self.status != HeavyEquipmentAssetStatus.retired.id
        ):
            overage = float(self.hours_used - self.next_service_hours)
            alerts.append(
                {
                    "metric": "next_service_hours",
                    "value": float(self.hours_used),
                    "threshold": float(self.next_service_hours),
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


class HeavyEquipmentTypeManager(models.Manager):
    def __init__(self, equipment_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.equipment_type = equipment_type

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.equipment_type:
            return queryset.filter(equipment_type=self.equipment_type)
        return queryset.none()


class HeavyEquipmentGroupProxyMixin:
    functional_group_filter = None
    objects = HeavyEquipmentGroupManager()

    @classmethod
    def filtered_queryset(cls, queryset):
        group = cls.functional_group_filter
        if not group:
            return queryset
        equipment_values = HEAVY_EQUIPMENT_GROUP_MAP.get(group, set())
        if not equipment_values:
            return queryset.none()
        return queryset.filter(equipment_type__in=equipment_values)


class HeavyEquipmentDebrisRemoval(HeavyEquipmentGroupProxyMixin, HeavyEquipmentAsset):
    functional_group_filter = HeavyEquipmentFunctionalGroup.debris_removal.id

    class Meta:
        proxy = True
        verbose_name = _("Debris removal equipment")
        verbose_name_plural = _("Debris removal equipment")


class HeavyEquipmentMaterialHandling(
    HeavyEquipmentGroupProxyMixin, HeavyEquipmentAsset
):
    functional_group_filter = HeavyEquipmentFunctionalGroup.material_handling.id

    class Meta:
        proxy = True
        verbose_name = _("Material handling equipment")
        verbose_name_plural = _("Material handling equipment")
    @classmethod
    @transition_action(
        verbose_name=_("Activate asset"),
        form_fields={
            "user": {
                "field": forms.CharField(
                    label=_("Assigned operator"),
                    required=False,
                ),
                "autocomplete_field": "user",
            },
            "owner": {
                "field": forms.CharField(
                    label=_("Owner"),
                    required=False,
                ),
                "autocomplete_field": "owner",
            },
            "assigned_location": {
                "field": forms.CharField(
                    label=_("Assigned location"),
                    required=False,
                )
            },
            "checklist_entry": {
                "field": forms.IntegerField(
                    label=_("Safety checklist entry"),
                    required=False,
                    help_text=_("Provide the ID of a valid activation checklist entry."),
                )
            },
        },
    )
    def activate_heavy_equipment_asset(cls, instances, **kwargs):
        user = None
        owner = None
        user_id = kwargs.get("user")
        owner_id = kwargs.get("owner")
        requester = kwargs.get("requester")
        if user_id:
            user = get_user_model().objects.get(pk=int(user_id))
        if owner_id:
            owner = get_user_model().objects.get(pk=int(owner_id))
        location = kwargs.get("assigned_location")
        checklist_entry_id = kwargs.get("checklist_entry")
        for instance in instances:
            checklist_entry = enforce_checklist(
                instance,
                SafetyChecklistTrigger.activation.id,
                checklist_entry_id,
            )
            history = _history_entry(kwargs, instance)
            if checklist_entry:
                history[_("Checklist entry")] = checklist_entry.pk
            if owner is not None:
                instance.owner = owner
                history[_("Owner")] = str(owner)
            if user is not None:
                ensure_operator_certification(user, instance)
                instance.user = user
                history[_("Operator")] = str(user)
            if location is not None:
                instance.assigned_location = location or ""
                if location:
                    history[_("Location")] = location
            instance.status = HeavyEquipmentAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            MaintenanceRecord.close_open_records(
                instance,
                resolution=_("Asset activated"),
            )
            notify_asset_event(
                instance,
                AssetEventType.STATUS_ACTIVATED,
                payload={
                    "assigned_user": user.pk if user else None,
                    "owner": owner.pk if owner else None,
                    "assigned_location": instance.assigned_location or None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "activate_heavy_equipment_asset",
                },
            )

    @classmethod
    @transition_action(
        verbose_name=_("Stand down asset"),
        form_fields={
            "storage_location": {
                "field": forms.CharField(
                    label=_("Storage location"),
                    required=False,
                )
            }
        },
    )
    def stand_down_heavy_equipment(cls, instances, **kwargs):
        storage_location = kwargs.get("storage_location")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if storage_location is not None:
                instance.assigned_location = storage_location or ""
                if storage_location:
                    history[_("Storage location")] = storage_location
            instance.user = None
            instance.status = HeavyEquipmentAssetStatus.standby.id
            instance.last_status_change = timezone.now().date()

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
    def start_heavy_equipment_maintenance(cls, instances, **kwargs):
        expected = kwargs.get("expected_completion")
        note = kwargs.get("maintenance_note")
        requester = kwargs.get("requester")
        performed_by = kwargs.get("performed_by") or ""
        estimated_cost = kwargs.get("estimated_cost")
        approval_flag = kwargs.get("requires_approval") or False
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if expected:
                instance.next_service_date = expected
                history[_("Expected completion")] = expected
            if note:
                history[_("Note")] = note
            if performed_by:
                history[_("Performed by")] = performed_by
            if estimated_cost is not None:
                history[_("Estimated cost")] = float(estimated_cost)
            instance.status = HeavyEquipmentAssetStatus.under_maintenance.id
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
                        "transition": "start_heavy_equipment_maintenance",
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
                    "transition": "start_heavy_equipment_maintenance",
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
            "hours_used": {
                "field": forms.DecimalField(
                    label=_("Hours used"),
                    required=False,
                    max_digits=10,
                    decimal_places=1,
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
            "next_service_hours": {
                "field": forms.IntegerField(
                    label=_("Next service after hours"),
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
    def complete_heavy_equipment_maintenance(cls, instances, **kwargs):
        completed_on = kwargs.get("completed_on") or timezone.now().date()
        hours_used = kwargs.get("hours_used")
        next_date = kwargs.get("next_service_date")
        next_hours = kwargs.get("next_service_hours")
        summary = kwargs.get("maintenance_summary")
        cost = kwargs.get("maintenance_cost")
        performed_by = kwargs.get("performed_by")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Completed on")] = completed_on
            instance.last_service_date = completed_on
            if hours_used is not None:
                instance.hours_used = hours_used
                history[_("Hours used")] = float(hours_used)
            if next_date:
                instance.next_service_date = next_date
                history[_("Next service date")] = next_date
            if next_hours is not None:
                instance.next_service_hours = next_hours
                history[_("Next service hours")] = next_hours
            if summary:
                history[_("Summary")] = summary
            if cost is not None:
                history[_("Cost")] = float(cost)
            if performed_by:
                history[_("Performed by")] = performed_by
            instance.status = HeavyEquipmentAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            extra = {
                "completed_on": completed_on.isoformat(),
                "hours_used": float(hours_used)
                if hours_used is not None
                else None,
                "next_service_date": next_date.isoformat()
                if next_date
                else None,
                "next_service_hours": next_hours,
            }
            if cost is not None:
                extra["actual_cost"] = float(cost)
            record = MaintenanceRecord.close_latest(
                instance,
                record_type=MaintenanceRecordType.maintenance.id,
                resolution=summary,
                extra_data=extra,
                cost=cost,
                performed_by=performed_by,
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
                    "next_service_hours": next_hours,
                    "hours_used": float(hours_used)
                    if hours_used is not None
                    else None,
                    "cost": float(cost) if cost is not None else None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "complete_heavy_equipment_maintenance",
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
        },
    )
    def report_heavy_equipment_damage(cls, instances, **kwargs):
        note = kwargs.get("damage_note")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if note:
                history[_("Damage note")] = note
            instance.status = HeavyEquipmentAssetStatus.damaged.id
            instance.last_status_change = timezone.now().date()
            incident = log_incident(
                instance,
                _("Damage reported"),
                description=note or "",
                severity=AssetIncidentSeverity.high.id,
                reported_by=requester,
            )
            history[_("Incident")] = incident.pk
            record = MaintenanceRecord.start_record(
                base_object=instance,
                record_type=MaintenanceRecordType.repair.id,
                status=MaintenanceRecordStatus.open.id,
                description=note or "",
                out_of_service=True,
            )
            history[_("Maintenance record")] = str(record.pk)
            notify_asset_event(
                instance,
                AssetEventType.INCIDENT_DAMAGE,
                payload={
                    "record_id": record.pk,
                    "note": note or "",
                },
                severity="warning",
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "report_heavy_equipment_damage",
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
    def retire_heavy_equipment_asset(cls, instances, **kwargs):
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
                    extra={
                        "requested_state": HeavyEquipmentAssetStatus.retired.id,
                    },
                )
                history[_("Approval requested")] = _("Pending managerial approval")
            instance.status = HeavyEquipmentAssetStatus.retired.id
            instance.last_status_change = retired_on
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
                    "transition": "retire_heavy_equipment_asset",
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
                    "transition": "retire_heavy_equipment_asset",
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
                        "transition": "retire_heavy_equipment_asset",
                    },
                )

    @classmethod
    @transition_action(
        verbose_name=_("Log refuel"),
        form_fields={
            "refueled_on": {
                "field": forms.DateField(
                    label=_("Refueled on"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "fuel_added": {
                "field": forms.DecimalField(
                    label=_("Fuel added (L)"),
                    required=False,
                    max_digits=10,
                    decimal_places=2,
                    min_value=0,
                )
            },
            "fuel_level_percent": {
                "field": forms.DecimalField(
                    label=_("New fuel level (%)"),
                    required=False,
                    max_digits=5,
                    decimal_places=2,
                    min_value=0,
                    max_value=100,
                )
            },
            "note": {
                "field": forms.CharField(
                    label=_("Note"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )
            },
            "fuel_cost": {
                "field": forms.DecimalField(
                    label=_("Fuel cost"),
                    required=False,
                    max_digits=10,
                    decimal_places=2,
                    min_value=0,
                )
            },
        },
    )
    def log_heavy_equipment_refuel(cls, instances, **kwargs):
        refueled_on = kwargs.get("refueled_on") or timezone.now().date()
        fuel_added = kwargs.get("fuel_added")
        fuel_level = kwargs.get("fuel_level_percent")
        note = kwargs.get("note")
        fuel_cost = kwargs.get("fuel_cost")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Refueled on")] = refueled_on
            if fuel_added is not None:
                history[_("Fuel added (L)")] = float(fuel_added)
            if fuel_level is not None:
                instance.fuel_level_percent = fuel_level
                history[_("Fuel level (%)")] = float(fuel_level)
            if note:
                history[_("Note")] = note
            if fuel_cost is not None:
                history[_("Fuel cost")] = float(fuel_cost)
            extra = {
                "refueled_on": refueled_on.isoformat(),
                "fuel_added_l": float(fuel_added)
                if fuel_added is not None
                else None,
                "fuel_level_percent": float(fuel_level)
                if fuel_level is not None
                else None,
            }
            if fuel_cost is not None:
                extra["fuel_cost"] = float(fuel_cost)
            MaintenanceRecord.start_record(
                base_object=instance,
                record_type=MaintenanceRecordType.refuel.id,
                status=MaintenanceRecordStatus.completed.id,
                description=note or "",
                extra_data=extra,
            )
            notify_asset_event(
                instance,
                AssetEventType.REFUEL_LOGGED,
                payload={
                    "refueled_on": refueled_on.isoformat(),
                    "fuel_added_l": float(fuel_added)
                    if fuel_added is not None
                    else None,
                    "fuel_level_percent": float(fuel_level)
                    if fuel_level is not None
                    else None,
                    "note": note or "",
                    "fuel_cost": float(fuel_cost) if fuel_cost is not None else None,
                },
                metadata={
                    "requester": requester.pk if requester else None,
                    "transition": "log_heavy_equipment_refuel",
                },
            )


class ExcavatorAsset(HeavyEquipmentAsset):
    objects = HeavyEquipmentTypeManager(HeavyEquipmentType.EXCAVATOR)

    class Meta:
        proxy = True
        verbose_name = _("Excavator")
        verbose_name_plural = _("Excavators")


class BulldozerAsset(HeavyEquipmentAsset):
    objects = HeavyEquipmentTypeManager(HeavyEquipmentType.BULLDOZER)

    class Meta:
        proxy = True
        verbose_name = _("Bulldozer")
        verbose_name_plural = _("Bulldozers")


class LoaderAsset(HeavyEquipmentAsset):
    objects = HeavyEquipmentTypeManager(HeavyEquipmentType.LOADER)

    class Meta:
        proxy = True
        verbose_name = _("Loader / skid steer")
        verbose_name_plural = _("Loaders / skid steers")


class CraneAsset(HeavyEquipmentAsset):
    objects = HeavyEquipmentTypeManager(HeavyEquipmentType.CRANE)

    class Meta:
        proxy = True
        verbose_name = _("Crane")
        verbose_name_plural = _("Cranes")


class ForkliftAsset(HeavyEquipmentAsset):
    objects = HeavyEquipmentTypeManager(HeavyEquipmentType.FORKLIFT)

    class Meta:
        proxy = True
        verbose_name = _("Forklift / telehandler")
        verbose_name_plural = _("Forklifts / telehandlers")


class OtherHeavyEquipmentAsset(HeavyEquipmentAsset):
    objects = HeavyEquipmentTypeManager(HeavyEquipmentType.OTHER)

    class Meta:
        proxy = True
        verbose_name = _("Other heavy equipment")
        verbose_name_plural = _("Other heavy equipment")
