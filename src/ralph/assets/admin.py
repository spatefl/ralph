# -*- coding: utf-8 -*-
from django.contrib import admin
from django.db.models import Count
from django.forms import BaseInlineFormSet
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from ralph.admin.decorators import register
from ralph.admin.mixins import RalphAdmin, RalphMPTTAdmin, RalphTabularInline
from ralph.admin.views.extra import RalphDetailView
from ralph.assets.models.assets import (
    Asset,
    AssetHolder,
    AssetModel,
    MaintenanceRecord,
    MaintenancePartUsage,
    SafetyChecklistTemplate,
    SafetyChecklistItem,
    SafetyChecklistEntry,
    SafetyChecklistResponse,
    OperatorCertification,
    AssetIncident,
    AssetIncidentTask,
    SparePart,
    SparePartCategory,
    SparePartStock,
    IntegrationEndpoint,
    IntegrationEndpointType,
    IntegrationDeliveryLog,
    IntegrationDeliveryStatus,
    SLAPolicy,
    ComplianceRecord,
    ComplianceTemplate,
    ReportConfig,
    DisposalRecord,
    DisposalTask,
    DisposalTemplate,
    DisposalTemplateTask,
    DeploymentEntry,
    DeploymentAssignment,
    TelemetryReading,
    WorkOrder,
    WorkOrderTask,
    BudgetInfo,
    BusinessSegment,
    Category,
    Environment,
    Manufacturer,
    ManufacturerKind,
    ProfitCenter,
    Service,
    ServiceEnvironment,
)
from ralph.assets.models.base import BaseObject
from ralph.assets.models.components import (
    ComponentModel,
    Disk,
    Ethernet,
    FibreChannelCard,
    GenericComponent,
    Memory,
    Processor,
)
from ralph.assets.models.configuration import ConfigurationClass, ConfigurationModule
from ralph.data_importer import resources
from ralph.lib.custom_fields.admin import CustomFieldValueAdminMixin
from ralph.lib.table.table import Table, TableWithUrl


@register(ConfigurationClass)
class ConfigurationClassAdmin(CustomFieldValueAdminMixin, RalphAdmin):
    fields = ["class_name", "module", "path"]
    readonly_fields = ["path"]
    raw_id_fields = ["module"]
    search_fields = [
        "path",
    ]
    list_display = ["class_name", "module", "path", "objects_count"]
    list_select_related = ["module"]
    list_filter = ["class_name", "module"]
    show_custom_fields_values_summary = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(objects_count=Count("baseobject"))
        return qs

    def objects_count(self, instance):
        return instance.objects_count

    objects_count.short_description = _("Objects count")
    objects_count.admin_order_field = "objects_count"

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ["class_name", "module"]
        return self.readonly_fields


@register(ConfigurationModule)
class ConfigurationModuleAdmin(CustomFieldValueAdminMixin, RalphMPTTAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    readonly_fields = ["show_children_modules", "show_children_classes"]
    raw_id_fields = ["parent"]
    fieldsets = (
        (_("Basic info"), {"fields": ["name", "parent", "support_team"]}),
        (
            _("Relations"),
            {"fields": ["show_children_modules", "show_children_classes"]},
        ),
    )
    show_custom_fields_values_summary = False

    @mark_safe
    def show_children_modules(self, module):
        if not module or not module.pk:
            return "&ndash;"
        return TableWithUrl(
            module.children_modules.all(), ["name"], url_field="name"
        ).render()

    show_children_modules.short_description = _("Children modules")

    @mark_safe
    def show_children_classes(self, module):
        if not module or not module.pk:
            return "&ndash;"
        return TableWithUrl(
            module.configuration_classes.all(), ["class_name"], url_field="class_name"
        ).render()

    show_children_classes.short_description = _("Children classes")

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ["name", "parent"]
        return self.readonly_fields


@register(ServiceEnvironment)
class ServiceEnvironmentAdmin(CustomFieldValueAdminMixin, RalphAdmin):
    show_custom_fields_values_summary = False
    search_fields = ["service__name", "environment__name"]
    list_select_related = ["service", "environment"]
    raw_id_fields = ["service", "environment"]
    resource_classes = [resources.ServiceEnvironmentResource]
    fields = ("service", "environment", "remarks", "tags")


class PolymorphicInlineFormset(BaseInlineFormSet):
    def get_queryset(self):
        return super().get_queryset()[:]


class ServiceEnvironmentInline(RalphTabularInline):
    model = ServiceEnvironment
    raw_id_fields = ["environment"]
    fields = ("environment",)
    min_num = 1
    formset = PolymorphicInlineFormset


class BaseObjectsList(Table):
    def url(self, item):
        return '<a href="{}">{}</a>'.format(item.get_absolute_url(), _("Go to object"))

    url.title = _("Link")

    def _str(self, item):
        return str(item)

    _str.title = _("object")


class ServiceBaseObjects(RalphDetailView):
    icon = "bookmark"
    name = "service_base_objects"
    label = _("Objects")
    url_name = "service_base_objects"

    def get_service_base_objects_queryset(self):
        return (
            BaseObject.polymorphic_objects.filter(service_env__service=self.object)
            .select_related("service_env__environment", "content_type")
            .exclude(content_type__model="vip")  # TODO remove after vip deletion
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_objects_list"] = BaseObjectsList(
            self.get_service_base_objects_queryset(),
            [
                "id",
                ("content_type", _("type")),
                ("service_env__environment", _("environment")),
                "_str",
                "url",
            ],
        )
        return context

    def get_object(self, model, pk):
        if pk.isdigit():
            query = {"pk": pk}
        else:
            query = {"uid": pk}

        return model.objects.get(**query)

    @classmethod
    def get_url_pattern(cls, model):
        return r"^{}/{}/(?P<pk>[\w-]+)/{}/$".format(
            model._meta.app_label, model._meta.model_name, cls.url_name
        )


@register(MaintenanceRecord)
class MaintenanceRecordAdmin(RalphAdmin):
    class MaintenancePartUsageInline(RalphTabularInline):
        model = MaintenancePartUsage
        extra = 0
        fields = (
            "part",
            "stock",
            "quantity_used",
            "unit_cost",
            "extended_cost_display",
            "notes",
            "modified",
        )
        readonly_fields = ("extended_cost_display", "modified")
        raw_id_fields = ("part", "stock")

        def extended_cost_display(self, instance):
            return instance.extended_cost

        extended_cost_display.short_description = _("Extended cost")

    list_display = (
        "base_object",
        "record_type_display",
        "status_display",
        "opened_at",
        "expected_completion",
        "closed_at",
        "service_provider",
        "sla_due_at",
        "is_sla_overdue",
        "out_of_service",
    )
    list_filter = ("record_type", "status", "out_of_service", "service_provider")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "description",
        "resolution",
    )
    raw_id_fields = ("base_object", "reported_by", "closed_by")
    readonly_fields = ("created", "modified", "is_sla_overdue")
    inlines = [MaintenancePartUsageInline]

    def record_type_display(self, instance):
        return instance.get_record_type_display()

    record_type_display.short_description = _("Type")

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")

    @admin.display(boolean=True, description=_("SLA overdue"))
    def is_sla_overdue(self, instance):
        return instance.is_sla_overdue


class MaintenanceRecordInline(RalphTabularInline):
    model = MaintenanceRecord
    fk_name = "base_object"
    extra = 0
    fields = (
        "record_type_display",
        "status_display",
        "opened_at",
        "expected_completion",
        "closed_at",
        "reported_by",
        "performed_by",
        "service_provider",
        "sla_due_at",
        "closed_by",
        "closure_notes",
        "closure_acknowledged",
        "closure_acknowledged_at",
        "cost",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def record_type_display(self, instance):
        return instance.get_record_type_display()

    record_type_display.short_description = _("Type")

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


class SparePartStockInline(RalphTabularInline):
    model = SparePartStock
    extra = 0
    fields = (
        "location",
        "quantity_on_hand",
        "quantity_reserved",
        "reorder_point",
        "reorder_quantity",
        "last_restocked_at",
        "is_active",
    )
    readonly_fields = ("last_restocked_at",)


@register(SparePartCategory)
class SparePartCategoryAdmin(RalphAdmin):
    list_display = ("name", "description", "created", "modified")
    search_fields = ("name", "description")


@register(SparePart)
class SparePartAdmin(RalphAdmin):
    list_display = (
        "display_name",
        "category",
        "vendor_name",
        "unit_cost",
        "restock_threshold",
        "restock_quantity",
        "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "sku", "vendor_name", "vendor_sku", "external_reference")
    inlines = [SparePartStockInline]


@register(SparePartStock)
class SparePartStockAdmin(RalphAdmin):
    list_display = (
        "part",
        "location",
        "quantity_on_hand",
        "quantity_reserved",
        "reorder_point",
        "reorder_quantity",
        "last_restocked_at",
        "is_active",
    )
    list_filter = ("is_active", "location")
    search_fields = ("part__name", "part__sku", "location")
    raw_id_fields = ("part",)


@register(MaintenancePartUsage)
class MaintenancePartUsageAdmin(RalphAdmin):
    list_display = (
        "maintenance_record",
        "part",
        "stock",
        "quantity_used",
        "effective_unit_cost",
        "extended_cost",
        "created",
    )
    search_fields = (
        "maintenance_record__base_object__hostname",
        "maintenance_record__base_object__barcode",
        "part__name",
        "part__sku",
    )
    list_filter = ("part",)
    raw_id_fields = ("maintenance_record", "part", "stock")
    readonly_fields = ("extended_cost", "created", "modified")


class SafetyChecklistItemInline(RalphTabularInline):
    model = SafetyChecklistItem
    extra = 0
    fields = ("prompt", "item_type", "is_required", "require_attachment")


@register(SafetyChecklistTemplate)
class SafetyChecklistTemplateAdmin(RalphAdmin):
    list_display = (
        "name",
        "trigger",
        "content_type",
        "validity_period_hours",
        "is_active",
    )
    list_filter = ("trigger", "is_active")
    search_fields = ("name", "notes")
    inlines = [SafetyChecklistItemInline]


class SafetyChecklistResponseInline(RalphTabularInline):
    model = SafetyChecklistResponse
    extra = 0
    fields = (
        "item",
        "value_boolean",
        "value_text",
        "value_decimal",
        "created",
    )
    readonly_fields = ("created",)
    raw_id_fields = ("item",)


@register(SafetyChecklistEntry)
class SafetyChecklistEntryAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "template",
        "status",
        "completed_by",
        "completed_at",
    )
    list_filter = ("status", "template__trigger")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "template__name",
    )
    raw_id_fields = ("base_object", "template", "completed_by")
    readonly_fields = ("created", "modified")
    inlines = [SafetyChecklistResponseInline]


@register(OperatorCertification)
class OperatorCertificationAdmin(RalphAdmin):
    list_display = (
        "user",
        "name",
        "content_type",
        "issued_on",
        "expires_on",
        "is_active",
    )
    list_filter = ("is_active", "content_type")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "name",
    )
    raw_id_fields = ("user",)
    readonly_fields = ("created", "modified")


class AssetIncidentTaskInline(RalphTabularInline):
    model = AssetIncidentTask
    extra = 0
    fields = ("description", "due_at", "completed_at", "completed_by")
    raw_id_fields = ("completed_by",)


@register(AssetIncident)
class AssetIncidentAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "title",
        "severity",
        "status",
        "opened_at",
        "closed_at",
        "reported_by",
        "assigned_to",
    )
    list_filter = ("severity", "status")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "title",
        "description",
    )
    raw_id_fields = ("base_object", "reported_by", "assigned_to")
    readonly_fields = ("created", "modified")
    inlines = [AssetIncidentTaskInline]


@register(AssetIncidentTask)
class AssetIncidentTaskAdmin(RalphAdmin):
    list_display = ("incident", "description", "due_at", "completed_at", "completed_by")
    search_fields = ("incident__title", "description")
    raw_id_fields = ("incident", "completed_by")
    readonly_fields = ("created", "modified")


@register(IntegrationEndpoint)
class IntegrationEndpointAdmin(RalphAdmin):
    list_display = (
        "name",
        "endpoint_type",
        "target_url",
        "queue_name",
        "enabled",
    )
    list_filter = ("endpoint_type", "enabled")
    search_fields = ("name", "target_url", "queue_name")
    readonly_fields = ("created", "modified")


@register(IntegrationDeliveryLog)
class IntegrationDeliveryLogAdmin(RalphAdmin):
    list_display = ("endpoint", "event_type", "status", "response_code", "created")
    list_filter = ("status", "event_type")
    search_fields = ("endpoint__name", "event_type")
    readonly_fields = ("created", "modified", "metadata")
    raw_id_fields = ("endpoint",)


@register(SLAPolicy)
class SLAPolicyAdmin(RalphAdmin):
    list_display = (
        "name",
        "content_type",
        "target_response_hours",
        "target_resolution_hours",
        "is_active",
    )
    list_filter = ("is_active", "content_type")
    search_fields = ("name", "description")
    readonly_fields = ("created", "modified")


@register(ComplianceRecord)
class ComplianceRecordAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "record_type_display",
        "title",
        "status_display",
        "performed_on",
        "expires_on",
        "template",
        "document_link",
    )
    list_filter = ("record_type", "status", "expires_on", "template")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "title",
        "reference",
        "description",
    )
    raw_id_fields = ("base_object", "template")
    readonly_fields = ("created", "modified", "document_link")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "base_object",
                    "template",
                    "record_type",
                    "status",
                    "title",
                    "description",
                    "notes",
                )
            },
        ),
        (
            _("Schedule"),
            {
                "fields": (
                    "performed_on",
                    "expires_on",
                    "performed_by",
                    "reference",
                    "document_url",
                    "document",
                    "document_link",
                )
            },
        ),
        (
            _("Metadata"),
            {"fields": ("extra_data", "created", "modified")},
        ),
    )

    def record_type_display(self, instance):
        return instance.get_record_type_display()

    record_type_display.short_description = _("Type")

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")

    def document_link(self, instance):
        if instance.document:
            return mark_safe(
                '<a href="{url}" target="_blank" rel="noopener">{label}</a>'.format(
                    url=instance.document.url,
                    label=_("Download"),
                )
            )
        return "—"

    document_link.short_description = _("Document")


@register(ComplianceTemplate)
class ComplianceTemplateAdmin(RalphAdmin):
    list_display = (
        "name",
        "record_type",
        "frequency_days",
        "grace_period_days",
        "content_type",
        "is_active",
        "auto_create",
        "modified",
    )
    list_filter = ("record_type", "is_active", "content_type")
    search_fields = ("name", "title", "description")
    readonly_fields = ("created", "modified")


class DisposalTemplateTaskInline(RalphTabularInline):
    model = DisposalTemplateTask
    extra = 1
    fields = ("name", "is_required")


@register(DisposalTemplate)
class DisposalTemplateAdmin(RalphAdmin):
    list_display = ("name", "content_type", "is_active", "modified")
    list_filter = ("is_active", "content_type")
    search_fields = ("name",)
    inlines = [DisposalTemplateTaskInline]
    readonly_fields = ("created", "modified")


class DisposalTaskInline(RalphTabularInline):
    model = DisposalTask
    extra = 0
    fields = (
        "name",
        "is_required",
        "is_completed",
        "completed_by",
        "completed_at",
    )
    can_delete = False


@register(DisposalRecord)
class DisposalRecordAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "status_display",
        "method",
        "approved_by",
        "approved_at",
        "modified",
    )
    list_filter = ("status", "approved_at")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "method",
        "notes",
    )
    raw_id_fields = ("base_object", "approved_by", "template")
    readonly_fields = ("created", "modified")
    inlines = [DisposalTaskInline]

    @admin.display(description=_("Status"))
    def status_display(self, instance):
        return DisposalStatus.from_id(instance.status).desc


class ComplianceRecordInline(RalphTabularInline):
    model = ComplianceRecord
    fk_name = "base_object"
    extra = 0
    fields = (
        "record_type_display",
        "title",
        "status_display",
        "performed_on",
        "expires_on",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def record_type_display(self, instance):
        return instance.get_record_type_display()

    record_type_display.short_description = _("Type")

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


class DeploymentAssignmentInline(RalphTabularInline):
    model = DeploymentAssignment
    fk_name = "deployment_entry"
    extra = 0
    fields = (
        "user",
        "role",
        "started_at",
        "ended_at",
        "handover_notes",
        "last_reported_at",
        "last_reported_metric",
    )
    readonly_fields = ("last_reported_at", "last_reported_metric")
    raw_id_fields = ("user",)


@register(DeploymentAssignment)
class DeploymentAssignmentAdmin(RalphAdmin):
    list_display = (
        "deployment_entry",
        "user",
        "role",
        "started_at",
        "ended_at",
        "last_reported_at",
    )
    list_filter = ("role",)
    search_fields = (
        "deployment_entry__base_object__hostname",
        "deployment_entry__base_object__barcode",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    raw_id_fields = ("deployment_entry", "user")
    readonly_fields = ("created", "modified")


@register(DeploymentEntry)
class DeploymentEntryAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "status_display",
        "shift_label",
        "assigned_to_user",
        "assigned_to_team",
        "location",
        "roster_summary",
        "started_at",
        "ended_at",
        "last_telemetry_at",
    )
    list_filter = ("status", "assigned_to_team", "shift_label")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "location",
        "shift_label",
        "notes",
    )
    raw_id_fields = ("base_object", "assigned_to_user", "assigned_to_team")
    readonly_fields = ("created", "modified", "roster_summary")
    inlines = [DeploymentAssignmentInline]

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


class DeploymentEntryInline(RalphTabularInline):
    model = DeploymentEntry
    fk_name = "base_object"
    extra = 0
    fields = (
        "status_display",
        "shift_label",
        "roster_summary",
        "assigned_to_user",
        "assigned_to_team",
        "location",
        "latitude",
        "longitude",
        "current_speed_kmh",
        "started_at",
        "ended_at",
        "last_telemetry_at",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


@register(TelemetryReading)
class TelemetryReadingAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "source",
        "metric",
        "value_numeric",
        "value_text",
        "unit",
        "captured_at",
        "ingested_at",
    )
    list_filter = ("source", "metric")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "metric",
        "value_text",
    )
    raw_id_fields = ("base_object",)
    readonly_fields = ("ingested_at", "created", "modified")


class TelemetryReadingInline(RalphTabularInline):
    model = TelemetryReading
    fk_name = "base_object"
    extra = 0
    fields = (
        "source",
        "metric",
        "value_numeric",
        "value_text",
        "unit",
        "captured_at",
        "ingested_at",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class WorkOrderInline(RalphTabularInline):
    model = WorkOrder
    fk_name = "base_object"
    extra = 0
    fields = (
        "title",
        "order_type_display",
        "priority_display",
        "status_display",
        "vendor_name",
        "opened_at",
        "due_at",
        "sla_target_at",
        "sla_breach_at",
        "effective_total_cost",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def order_type_display(self, instance):
        return instance.get_order_type_display()

    order_type_display.short_description = _("Type")

    def priority_display(self, instance):
        return instance.get_priority_display()

    priority_display.short_description = _("Priority")

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


@register(WorkOrder)
class WorkOrderAdmin(RalphAdmin):
    list_display = (
        "base_object",
        "title",
        "order_type",
        "priority",
        "status",
        "vendor_name",
        "opened_at",
        "due_at",
        "sla_target_at",
        "sla_breach_at",
        "effective_total_cost",
    )
    list_filter = ("order_type", "priority", "status")
    search_fields = ("title", "vendor_name", "base_object__hostname", "base_object__barcode")
    raw_id_fields = ("base_object", "approved_by")


@register(WorkOrderTask)
class WorkOrderTaskAdmin(RalphAdmin):
    list_display = (
        "work_order",
        "name",
        "status",
        "technician",
        "started_at",
        "ended_at",
        "cost",
    )
    list_filter = ("status",)
    search_fields = ("name", "work_order__title", "technician__username")
    raw_id_fields = ("work_order", "technician")


@register(ReportConfig)
class ReportConfigAdmin(RalphAdmin):
    list_display = (
        "name",
        "endpoint",
        "export_format",
        "is_active",
        "schedule_interval_seconds",
        "last_run_at",
    )
    list_filter = ("endpoint", "is_active")
    search_fields = ("name", "recipients")

class SafetyChecklistEntryInline(RalphTabularInline):
    model = SafetyChecklistEntry
    fk_name = "base_object"
    extra = 0
    fields = (
        "template",
        "status_display",
        "completed_at",
        "completed_by",
        "notes",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


class AssetIncidentInline(RalphTabularInline):
    model = AssetIncident
    fk_name = "base_object"
    extra = 0
    fields = (
        "title",
        "severity_display",
        "status_display",
        "opened_at",
        "closed_at",
        "assigned_to",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def severity_display(self, instance):
        return instance.get_severity_display()

    severity_display.short_description = _("Severity")

    def status_display(self, instance):
        return instance.get_status_display()

    status_display.short_description = _("Status")


@register(ManufacturerKind)
class ManufacturerKindAdmin(RalphAdmin):
    search_fields = ["name"]


@register(Service)
class ServiceAdmin(RalphAdmin):
    list_display = ["name", "uid", "active", "business_segment"]
    search_fields = ["name", "uid"]
    list_filter = ["active", "business_segment", "profit_center", "support_team"]
    list_select_related = ["business_segment"]

    fields = (
        "name",
        "uid",
        "active",
        "profit_center",
        "business_segment",
        "cost_center",
        "technical_owners",
        "business_owners",
        "support_team",
    )
    inlines = [ServiceEnvironmentInline]
    raw_id_fields = [
        "profit_center",
        "support_team",
        "business_owners",
        "technical_owners",
    ]
    resource_classes = [resources.ServiceResource]
    change_views = [ServiceBaseObjects]


@register(Manufacturer)
class ManufacturerAdmin(RalphAdmin):
    search_fields = [
        "name",
    ]
    list_filter = [
        "manufacturer_kind",
    ]


@register(BudgetInfo)
class BudgetInfoAdmin(RalphAdmin):
    search_fields = ["name"]


@register(Environment)
class EnvironmentAdmin(RalphAdmin):
    search_fields = ["name"]


@register(BusinessSegment)
class BusinessSegmentAdmin(RalphAdmin):
    search_fields = ["name"]
    list_display = ["name", "services_count"]

    def get_queryset(self, request):
        return BusinessSegment.objects.annotate(services_count=Count("service"))

    def services_count(self, instance):
        return instance.services_count

    services_count.short_description = _("Services count")
    services_count.admin_order_field = "services_count"


@register(ProfitCenter)
class ProfitCenterAdmin(RalphAdmin):
    search_fields = ["name"]


@register(AssetModel)
class AssetModelAdmin(CustomFieldValueAdminMixin, RalphAdmin):
    resource_classes = [resources.AssetModelResource]
    list_select_related = ["manufacturer", "category"]
    list_display = ["name", "type", "manufacturer", "category", "assets_count"]
    raw_id_fields = ["manufacturer"]
    search_fields = ["name", "manufacturer__name"]
    list_filter = ["type", "manufacturer", "category"]
    ordering = ["name"]
    fields = (
        "name",
        "manufacturer",
        "category",
        "type",
        "has_parent",
        "cores_count",
        "height_of_device",
        "power_consumption",
        "visualization_layout_front",
        "visualization_layout_back",
    )

    def get_queryset(self, request):
        return AssetModel.objects.annotate(assets_count=Count("assets"))

    def assets_count(self, instance):
        return instance.assets_count

    assets_count.short_description = _("Assets count")
    assets_count.admin_order_field = "assets_count"


@register(Category)
class CategoryAdmin(RalphMPTTAdmin):
    search_fields = ["name"]
    list_display = ["name", "code"]
    resource_classes = [resources.CategoryResource]

    def get_actions(self, request):
        return []


class ComponentAdminMixin(object):
    raw_id_fields = ["base_object", "model"]


@register(ComponentModel)
class ComponentModelAdmin(RalphAdmin):
    search_fields = ["name"]


@register(GenericComponent)
class GenericComponentAdmin(ComponentAdminMixin, RalphAdmin):
    search_fields = ["name"]


@register(Ethernet)
class EthernetAdmin(ComponentAdminMixin, RalphAdmin):
    search_fields = ["label", "mac"]


@register(Disk, FibreChannelCard, Memory, Processor)
class ComponentAdmin(ComponentAdminMixin, RalphAdmin):
    pass


@register(Asset)
class AssetAdmin(RalphAdmin):
    raw_id_fields = ["parent", "service_env", "model"]
    search_fields = ["hostname", "sn", "barcode"]


@register(BaseObject)
class BaseObjectAdmin(RalphAdmin):
    list_display = ["repr"]
    raw_id_fields = ["parent", "service_env"]
    exclude = ("content_type",)
    list_select_related = ["content_type"]

    def repr(self, obj):
        return "{}: {}".format(obj.content_type, obj)

    def has_add_permission(self, request):
        return False


@register(AssetHolder)
class AssetHolderAdmin(RalphAdmin):
    search_fields = ["name"]
