from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AlreadyRegistered, NotRegistered
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from ralph.admin.mixins import RalphAdmin, RalphTabularInline
from ralph.admin.views.extra import RalphDetailViewAdmin
from ralph.admin.sites import ralph_site
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
)
from ralph.sensors.forms import (
    SensorAssignmentForm,
    SensorFaultStatusForm,
    SensorMaintenanceStatusForm,
    SensorRetirementForm,
    SensorUnassignmentForm,
)
from ralph.sensors.models import (
    SensorCategory,
    SensorAsset,
    EnvironmentalSensorAsset,
    SecuritySensorAsset,
    InfrastructureSensorAsset,
    LogisticsSensorAsset,
    WearableSensorAsset,
    Sensor,
    SensorAssignment,
    SensorMaintenanceLog,
    SensorStatus,
    SensorStatusLog,
    SensorUptimeLog,
)
from ralph.lib.custom_fields.admin import CustomFieldValueAdminMixin
from ralph.lib.mixins.forms import AssetFormMixin, PriceFormMixin
from ralph.lib.transitions.admin import TransitionAdminMixin


class SensorAssetAdminForm(PriceFormMixin, AssetFormMixin, RalphAdmin.form):
    MODEL_TYPE = ObjectModelType.sensor

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        service_env_field = self.fields.get("service_env")
        if service_env_field:
            service_env_field.required = False


class SensorOperationsView(RalphDetailViewAdmin):
    icon = "plug"
    name = "operations"
    label = _("Operations")
    url_name = "operations"
    inlines = [MaintenanceRecordInline, DeploymentEntryInline]
    summary_fields = [
        "status",
        "location_description",
        "last_online_at",
        "battery_level_percent",
        "next_calibration_due",
        "communication_protocol",
        "power_source",
    ]


class SensorComplianceView(RalphDetailViewAdmin):
    icon = "shield"
    name = "compliance"
    label = _("Compliance")
    url_name = "compliance"
    inlines = [ComplianceRecordInline]
    summary_fields = [
        "last_calibrated",
        "next_calibration_due",
        "calibration_interval_days",
        "maintenance_contact",
    ]


class SensorDataView(RalphDetailViewAdmin):
    icon = "area-chart"
    name = "data"
    label = _("Telemetry")
    url_name = "telemetry"
    inlines = [TelemetryReadingInline]
    summary_fields = [
        "sensor_type",
        "external_identifier",
        "measurement_unit",
        "battery_level_percent",
        "battery_level_threshold_percent",
        "last_online_at",
        "firmware_version",
        "hardware_revision",
    ]


class SensorAssetAdmin(
    AttachmentsMixin,
    TransitionAdminMixin,
    CustomFieldValueAdminMixin,
    RalphAdmin,
):
    show_transition_history = True
    form = SensorAssetAdminForm
    inlines = [MaintenanceRecordInline]
    list_display = (
        "status",
        "sensor_type",
        "category",
        "serial_number",
        "external_identifier",
        "manufacturer",
        "model_name",
        "model",
        "power_source",
        "owner",
        "user",
        "location_description",
        "region",
        "service_env",
        "maintenance_status",
        "compliance_status",
    )
    search_fields = (
        "serial_number",
        "external_identifier",
        "manufacturer",
        "model_name",
        "firmware_version",
        "installation_site",
        "barcode",
        "hostname",
        "sensor_type",
        "category",
        "model__name",
    )
    list_filter = (
        "status",
        "sensor_type",
        "category",
        "power_source",
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
            _("Identification & Hardware"),
            {
                "fields": (
                    "hostname",
                    "sensor_type",
                    "category",
                    "manufacturer",
                    "model_name",
                    "serial_number",
                    "external_identifier",
                    "barcode",
                    "sn",
                    "firmware_version",
                    "hardware_revision",
                    "measurement_unit",
                )
            },
        ),
        (
            _("Status & Telemetry"),
            {
                "fields": (
                    "status",
                    "last_status_change",
                    "power_source",
                    "battery_level_percent",
                    "battery_level_threshold_percent",
                    "last_online_at",
                    "total_uptime_hours",
                    "total_downtime_hours",
                    "expected_update_interval_seconds",
                    "maintenance_status",
                    "compliance_status",
                )
            },
        ),
        (
            _("Calibration & Compliance"),
            {
                "fields": (
                    "last_calibrated",
                    "next_calibration_due",
                    "calibration_interval_days",
                    "maintenance_contact",
                )
            },
        ),
        (
            _("Deployment"),
            {
                "fields": (
                    "owner",
                    "user",
                    "location_description",
                    "installation_site",
                    "latitude",
                    "longitude",
                    "region",
                    "service_env",
                )
            },
        ),
        (
            _("Integration & Links"),
            {
                "fields": (
                    "communication_protocol",
                    "external_feed_reference",
                    "parent_asset",
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
        (_("Additional"), {"fields": ("remarks", "tags")}),
    )
    change_views = [
        SensorOperationsView,
        SensorComplianceView,
        SensorDataView,
    ]

    def __init__(self, *args, **kwargs):
        self.change_views = list(self.change_views or [])
        super().__init__(*args, **kwargs)

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
        return _("{} open / {} overdue").format(open_count, overdue_count)

    @admin.display(description=_("Compliance"))
    def compliance_status(self, obj):
        records = obj.compliance_records.all()
        due_soon = records.filter(status=ComplianceRecordStatus.due_soon.id).count()
        overdue = records.filter(status=ComplianceRecordStatus.overdue.id).count()
        return _("{} due soon / {} overdue").format(due_soon, overdue)


class SensorAssetCategoryAdmin(SensorAssetAdmin):
    sensor_category_filter = None

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        category = self.sensor_category_filter or getattr(
            self.model, "sensor_category_filter", None
        )
        if not category:
            return queryset
        return queryset.filter(category=category)


class SensorAssignmentInline(RalphTabularInline):
    model = SensorAssignment
    extra = 0
    fields = (
        "assigned_at",
        "assignee",
        "location",
        "latitude",
        "longitude",
        "assigned_by",
        "unassigned_at",
        "unassigned_by",
        "note",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class SensorUptimeLogInline(RalphTabularInline):
    model = SensorUptimeLog
    extra = 1
    fields = (
        "date",
        "hours_online",
        "hours_offline",
        "operational_cost",
        "note",
        "recorded_by",
    )
    readonly_fields = ("recorded_by",)


class SensorMaintenanceLogInline(RalphTabularInline):
    model = SensorMaintenanceLog
    extra = 1
    fields = (
        "date",
        "description",
        "result",
        "cost",
        "technician",
        "reference",
        "next_calibration_due",
    )


class SensorStatusLogInline(RalphTabularInline):
    model = SensorStatusLog
    extra = 0
    fields = (
        "created",
        "previous_status",
        "new_status",
        "changed_by",
        "note",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class SensorAdmin(RalphAdmin):
    list_display = (
        "name",
        "sensor_type",
        "model_name",
        "serial_number",
        "status",
        "installation_date",
        "location_description",
        "last_calibrated",
        "next_calibration_due",
        "calibration_interval_days",
        "acquisition_cost",
        "total_maintenance_cost",
        "total_operational_cost",
        "warranty_expiration",
        "last_online_at",
        "total_uptime_hours",
        "assigned_user",
    )
    list_filter = (
        "sensor_type",
        "status",
        "installation_date",
        "last_calibrated",
        "next_calibration_due",
        "last_online_at",
        "cost_center",
    )
    search_fields = (
        "name",
        "serial_number",
        "sensor_type",
        "model_name",
        "location_description",
        "assigned_user__username",
        "cost_center",
    )
    inlines = [
        SensorAssignmentInline,
        SensorUptimeLogInline,
        SensorMaintenanceLogInline,
        SensorStatusLogInline,
    ]
    actions = [
        "assign_sensors",
        "unassign_sensors",
        "mark_active",
        "mark_maintenance",
        "mark_faulty",
        "retire_sensors",
    ]

    def _perform_status_action(
        self,
        request,
        queryset,
        target_status,
        form_class,
        title,
    ):
        action_name = request.POST.get("action")
        if "apply" in request.POST:
            form = form_class(request.POST)
            if form.is_valid():
                note, metadata = form.cleaned_note_and_metadata()
                metadata = self._clean_metadata(metadata)
                updated = 0
                for obj in queryset:
                    try:
                        if obj.change_status(
                            request.user,
                            target_status,
                            note=note,
                            metadata=metadata,
                        ):
                            updated += 1
                    except ValidationError as exc:
                        self.message_user(
                            request,
                            _("%(sensor)s – %(error)s")
                            % {"sensor": obj, "error": exc.messages[0]},
                            level=messages.ERROR,
                        )
                if updated:
                    self.message_user(
                        request,
                        _("Updated %(count)s sensor(s) to %(status)s.")
                        % {
                            "count": updated,
                            "status": SensorStatus(target_status).label,
                        },
                        level=messages.SUCCESS,
                    )
                return None
        else:
            form = form_class()

        context = {
            "title": title,
            "objects": queryset,
            "form": form,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "action_name": action_name,
            "target_status_label": SensorStatus(target_status).label,
            "select_across": request.POST.get("select_across"),
        }
        return render(request, "admin/lifecycle/status_action.html", context)

    def _clean_metadata(self, metadata):
        return {k: v for k, v in metadata.items() if v not in ("", None)}

    def _perform_assignment_action(
        self,
        request,
        queryset,
        form_class,
        title,
        assign=True,
    ):
        action_name = request.POST.get("action")
        if "apply" in request.POST:
            form = form_class(request.POST)
            if form.is_valid():
                cleaned = form.cleaned_data
                note = cleaned.get("note", "")
                updated = 0
                for obj in queryset:
                    try:
                        if assign:
                            obj.assign_to(
                                user=cleaned.get("assignee"),
                                location=cleaned.get("location", ""),
                                latitude=cleaned.get("latitude"),
                                longitude=cleaned.get("longitude"),
                                assigned_by=request.user,
                                note=note,
                            )
                            updated += 1
                        else:
                            if obj.unassign(unassigned_by=request.user, note=note):
                                updated += 1
                    except ValidationError as exc:
                        self.message_user(
                            request,
                            _("%(sensor)s – %(error)s")
                            % {"sensor": obj, "error": exc.messages[0]},
                            level=messages.ERROR,
                        )
                if updated:
                    message = (
                        _("Assigned %(count)s sensor(s).")
                        if assign
                        else _("Unassigned %(count)s sensor(s).")
                    )
                    self.message_user(
                        request,
                        message % {"count": updated},
                        level=messages.SUCCESS,
                    )
                return None
        else:
            form = form_class()

        context = {
            "title": title,
            "objects": queryset,
            "form": form,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "action_name": action_name,
            "target_status_label": title,
            "select_across": request.POST.get("select_across"),
        }
        return render(request, "admin/lifecycle/status_action.html", context)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, SensorUptimeLog) and instance.recorded_by_id is None:
                instance.recorded_by = request.user
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    @admin.action(description=_("Assign selected sensors"))
    def assign_sensors(self, request, queryset):
        return self._perform_assignment_action(
            request,
            queryset,
            form_class=SensorAssignmentForm,
            title=_("Assign sensors"),
            assign=True,
        )

    @admin.action(description=_("Unassign selected sensors"))
    def unassign_sensors(self, request, queryset):
        return self._perform_assignment_action(
            request,
            queryset,
            form_class=SensorUnassignmentForm,
            title=_("Unassign sensors"),
            assign=False,
        )

    @admin.action(description=_("Mark selected sensors as Installed / Active"))
    def mark_active(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            SensorStatus.INSTALLED_ACTIVE,
            form_class=SensorMaintenanceStatusForm,
            title=_("Confirm active status"),
        )

    @admin.action(description=_("Mark selected sensors as Maintenance / Calibrating"))
    def mark_maintenance(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            SensorStatus.MAINTENANCE,
            form_class=SensorMaintenanceStatusForm,
            title=_("Confirm maintenance status"),
        )

    @admin.action(description=_("Mark selected sensors as Faulty"))
    def mark_faulty(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            SensorStatus.FAULTY,
            form_class=SensorFaultStatusForm,
            title=_("Confirm faulty status"),
        )

    @admin.action(description=_("Retire selected sensors"))
    def retire_sensors(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            SensorStatus.RETIRED,
            form_class=SensorRetirementForm,
            title=_("Confirm sensor retirement"),
        )


class SensorAssignmentAdmin(RalphAdmin):
    list_display = (
        "sensor",
        "assignee",
        "location",
        "latitude",
        "longitude",
        "assigned_at",
        "unassigned_at",
    )
    list_filter = ("assigned_at", "unassigned_at", "assignee")
    search_fields = (
        "sensor__name",
        "sensor__serial_number",
        "assignee__username",
        "location",
    )
    raw_id_fields = ("sensor", "assignee", "assigned_by", "unassigned_by")
    readonly_fields = ("created", "modified")


class SensorUptimeLogAdmin(RalphAdmin):
    list_display = (
        "sensor",
        "date",
        "hours_online",
        "hours_offline",
        "operational_cost",
        "recorded_by",
    )
    list_filter = ("date",)
    search_fields = ("sensor__name", "sensor__serial_number")
    raw_id_fields = ("sensor", "recorded_by")

    def save_model(self, request, obj, form, change):
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


class SensorMaintenanceLogAdmin(RalphAdmin):
    list_display = (
        "sensor",
        "date",
        "description",
        "result",
        "cost",
        "technician",
    )
    list_filter = ("date", "result")
    search_fields = ("sensor__name", "sensor__serial_number", "description")
    raw_id_fields = ("sensor",)


class SensorStatusLogAdmin(RalphAdmin):
    list_display = (
        "sensor",
        "previous_status",
        "new_status",
        "changed_by",
        "created",
    )
    list_filter = ("previous_status", "new_status", "created")
    search_fields = ("sensor__name", "sensor__serial_number")
    raw_id_fields = ("sensor", "changed_by")
    readonly_fields = ("created", "modified")


class EnvironmentalSensorAssetAdmin(SensorAssetCategoryAdmin):
    sensor_category_filter = SensorCategory.environmental.id
    change_views = []


class SecuritySensorAssetAdmin(SensorAssetCategoryAdmin):
    sensor_category_filter = SensorCategory.security.id
    change_views = []


class InfrastructureSensorAssetAdmin(SensorAssetCategoryAdmin):
    sensor_category_filter = SensorCategory.infrastructure.id
    change_views = []


class LogisticsSensorAssetAdmin(SensorAssetCategoryAdmin):
    sensor_category_filter = SensorCategory.logistics.id
    change_views = []


class WearableSensorAssetAdmin(SensorAssetCategoryAdmin):
    sensor_category_filter = SensorCategory.wearable.id
    change_views = []


def _register(model, admin_class):
    try:
        admin.site.unregister(model)
    except NotRegistered:
        pass
    try:
        ralph_site.register([model], admin_class)
    except AlreadyRegistered:
        pass


for _model, _admin in [
    (SensorAsset, SensorAssetAdmin),
    (EnvironmentalSensorAsset, EnvironmentalSensorAssetAdmin),
    (SecuritySensorAsset, SecuritySensorAssetAdmin),
    (InfrastructureSensorAsset, InfrastructureSensorAssetAdmin),
    (LogisticsSensorAsset, LogisticsSensorAssetAdmin),
    (WearableSensorAsset, WearableSensorAssetAdmin),
    (Sensor, SensorAdmin),
    (SensorAssignment, SensorAssignmentAdmin),
    (SensorUptimeLog, SensorUptimeLogAdmin),
    (SensorMaintenanceLog, SensorMaintenanceLogAdmin),
    (SensorStatusLog, SensorStatusLogAdmin),
]:
    _register(_model, _admin)
