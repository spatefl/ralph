from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AlreadyRegistered, NotRegistered
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from ralph.admin.mixins import RalphAdmin, RalphTabularInline
from ralph.admin.sites import ralph_site
from ralph.sensors.forms import (
    SensorAssignmentForm,
    SensorFaultStatusForm,
    SensorMaintenanceStatusForm,
    SensorRetirementForm,
    SensorUnassignmentForm,
)
from ralph.sensors.models import (
    Sensor,
    SensorAssignment,
    SensorMaintenanceLog,
    SensorStatus,
    SensorStatusLog,
    SensorUptimeLog,
)


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
    (Sensor, SensorAdmin),
    (SensorAssignment, SensorAssignmentAdmin),
    (SensorUptimeLog, SensorUptimeLogAdmin),
    (SensorMaintenanceLog, SensorMaintenanceLogAdmin),
    (SensorStatusLog, SensorStatusLogAdmin),
]:
    _register(_model, _admin)
