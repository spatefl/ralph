from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ralph.admin.decorators import register
from ralph.heavy_equipment.admin import (
    HeavyEquipmentAssetAdmin,
    HeavyEquipmentAssetAdminForm,
    HeavyEquipmentComplianceView,
    HeavyEquipmentDataView,
    HeavyEquipmentOperationsView,
)
from ralph.heavy_equipment.models import HeavyEquipmentType
from ralph.trailers.models import (
    TrailerAsset,
    CommandTrailer,
    OfficeTrailer,
    RestroomTrailer,
    ShowerTrailer,
    LaundryTrailer,
    SleepingTrailer,
    MedicalTrailer,
    CommunicationsTrailer,
    WaterTrailer,
    StorageTrailer,
    SpecialtyTrailer,
)


class TrailerAssetAdminForm(HeavyEquipmentAssetAdminForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        equipment_field = self.fields.get("equipment_type")
        if equipment_field:
            equipment_field.widget.attrs["hidden"] = True
            equipment_field.required = False
            equipment_field.initial = HeavyEquipmentType.TRAILER


class TrailerOperationsView(HeavyEquipmentOperationsView):
    label = _("Operations")
    url_name = "operations"
    namespace = None
    summary_fields = [
        "status",
        "deployment_status",
        "occupancy_status",
        "occupancy_level_percent",
        "assigned_location",
        "hours_used",
        "fuel_level_percent",
        "water_level_percent",
    ]


class TrailerComplianceView(HeavyEquipmentComplianceView):
    label = _("Compliance")
    url_name = "compliance"
    namespace = None


class TrailerDataView(HeavyEquipmentDataView):
    label = _("Telemetry")
    url_name = "telemetry"
    namespace = None


@register(TrailerAsset)
class TrailerAssetAdmin(HeavyEquipmentAssetAdmin):
    form = TrailerAssetAdminForm
    change_views = [
        TrailerOperationsView,
        TrailerComplianceView,
        TrailerDataView,
    ]

    list_display = HeavyEquipmentAssetAdmin.list_display + ("trailer_subtype", "occupancy_status")
    list_filter = HeavyEquipmentAssetAdmin.list_filter + ("trailer_subtype", "occupancy_status", "has_climate_control")
    fieldsets = (
        (
            _("Identification"),
            {
                "fields": (
                    "hostname",
                    "equipment_identifier",
                    "trailer_subtype",
                    "manufacturer",
                    "model_name",
                    "barcode",
                    "sn",
                    "model",
                )
            },
        ),
        (
            _("Status"),
            {
                "fields": (
                    "status",
                    "deployment_status",
                    "occupancy_status",
                    "maintenance_status",
                    "compliance_status",
                    "last_status_change",
                )
            },
        ),
        (
            _("Location & Service"),
            {
                "fields": (
                    "assigned_location",
                    "deployment_site",
                    "deployed_on",
                    "last_service_visit",
                    "deployment_notes",
                )
            },
        ),
        (
            _("Usage & Maintenance"),
            {
                "fields": (
                    "hours_used",
                    "maintenance_interval_hours",
                    "maintenance_interval_days",
                    "last_service_date",
                    "next_service_date",
                    "next_service_hours",
                )
            },
        ),
        (
            _("Capacity & Levels"),
            {
                "fields": (
                    "occupancy_capacity",
                    "occupancy_level_percent",
                    "occupancy_last_reported_at",
                    "fixtures",
                    "has_climate_control",
                    "has_onboard_generator",
                    "fuel_capacity_liters",
                    "fuel_level_percent",
                    "fuel_level_threshold_percent",
                    "water_tank_capacity_liters",
                    "water_level_percent",
                    "water_level_threshold_percent",
                    "waste_tank_capacity_liters",
                    "waste_level_percent",
                    "battery_capacity_kwh",
                    "battery_level_percent",
                    "battery_level_threshold_percent",
                )
            },
        ),
        (
            _("Assignments"),
            {
                "fields": (
                    "owner",
                    "user",
                    "region",
                    "service_env",
                )
            },
        ),
        (
            _("Financial"),
            {
                "fields": (
                    "ownership_type",
                    "acquisition_vendor",
                    "acquired_on",
                    "acquisition_cost",
                    "lease_expiration",
                    "warranty_expiry",
                    "annual_capex_budget",
                    "annual_opex_budget",
                    "budget_period_start",
                    "price",
                    "invoice_no",
                    "invoice_date",
                    "provider",
                    "order_no",
                    "budget_info",
                    "property_of",
                )
            },
        ),
        (
            _("Notes"),
            {
                "fields": (
                    "remarks",
                    "tags",
                )
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(equipment_type=HeavyEquipmentType.TRAILER)

    def save_model(self, request, obj, form, change):
        obj.equipment_type = HeavyEquipmentType.TRAILER
        super().save_model(request, obj, form, change)


class TrailerSubtypeAdmin(TrailerAssetAdmin):
    trailer_subtype = None
    change_views = []

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self.trailer_subtype:
            return queryset.filter(trailer_subtype=self.trailer_subtype)
        return queryset.none()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if self.trailer_subtype and "trailer_subtype" in form.base_fields:
            field = form.base_fields["trailer_subtype"]
            field.initial = self.trailer_subtype
            field.widget = forms.HiddenInput()
        return form

    def save_model(self, request, obj, form, change):
        if self.trailer_subtype:
            obj.trailer_subtype = self.trailer_subtype
        super().save_model(request, obj, form, change)


@register(CommandTrailer)
class CommandTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = CommandTrailer.subtype


@register(OfficeTrailer)
class OfficeTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = OfficeTrailer.subtype


@register(RestroomTrailer)
class RestroomTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = RestroomTrailer.subtype


@register(ShowerTrailer)
class ShowerTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = ShowerTrailer.subtype


@register(LaundryTrailer)
class LaundryTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = LaundryTrailer.subtype


@register(SleepingTrailer)
class SleepingTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = SleepingTrailer.subtype


@register(MedicalTrailer)
class MedicalTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = MedicalTrailer.subtype


@register(CommunicationsTrailer)
class CommunicationsTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = CommunicationsTrailer.subtype


@register(WaterTrailer)
class WaterTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = WaterTrailer.subtype


@register(StorageTrailer)
class StorageTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = StorageTrailer.subtype


@register(SpecialtyTrailer)
class SpecialtyTrailerAdmin(TrailerSubtypeAdmin):
    trailer_subtype = SpecialtyTrailer.subtype
