from django import forms
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
    Location,
)
from ralph.assets.admin import (
    MaintenanceRecordInline,
    ComplianceRecordInline,
    DeploymentEntryInline,
    TelemetryReadingInline,
)
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
        assigned_location = self.fields.get("assigned_location")
        if assigned_location:
            locations = Location.objects.all().order_by("name")
            choices = [("", "---------")]
            choices.extend(
                (loc.code, f"{loc.name} ({loc.code})") if loc.code else (loc.name, loc.name)
                for loc in locations
            )
            current = self.initial.get("assigned_location") or getattr(
                self.instance, "assigned_location", None
            )
            if current and current not in {choice[0] for choice in choices}:
                choices.append((current, f"{current} (existing)"))
            self.fields["assigned_location"] = forms.ChoiceField(
                choices=choices,
                required=False,
                label=assigned_location.label,
                help_text=_("Select assigned location from SC3 Locations."),
            )


class DroneOperationsView(RalphDetailViewAdmin):
    icon = "plane"
    name = "operations"
    label = _("Operations")
    url_name = "operations"
    inlines = [MaintenanceRecordInline, DeploymentEntryInline]
    summary_fields = [
        "status",
        "current_mission",
        "mission_payload_description",
        "total_flight_hours",
        "flight_count",
        "battery_health_percent",
        "battery_health_threshold_percent",
        "battery_cycle_count",
        "next_maintenance_date",
        "next_maintenance_flight_hours",
        "budget_status_display",
        "disposal_status_display",
    ]


class DroneComplianceView(RalphDetailViewAdmin):
    icon = "shield"
    name = "compliance"
    label = _("Compliance")
    url_name = "compliance"
    inlines = [ComplianceRecordInline]
    summary_fields = [
        "last_service_date",
        "next_maintenance_date",
        "mission_profile",
        "registration_expires_on",
        "airworthiness_expires_on",
        "insurance_expiry",
        "operator_certificate_number",
        "pilot_license_required",
        "next_inspection_due",
    ]


class DroneDataView(RalphDetailViewAdmin):
    icon = "line-chart"
    name = "data"
    label = _("Telemetry")
    url_name = "telemetry"
    inlines = [TelemetryReadingInline]
    summary_fields = [
        "battery_capacity_mah",
        "battery_health_percent",
        "battery_health_threshold_percent",
        "battery_cycle_count",
        "flight_time_limit_minutes",
        "max_range_km",
        "last_status_change",
    ]


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
        "manufacturer",
        "model",
        "registration_id",
        "registration_expires_on",
        "airworthiness_expires_on",
        "insurance_expiry",
        "owner",
        "user",
        "assigned_team",
        "assigned_location",
        "region",
        "service_env",
        "maintenance_status",
        "compliance_status",
    )
    search_fields = (
        "identifier",
        "serial_number",
        "registration_id",
        "operator_certificate_number",
        "insurance_policy_number",
        "barcode",
        "hostname",
        "model__name",
    )
    list_filter = (
        "status",
        "drone_type",
        "mission_profile",
        "assigned_team",
        "registration_expires_on",
        "insurance_expiry",
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
        "org_location",
        "region",
        "service_env",
        "budget_info",
        "property_of",
    )
    readonly_fields = ("maintenance_status", "compliance_status")
    change_views = [
        DroneOperationsView,
        DroneComplianceView,
        DroneDataView,
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
    fieldsets = (
        (
            _("Identification"),
            {
                "fields": (
                    "hostname",
                    "identifier",
                    "serial_number",
                    "manufacturer",
                    "model",
                    "drone_type",
                    "mission_profile",
                    "manufacture_year",
                    "barcode",
                    "sn",
                )
            },
        ),
        (
            _("Avionics & Firmware"),
            {
                "fields": (
                    "firmware_version",
                    "last_firmware_update",
                    "communication_link_type",
                )
            },
        ),
        (
            _("Compliance & Documentation"),
            {
                "fields": (
                    "registration_id",
                    "registration_authority",
                    "registration_expires_on",
                    "airworthiness_certificate_id",
                    "airworthiness_expires_on",
                    "operator_certificate_number",
                    "pilot_license_required",
                    "insurance_policy_number",
                    "insurance_provider",
                    "insurance_expiry",
                )
            },
        ),
        (
            _("Operations & Payload"),
            {
                "fields": (
                    "status",
                    "last_status_change",
                    "current_mission",
                    "mission_payload_description",
                    "payload_mounting",
                    "payload_power_requirements",
                    "total_flight_hours",
                    "flight_count",
                    "battery_capacity_mah",
                    "battery_health_percent",
                    "battery_health_threshold_percent",
                    "battery_cycle_count",
                    "flight_time_limit_minutes",
                    "max_range_km",
                    "max_endurance_minutes",
                    "maintenance_status",
                    "compliance_status",
                )
            },
        ),
        (
            _("Assignments & Location"),
            {
                "fields": (
                    "owner",
                    "user",
                    "assigned_team",
                    "org_location",
                    "assigned_location",
                    "home_location_description",
                    "last_known_latitude",
                    "last_known_longitude",
                    "last_known_altitude_m",
                    "failsafe_behavior",
                    "region",
                    "service_env",
                )
            },
        ),
        (
            _("Maintenance & Inspection"),
            {
                "fields": (
                    "last_service_date",
                    "next_maintenance_date",
                    "next_maintenance_flight_hours",
                    "last_inspection_date",
                    "next_inspection_due",
                )
            },
        ),
        (
            _("Financial"),
            {
                "fields": (
                    "price",
                    "invoice_no",
                    "invoice_date",
                    "provider",
                    "order_no",
                    "annual_capex_budget",
                    "annual_opex_budget",
                    "budget_period_start",
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
    change_views = []


class SurveillanceDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.SURVEILLANCE
    change_views = []


class DeliveryDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.DELIVERY
    change_views = []


class InspectionDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.INSPECTION
    change_views = []


class TrainingDroneAssetAdmin(DroneAssetMissionAdmin):
    mission_profile_filter = DroneMissionProfile.TRAINING
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
