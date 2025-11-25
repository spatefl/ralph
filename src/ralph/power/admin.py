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
from ralph.power.models import (
    PowerAsset,
    PowerAssetType,
    GeneratorAsset,
    LightTowerAsset,
    BatteryAsset,
    PumpAsset,
)


class PowerAssetAdminForm(HeavyEquipmentAssetAdminForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        equipment_field = self.fields.get("equipment_type")
        if equipment_field:
            equipment_field.widget.attrs["hidden"] = True
            equipment_field.required = False
            equipment_field.initial = HeavyEquipmentType.GENERATOR


class PowerOperationsView(HeavyEquipmentOperationsView):
    label = _("Operations")
    url_name = "operations"
    namespace = None
    summary_fields = [
        "status",
        "deployment_status",
        "hours_used",
        "last_runtime_hours",
        "fuel_level_percent",
        "battery_level_percent",
        "power_output_kw",
        "next_service_date",
    ]


class PowerComplianceView(HeavyEquipmentComplianceView):
    label = _("Compliance")
    url_name = "compliance"
    namespace = None


class PowerDataView(HeavyEquipmentDataView):
    label = _("Telemetry")
    url_name = "telemetry"
    namespace = None


@register(PowerAsset)
class PowerAssetAdmin(HeavyEquipmentAssetAdmin):
    form = PowerAssetAdminForm
    change_views = [
        PowerOperationsView,
        PowerComplianceView,
        PowerDataView,
    ]
    list_display = HeavyEquipmentAssetAdmin.list_display + ("power_asset_type", "supports_three_phase")
    list_filter = HeavyEquipmentAssetAdmin.list_filter + ("power_asset_type", "supports_three_phase")
    fieldsets = (
        (
            _("Identification"),
            {
                "fields": (
                    "hostname",
                    "equipment_identifier",
                    "power_asset_type",
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
                    "maintenance_status",
                    "compliance_status",
                    "last_status_change",
                )
            },
        ),
        (
            _("Runtime & Maintenance"),
            {
                "fields": (
                    "hours_used",
                    "last_runtime_hours",
                    "odometer_km",
                    "maintenance_interval_hours",
                    "maintenance_interval_days",
                    "last_service_date",
                    "next_service_date",
                    "next_service_hours",
                )
            },
        ),
        (
            _("Fuel & Energy"),
            {
                "fields": (
                    "fuel_capacity_liters",
                    "fuel_level_percent",
                    "fuel_level_threshold_percent",
                    "fuel_burn_rate_lph",
                    "battery_capacity_kwh",
                    "battery_level_percent",
                    "battery_level_threshold_percent",
                )
            },
        ),
        (
            _("Power & Output"),
            {
                "fields": (
                    "max_output_kw",
                    "supports_three_phase",
                    "power_output_kw",
                )
            },
        ),
        (
            _("Location & Deployment"),
            {
                "fields": (
                    "org_location",
                    "assigned_location",
                    "deployment_site",
                    "deployed_on",
                    "deployment_notes",
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
        return queryset.filter(equipment_type__in={
            HeavyEquipmentType.GENERATOR,
            HeavyEquipmentType.LIGHT_TOWER,
            HeavyEquipmentType.PUMP,
        })

    def save_model(self, request, obj, form, change):
        if obj.power_asset_type == PowerAssetType.LIGHT_TOWER:
            obj.equipment_type = HeavyEquipmentType.LIGHT_TOWER
        elif obj.power_asset_type == PowerAssetType.PUMP:
            obj.equipment_type = HeavyEquipmentType.PUMP
        else:
            obj.equipment_type = HeavyEquipmentType.GENERATOR
        super().save_model(request, obj, form, change)


class PowerSubtypeAdmin(PowerAssetAdmin):
    power_asset_type = None
    change_views = []

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self.power_asset_type:
            return queryset.filter(power_asset_type=self.power_asset_type)
        return queryset.none()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if self.power_asset_type and "power_asset_type" in form.base_fields:
            field = form.base_fields["power_asset_type"]
            field.initial = self.power_asset_type
            field.widget = forms.HiddenInput()
        return form

    def save_model(self, request, obj, form, change):
        if self.power_asset_type:
            obj.power_asset_type = self.power_asset_type
        super().save_model(request, obj, form, change)


@register(GeneratorAsset)
class GeneratorAssetAdmin(PowerSubtypeAdmin):
    power_asset_type = PowerAssetType.GENERATOR


@register(LightTowerAsset)
class LightTowerAssetAdmin(PowerSubtypeAdmin):
    power_asset_type = PowerAssetType.LIGHT_TOWER


@register(BatteryAsset)
class BatteryAssetAdmin(PowerSubtypeAdmin):
    power_asset_type = PowerAssetType.BATTERY


@register(PumpAsset)
class PumpAssetAdmin(PowerSubtypeAdmin):
    power_asset_type = PowerAssetType.PUMP
