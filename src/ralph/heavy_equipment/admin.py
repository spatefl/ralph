from django.utils.translation import gettext_lazy as _

from ralph.admin.decorators import register
from ralph.admin.mixins import RalphAdmin
from ralph.admin.views.extra import RalphDetailViewAdmin
from ralph.attachments.admin import AttachmentsMixin
from ralph.assets.models.choices import ObjectModelType
from ralph.assets.admin import (
    MaintenanceRecordInline,
    ComplianceRecordInline,
    DeploymentEntryInline,
    TelemetryReadingInline,
)
from ralph.heavy_equipment.models import (
    HEAVY_EQUIPMENT_GROUP_MAP,
    HeavyEquipmentAsset,
    HeavyEquipmentFunctionalGroup,
    HeavyEquipmentDebrisRemoval,
    HeavyEquipmentPowerGeneration,
    HeavyEquipmentWaterManagement,
    HeavyEquipmentMaterialHandling,
)
from ralph.lib.custom_fields.admin import CustomFieldValueAdminMixin
from ralph.lib.mixins.forms import AssetFormMixin, PriceFormMixin
from ralph.lib.transitions.admin import TransitionAdminMixin


class HeavyEquipmentAssetAdminForm(PriceFormMixin, AssetFormMixin, RalphAdmin.form):
    MODEL_TYPE = ObjectModelType.heavy_equipment

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        service_env_field = self.fields.get("service_env")
        if service_env_field:
            service_env_field.required = False


class HeavyEquipmentOperationsView(RalphDetailViewAdmin):
    icon = "cogs"
    name = "operations"
    label = _("Operations")
    url_name = "operations"
    inlines = [MaintenanceRecordInline, DeploymentEntryInline]
    summary_fields = [
        "status",
        "assigned_location",
        "hours_used",
        "odometer_km",
        "next_service_date",
        "next_service_hours",
    ]


class HeavyEquipmentComplianceView(RalphDetailViewAdmin):
    icon = "shield"
    name = "compliance"
    label = _("Compliance")
    url_name = "compliance"
    inlines = [ComplianceRecordInline]
    summary_fields = [
        "last_service_date",
        "next_service_date",
        "assigned_location",
    ]


class HeavyEquipmentDataView(RalphDetailViewAdmin):
    icon = "line-chart"
    name = "data"
    label = _("Telemetry")
    url_name = "telemetry"
    inlines = [TelemetryReadingInline]
    summary_fields = [
        "hours_used",
        "fuel_level_percent",
        "water_level_percent",
        "battery_level_percent",
        "last_status_change",
    ]


@register(HeavyEquipmentAsset)
class HeavyEquipmentAssetAdmin(
    AttachmentsMixin,
    TransitionAdminMixin,
    CustomFieldValueAdminMixin,
    RalphAdmin,
):
    show_transition_history = True
    form = HeavyEquipmentAssetAdminForm
    inlines = [MaintenanceRecordInline]
    list_display = (
        "status",
        "equipment_identifier",
        "equipment_type",
        "manufacturer",
        "model",
        "owner",
        "user",
        "assigned_location",
        "region",
        "service_env",
    )
    search_fields = (
        "equipment_identifier",
        "manufacturer",
        "model_name",
        "barcode",
        "hostname",
        "sn",
        "model__name",
    )
    list_filter = (
        "status",
        "equipment_type",
        "region",
        "owner",
        "user",
        "service_env",
    )
    list_select_related = (
        "model",
        "owner",
        "user",
        "region",
        "service_env",
        "service_env__service",
        "service_env__environment",
    )
    raw_id_fields = (
        "model",
        "owner",
        "user",
        "region",
        "service_env",
        "budget_info",
        "property_of",
    )
    fieldsets = (
        (
            _("Identification"),
            {
                "fields": (
                    "hostname",
                    "equipment_identifier",
                    "equipment_type",
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
                    "last_status_change",
                    "hours_used",
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
            _("Capacity"),
            {
                "fields": (
                    "fuel_capacity_liters",
                    "fuel_level_percent",
                    "water_tank_capacity_liters",
                    "water_level_percent",
                    "battery_capacity_kwh",
                    "battery_level_percent",
                )
            },
        ),
        (
            _("Assignments"),
            {
                "fields": (
                    "owner",
                    "user",
                    "assigned_location",
                    "region",
                    "service_env",
                )
            },
        ),
        (
            _("Financial"),
            {
                "fields": (
                    "price",
                    "currency",
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
            _("Additional"),
            {
                "fields": (
                    "remarks",
                    "tags",
                )
            },
        ),
    )
    change_views = [
        HeavyEquipmentOperationsView,
        HeavyEquipmentComplianceView,
        HeavyEquipmentDataView,
    ]

    def __init__(self, *args, **kwargs):
        self.change_views = list(self.change_views or [])
        super().__init__(*args, **kwargs)


class HeavyEquipmentGroupAdmin(HeavyEquipmentAssetAdmin):
    functional_group_filter = None
    change_views = []

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        group = self.functional_group_filter or getattr(
            self.model, "functional_group_filter", None
        )
        if not group:
            return queryset
        equipment_values = HEAVY_EQUIPMENT_GROUP_MAP.get(group, set())
        if not equipment_values:
            return queryset.none()
        return queryset.filter(equipment_type__in=equipment_values)


@register(HeavyEquipmentDebrisRemoval)
class HeavyEquipmentDebrisRemovalAdmin(HeavyEquipmentGroupAdmin):
    functional_group_filter = HeavyEquipmentFunctionalGroup.debris_removal.id


@register(HeavyEquipmentPowerGeneration)
class HeavyEquipmentPowerGenerationAdmin(HeavyEquipmentGroupAdmin):
    functional_group_filter = HeavyEquipmentFunctionalGroup.power_generation.id


@register(HeavyEquipmentWaterManagement)
class HeavyEquipmentWaterManagementAdmin(HeavyEquipmentGroupAdmin):
    functional_group_filter = HeavyEquipmentFunctionalGroup.water_management.id


@register(HeavyEquipmentMaterialHandling)
class HeavyEquipmentMaterialHandlingAdmin(HeavyEquipmentGroupAdmin):
    functional_group_filter = HeavyEquipmentFunctionalGroup.material_handling.id
