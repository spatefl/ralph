from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AlreadyRegistered, NotRegistered
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from ralph.admin.mixins import RalphAdmin, RalphTabularInline
from ralph.admin.sites import ralph_site
from ralph.attachments.admin import AttachmentsMixin
from ralph.assets.models.choices import ObjectModelType
from ralph.assets.admin import MaintenanceRecordInline
from ralph.drones.forms import (
    DroneAssignmentForm,
    DroneCertificationForm,
    DroneMaintenanceStatusForm,
    DroneRetirementForm,
    DroneUnassignmentForm,
)
from ralph.drones.models import (
    DroneMissionProfile,
    DroneAsset,
    SurveyDroneAsset,
    SurveillanceDroneAsset,
    DeliveryDroneAsset,
    InspectionDroneAsset,
    TrainingDroneAsset,
    Drone,
    DroneAssignment,
    DroneFlightLog,
    DroneMaintenanceLog,
    DroneStatus,
    DroneStatusLog,
)
from ralph.lib.custom_fields.admin import CustomFieldValueAdminMixin
from ralph.lib.mixins.forms import AssetFormMixin, PriceFormMixin
from ralph.lib.transitions.admin import TransitionAdminMixin


class DroneAssetAdminForm(PriceFormMixin, AssetFormMixin, RalphAdmin.form):
    MODEL_TYPE = ObjectModelType.drone

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        service_env_field = self.fields.get("service_env")
        if service_env_field:
            service_env_field.required = False


class DroneAssetAdmin(
    AttachmentsMixin,
    TransitionAdminMixin,
    CustomFieldValueAdminMixin,
    RalphAdmin,
):
    show_transition_history = True
    form = DroneAssetAdminForm
    inlines = [MaintenanceRecordInline]
    list_display = (
        "status",
        "identifier",
        "serial_number",
        "drone_type",
        "mission_profile",
        "model",
        "owner",
        "user",
        "assigned_team",
        "assigned_location",
        "region",
        "service_env",
    )
    search_fields = (
        "identifier",
        "serial_number",
        "barcode",
        "hostname",
        "model__name",
    )
    list_filter = (
        "status",
        "drone_type",
        "mission_profile",
        "assigned_team",
        "region",
        "owner",
        "user",
        "service_env",
    )
    list_select_related = (
        "model",
        "owner",
        "user",
        "assigned_team",
        "region",
        "service_env",
        "service_env__service",
        "service_env__environment",
    )
    raw_id_fields = (
        "model",
        "owner",
        "user",
        "assigned_team",
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
                    "identifier",
                    "serial_number",
                    "barcode",
                    "sn",
                    "model",
                    "drone_type",
                    "mission_profile",
                    "firmware_version",
                    "last_firmware_update",
                )
            },
        ),
        (
            _("Operations"),
            {
                "fields": (
                    "status",
                    "last_status_change",
                    "current_mission",
                    "battery_capacity_mah",
                    "battery_health_percent",
                    "flight_time_limit_minutes",
                    "total_flight_hours",
                    "flight_count",
                )
            },
        ),
        (
            _("Assignments"),
            {
                "fields": (
                    "owner",
                    "user",
                    "assigned_team",
                    "assigned_location",
                    "last_known_latitude",
                    "last_known_longitude",
                    "last_known_altitude_m",
                    "region",
                    "service_env",
                )
            },
        ),
        (
            _("Maintenance"),
            {
                "fields": (
                    "last_service_date",
                    "next_maintenance_date",
                    "next_maintenance_flight_hours",
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


class DroneAssetMissionAdmin(DroneAssetAdmin):
    mission_profile_filter = None

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        profile = self.mission_profile_filter or getattr(
            self.model, "mission_profile_filter", None
        )
        if not profile:
            return queryset
        return queryset.filter(mission_profile=profile)


class DroneAssignmentInline(RalphTabularInline):
    model = DroneAssignment
    extra = 0
    fields = (
        "assigned_at",
        "assignee",
        "team",
        "location",
        "mission",
        "assigned_by",
        "unassigned_at",
        "unassigned_by",
        "note",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class DroneFlightLogInline(RalphTabularInline):
    model = DroneFlightLog
    extra = 1
    fields = (
        "date",
        "duration_minutes",
        "distance_km",
        "mission",
        "battery_cycles_used",
        "note",
        "recorded_by",
    )
    readonly_fields = ("recorded_by",)


class DroneMaintenanceLogInline(RalphTabularInline):
    model = DroneMaintenanceLog
    extra = 1
    fields = (
        "date",
        "description",
        "flight_hours",
        "cost",
        "reference",
        "performed_by",
        "firmware_version",
        "battery_cycles",
        "next_maintenance_date",
        "next_maintenance_flight_hours",
    )


class DroneStatusLogInline(RalphTabularInline):
    model = DroneStatusLog
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


class DroneAdmin(RalphAdmin):
    list_display = (
        "identifier",
        "model_name",
        "drone_type",
        "status",
        "registration_number",
        "assigned_team",
        "assigned_user",
        "assigned_location",
        "current_mission",
        "acquisition_cost",
        "total_maintenance_cost",
        "total_operational_cost",
        "warranty_expiration",
        "flight_hours",
        "flight_count",
        "battery_cycle_count",
        "last_service_date",
        "next_maintenance_date",
        "next_maintenance_flight_hours",
        "last_firmware_update",
    )
    list_filter = (
        "drone_type",
        "status",
        "last_service_date",
        "next_maintenance_date",
        "last_firmware_update",
        "assigned_team",
        "cost_center",
    )
    search_fields = (
        "identifier",
        "model_name",
        "serial_number",
        "firmware_version",
        "registration_number",
        "pilot_license_required",
        "assigned_location",
        "assigned_team__name",
        "current_mission",
        "cost_center",
    )
    inlines = [
        DroneAssignmentInline,
        DroneFlightLogInline,
        DroneMaintenanceLogInline,
        DroneStatusLogInline,
    ]
    actions = [
        "assign_drones",
        "unassign_drones",
        "mark_operational",
        "mark_grounded",
        "mark_awaiting_certification",
        "retire_drones",
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
                            _("%(drone)s – %(error)s")
                            % {"drone": obj, "error": exc.messages[0]},
                            level=messages.ERROR,
                        )
                if updated:
                    self.message_user(
                        request,
                        _("Updated %(count)s drone(s) to %(status)s.")
                        % {
                            "count": updated,
                            "status": DroneStatus(target_status).label,
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
            "target_status_label": DroneStatus(target_status).label,
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
                                team=cleaned.get("team"),
                                location=cleaned.get("location", ""),
                                mission=cleaned.get("mission", ""),
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
                            _("%(drone)s – %(error)s")
                            % {"drone": obj, "error": exc.messages[0]},
                            level=messages.ERROR,
                        )
                if updated:
                    message = (
                        _("Assigned %(count)s drone(s).")
                        if assign
                        else _("Unassigned %(count)s drone(s).")
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
            if isinstance(instance, DroneFlightLog) and instance.recorded_by_id is None:
                instance.recorded_by = request.user
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    @admin.action(description=_("Assign selected drones"))
    def assign_drones(self, request, queryset):
        return self._perform_assignment_action(
            request,
            queryset,
            form_class=DroneAssignmentForm,
            title=_("Assign drones"),
            assign=True,
        )

    @admin.action(description=_("Unassign selected drones"))
    def unassign_drones(self, request, queryset):
        return self._perform_assignment_action(
            request,
            queryset,
            form_class=DroneUnassignmentForm,
            title=_("Unassign drones"),
            assign=False,
        )

    @admin.action(description=_("Mark selected drones as Operational"))
    def mark_operational(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            DroneStatus.OPERATIONAL,
            form_class=DroneMaintenanceStatusForm,
            title=_("Confirm operational status"),
        )

    @admin.action(description=_("Mark selected drones as Grounded"))
    def mark_grounded(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            DroneStatus.GROUNDED,
            form_class=DroneMaintenanceStatusForm,
            title=_("Confirm grounded status"),
        )

    @admin.action(description=_("Mark selected drones as Awaiting Certification"))
    def mark_awaiting_certification(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            DroneStatus.AWAITING_CERTIFICATION,
            form_class=DroneCertificationForm,
            title=_("Confirm awaiting certification status"),
        )

    @admin.action(description=_("Retire selected drones"))
    def retire_drones(self, request, queryset):
        return self._perform_status_action(
            request,
            queryset,
            DroneStatus.RETIRED,
            form_class=DroneRetirementForm,
            title=_("Confirm drone retirement"),
        )


class DroneAssignmentAdmin(RalphAdmin):
    list_display = (
        "drone",
        "assignee",
        "team",
        "location",
        "mission",
        "assigned_at",
        "unassigned_at",
    )
    list_filter = ("assigned_at", "unassigned_at", "team", "assignee")
    search_fields = (
        "drone__identifier",
        "assignee__username",
        "team__name",
        "location",
        "mission",
    )
    raw_id_fields = (
        "drone",
        "assignee",
        "team",
        "assigned_by",
        "unassigned_by",
    )
    readonly_fields = ("created", "modified")


class DroneFlightLogAdmin(RalphAdmin):
    list_display = (
        "drone",
        "date",
        "duration_minutes",
        "distance_km",
        "operational_cost",
        "recorded_by",
    )
    list_filter = ("date", "mission")
    search_fields = ("drone__identifier", "mission")
    raw_id_fields = ("drone", "recorded_by")

    def save_model(self, request, obj, form, change):
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


class DroneMaintenanceLogAdmin(RalphAdmin):
    list_display = (
        "drone",
        "date",
        "description",
        "flight_hours",
        "cost",
        "performed_by",
    )
    list_filter = ("date", "performed_by")
    search_fields = ("drone__identifier", "description")
    raw_id_fields = ("drone",)


class DroneStatusLogAdmin(RalphAdmin):
    list_display = (
        "drone",
        "previous_status",
        "new_status",
        "changed_by",
        "created",
    )
    list_filter = ("previous_status", "new_status", "created")
    search_fields = ("drone__identifier",)
    raw_id_fields = ("drone", "changed_by")
    readonly_fields = ("created", "modified")


class SurveyDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.SURVEY


class SurveillanceDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.SURVEILLANCE


class DeliveryDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.DELIVERY


class InspectionDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.INSPECTION


class TrainingDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.TRAINING


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
    (DroneAsset, DroneAssetAdmin),
    (SurveyDroneAsset, SurveyDroneAssetAdmin),
    (SurveillanceDroneAsset, SurveillanceDroneAssetAdmin),
    (DeliveryDroneAsset, DeliveryDroneAssetAdmin),
    (InspectionDroneAsset, InspectionDroneAssetAdmin),
    (TrainingDroneAsset, TrainingDroneAssetAdmin),
    (Drone, DroneAdmin),
    (DroneAssignment, DroneAssignmentAdmin),
    (DroneFlightLog, DroneFlightLogAdmin),
    (DroneMaintenanceLog, DroneMaintenanceLogAdmin),
    (DroneStatusLog, DroneStatusLogAdmin),
]:
    _register(_model, _admin)
