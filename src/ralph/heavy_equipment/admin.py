from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.admin.decorators import register
from ralph.admin.mixins import RalphAdmin
from ralph.admin.views.extra import RalphDetailViewAdmin
from ralph.attachments.admin import AttachmentsMixin
from ralph.assets.models.choices import ObjectModelType
from ralph.assets.models.assets import (
    MaintenanceRecordStatus,
    ComplianceRecordStatus,
)
from ralph.assets.admin import (
    MaintenanceRecordInline,
    ComplianceRecordInline,
    DeploymentEntryInline,
    TelemetryReadingInline,
    SafetyChecklistEntryInline,
    AssetIncidentInline,
    WorkOrderInline,
)
from ralph.heavy_equipment.models import (
    HEAVY_EQUIPMENT_GROUP_MAP,
    HeavyEquipmentAsset,
    HeavyEquipmentFunctionalGroup,
    HeavyEquipmentDebrisRemoval,
    HeavyEquipmentMaterialHandling,
    HeavyEquipmentType,
    ExcavatorAsset,
    BulldozerAsset,
    LoaderAsset,
    CraneAsset,
    ForkliftAsset,
    OtherHeavyEquipmentAsset,
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
        equipment_field = self.fields.get("equipment_type")
        if equipment_field:
            equipment_field.choices = [
                choice
                for choice in equipment_field.choices
                if not choice[0]
                or choice[0] in HeavyEquipmentAsset.MACHINERY_TYPES
            ]


class HeavyEquipmentOperationsView(RalphDetailViewAdmin):
    icon = "cogs"
    name = "operations"
    label = _("Operations")
    url_name = "operations"
    inlines = [
        MaintenanceRecordInline,
        WorkOrderInline,
        DeploymentEntryInline,
        SafetyChecklistEntryInline,
        AssetIncidentInline,
        TelemetryReadingInline,
    ]
    summary_fields = [
        "status",
        "deployment_status",
        "hours_used",
        "fuel_level_percent",
        "water_level_percent",
        "battery_level_percent",
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
        "ownership_type",
        "acquisition_vendor",
        "acquired_on",
        "warranty_expiry",
        "lease_expiration",
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
        "fuel_level_threshold_percent",
        "water_level_percent",
        "water_level_threshold_percent",
        "battery_level_percent",
        "battery_level_threshold_percent",
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
        "deployment_status",
        "equipment_identifier",
        "equipment_type",
        "manufacturer",
        "model",
        "ownership_type",
        "owner",
        "user",
        "assigned_location",
        "deployment_site",
        "region",
        "service_env",
        "maintenance_status",
        "compliance_status",
    )
    search_fields = (
        "equipment_identifier",
        "manufacturer",
        "model_name",
        "deployment_site",
        "acquisition_vendor",
        "barcode",
        "hostname",
        "sn",
        "model__name",
    )
    list_filter = (
        "status",
        "equipment_type",
        "deployment_status",
        "ownership_type",
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
    readonly_fields = ("maintenance_status", "compliance_status")
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
            _("Status & Service"),
            {
                "fields": (
                    "status",
                    "deployment_status",
                    "last_status_change",
                    "hours_used",
                    "odometer_km",
                    "maintenance_interval_hours",
                    "maintenance_interval_days",
                    "last_service_date",
                    "next_service_date",
                    "next_service_hours",
                    "maintenance_status",
                    "compliance_status",
                )
            },
        ),
        (
            _("Capacity & Levels"),
            {
                "fields": (
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
                    "hydraulic_oil_capacity_liters",
                    "hydraulic_oil_level_percent",
                    "power_output_kw",
                )
            },
        ),
        (
            _("Deployment"),
            {
                "fields": (
                    "deployment_site",
                    "assigned_location",
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
            _("Financial & Ownership"),
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

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(equipment_type__in=HeavyEquipmentAsset.MACHINERY_TYPES)

    @admin.display(description=_("Maintenance"))
    def maintenance_status(self, obj):
        open_statuses = [
            MaintenanceRecordStatus.open.id,
            MaintenanceRecordStatus.in_progress.id,
        ]
        open_records = obj.maintenance_records.filter(status__in=open_statuses)
        open_count = open_records.count()
        overdue_count = open_records.filter(
            expected_completion__isnull=False,
            expected_completion__lt=timezone.now().date(),
        ).count()
        return _("{open} open / {overdue} overdue").format(
            open=open_count,
            overdue=overdue_count,
        )

    @admin.display(description=_("Compliance"))
    def compliance_status(self, obj):
        records = obj.compliance_records.all()
        due_soon = records.filter(status=ComplianceRecordStatus.due_soon.id).count()
        overdue = records.filter(status=ComplianceRecordStatus.overdue.id).count()
        return _("{soon} due soon / {overdue} overdue").format(
            soon=due_soon,
            overdue=overdue,
        )


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


@register(HeavyEquipmentMaterialHandling)
class HeavyEquipmentMaterialHandlingAdmin(HeavyEquipmentGroupAdmin):
    functional_group_filter = HeavyEquipmentFunctionalGroup.material_handling.id


class HeavyEquipmentTypeAdmin(HeavyEquipmentAssetAdmin):
    equipment_type_filter = None
    change_views = []

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self.equipment_type_filter:
            return queryset.filter(equipment_type=self.equipment_type_filter)
        return queryset.none()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if self.equipment_type_filter and "equipment_type" in form.base_fields:
            field = form.base_fields["equipment_type"]
            field.initial = self.equipment_type_filter
            field.widget = forms.HiddenInput()
        return form

    def save_model(self, request, obj, form, change):
        if self.equipment_type_filter:
            obj.equipment_type = self.equipment_type_filter
        super().save_model(request, obj, form, change)


@register(ExcavatorAsset)
class ExcavatorAssetAdmin(HeavyEquipmentTypeAdmin):
    equipment_type_filter = HeavyEquipmentType.EXCAVATOR


@register(BulldozerAsset)
class BulldozerAssetAdmin(HeavyEquipmentTypeAdmin):
    equipment_type_filter = HeavyEquipmentType.BULLDOZER


@register(LoaderAsset)
class LoaderAssetAdmin(HeavyEquipmentTypeAdmin):
    equipment_type_filter = HeavyEquipmentType.LOADER


@register(CraneAsset)
class CraneAssetAdmin(HeavyEquipmentTypeAdmin):
    equipment_type_filter = HeavyEquipmentType.CRANE


@register(ForkliftAsset)
class ForkliftAssetAdmin(HeavyEquipmentTypeAdmin):
    equipment_type_filter = HeavyEquipmentType.FORKLIFT


@register(OtherHeavyEquipmentAsset)
class OtherHeavyEquipmentAssetAdmin(HeavyEquipmentTypeAdmin):
    equipment_type_filter = HeavyEquipmentType.OTHER
