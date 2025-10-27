from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AlreadyRegistered, NotRegistered
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from ralph.admin.mixins import RalphAdmin, RalphTabularInline
from ralph.admin.sites import ralph_site
from ralph.fleet.forms import (
    VehicleAssignmentForm,
    VehicleMaintenanceStatusForm,
    VehicleRetirementForm,
    VehicleUnassignmentForm,
)
from ralph.fleet.models import (
    Vehicle,
    VehicleAssignment,
    VehicleMaintenanceLog,
    VehicleStatus,
    VehicleStatusLog,
    VehicleUsageLog,
)


class VehicleAssignmentInline(RalphTabularInline):
    model = VehicleAssignment
    extra = 0
    fields = (
        "assigned_at",
        "assignee",
        "location",
        "assigned_by",
        "unassigned_at",
        "unassigned_by",
        "note",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class VehicleUsageLogInline(RalphTabularInline):
    model = VehicleUsageLog
    extra = 1
    fields = (
        "date",
        "odometer_km",
        "distance_km",
        "fuel_volume_l",
        "fuel_cost",
        "note",
        "recorded_by",
    )
    readonly_fields = ("recorded_by",)


class VehicleMaintenanceLogInline(RalphTabularInline):
    model = VehicleMaintenanceLog
    extra = 1
    fields = (
        "date",
        "description",
        "mileage_km",
        "cost",
        "reference",
        "performed_by",
        "next_service_date",
        "next_service_odometer",
    )


class VehicleStatusLogInline(RalphTabularInline):
    model = VehicleStatusLog
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


class VehicleAdmin(RalphAdmin):
    list_display = (
        "license_plate",
        "make",
        "model_name",
        "year",
        "fuel_type",
        "status",
        "next_service_date",
        "next_service_odometer",
        "assigned_user",
        "assigned_location",
        "purchase_cost",
        "total_maintenance_cost",
        "total_operational_cost",
        "warranty_expiration",
    )
    list_filter = (
        "fuel_type",
        "status",
        "year",
        "next_service_date",
        "cost_center",
    )
    search_fields = (
        "license_plate",
        "vin",
        "make",
        "model_name",
        "telematics_id",
        "assigned_location",
        "cost_center",
    )
    inlines = [
        VehicleAssignmentInline,
        VehicleUsageLogInline,
        VehicleMaintenanceLogInline,
        VehicleStatusLogInline,
    ]
    actions = [
        "assign_vehicle",
        "unassign_vehicle",
        "mark_vehicles_in_service",
        "mark_vehicles_under_maintenance",
        "decommission_vehicles",
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
                            _("%(vehicle)s – %(error)s")
                            % {"vehicle": obj, "error": exc.messages[0]},
                            level=messages.ERROR,
                        )
                if updated:
                    self.message_user(
                        request,
                        _("Updated %(count)s vehicle(s) to %(status)s.")
                        % {
                            "count": updated,
                            "status": VehicleStatus(target_status).label,
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
            "target_status_label": VehicleStatus(target_status).label,
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
                                assignee=cleaned.get("assignee"),
                                location=cleaned.get("location", ""),
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
                            _("%(vehicle)s – %(error)s")
                            % {"vehicle": obj, "error": exc.messages[0]},
                            level=messages.ERROR,
                        )
                if updated:
                    message = (
                        _("Assigned %(count)s vehicle(s).")
                        if assign
                        else _("Unassigned %(count)s vehicle(s).")
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
            if isinstance(instance, VehicleUsageLog) and instance.recorded_by_id is None:
                instance.recorded_by = request.user
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    @admin.action(description=_("Assign selected vehicles"))
    def assign_vehicle(self, request, queryset):
        return self._perform_assignment_action(
            request,
            queryset,
            form_class=VehicleAssignmentForm,
            title=_("Assign vehicles"),
            assign=True,
        )

    @admin.action(description=_("Unassign selected vehicles"))
    def unassign_vehicle(self, request, queryset):
        return self._perform_assignment_action(
            request,
            queryset,
            form_class=VehicleUnassignmentForm,
            title=_("Unassign vehicles"),
            assign=False,
        )

    @admin.action(description=_("Mark selected vehicles as In Service"))
    def mark_vehicles_in_service(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            VehicleStatus.IN_SERVICE,
            form_class=VehicleMaintenanceStatusForm,
            title=_("Confirm In Service status"),
        )

    @admin.action(description=_("Mark selected vehicles as Under Maintenance"))
    def mark_vehicles_under_maintenance(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            VehicleStatus.UNDER_MAINTENANCE,
            form_class=VehicleMaintenanceStatusForm,
            title=_("Confirm Under Maintenance status"),
        )

    @admin.action(description=_("Decommission selected vehicles"))
    def decommission_vehicles(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            VehicleStatus.DECOMMISSIONED,
            form_class=VehicleRetirementForm,
            title=_("Confirm vehicle decommission"),
        )


class VehicleAssignmentAdmin(RalphAdmin):
    list_display = (
        "vehicle",
        "assignee",
        "location",
        "assigned_at",
        "unassigned_at",
        "assigned_by",
        "unassigned_by",
    )
    list_filter = ("assigned_at", "unassigned_at", "assignee")
    search_fields = (
        "vehicle__license_plate",
        "vehicle__vin",
        "assignee__username",
        "location",
    )
    raw_id_fields = ("vehicle", "assignee", "assigned_by", "unassigned_by")
    readonly_fields = ("created", "modified")


class VehicleUsageLogAdmin(RalphAdmin):
    list_display = (
        "vehicle",
        "date",
        "distance_km",
        "fuel_volume_l",
        "fuel_cost",
        "recorded_by",
    )
    list_filter = ("date",)
    search_fields = ("vehicle__license_plate", "vehicle__vin")
    raw_id_fields = ("vehicle", "recorded_by")

    def save_model(self, request, obj, form, change):
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


class VehicleMaintenanceLogAdmin(RalphAdmin):
    list_display = (
        "vehicle",
        "date",
        "description",
        "mileage_km",
        "cost",
        "performed_by",
    )
    list_filter = ("date", "performed_by")
    search_fields = ("vehicle__license_plate", "vehicle__vin", "description")
    raw_id_fields = ("vehicle",)


class VehicleStatusLogAdmin(RalphAdmin):
    list_display = (
        "vehicle",
        "previous_status",
        "new_status",
        "changed_by",
        "created",
    )
    list_filter = ("previous_status", "new_status", "created")
    search_fields = ("vehicle__license_plate", "vehicle__vin")
    raw_id_fields = ("vehicle", "changed_by")
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
    (Vehicle, VehicleAdmin),
    (VehicleAssignment, VehicleAssignmentAdmin),
    (VehicleUsageLog, VehicleUsageLogAdmin),
    (VehicleMaintenanceLog, VehicleMaintenanceLogAdmin),
    (VehicleStatusLog, VehicleStatusLogAdmin),
]:
    _register(_model, _admin)
