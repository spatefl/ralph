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
from ralph.fleet.models import (
    FLEET_GROUP_MAP,
    FleetAsset,
    FleetAssetFunctionalGroup,
    FleetLightVehicle,
    FleetTruckHauler,
    FleetUtilityVehicle,
    FleetEmergencyVehicle,
    FleetPassengerVehicle,
)
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
from ralph.lib.custom_fields.admin import CustomFieldValueAdminMixin
from ralph.lib.mixins.forms import AssetFormMixin, PriceFormMixin
from ralph.lib.transitions.admin import TransitionAdminMixin


class FleetAssetAdminForm(PriceFormMixin, AssetFormMixin, RalphAdmin.form):
    MODEL_TYPE = ObjectModelType.fleet

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


class FleetOperationsView(RalphDetailViewAdmin):
    icon = "cogs"
    name = "operations"
    label = _("Operations")
    url_name = "operations"
    inlines = [MaintenanceRecordInline, DeploymentEntryInline]
    summary_fields = [
        "status",
        "assigned_location",
        "user",
        "odometer_km",
        "next_service_date",
        "next_service_odometer",
        "last_telematics_at",
        "last_known_speed_kmh",
        "budget_status_display",
        "disposal_status_display",
    ]


class FleetComplianceView(RalphDetailViewAdmin):
    icon = "shield"
    name = "compliance"
    label = _("Compliance")
    url_name = "compliance"
    inlines = [ComplianceRecordInline]
    summary_fields = [
        "registration_expiry",
        "inspection_due_date",
        "insurance_expiry",
        "roadworthiness_certificate_expiry",
        "insurance_provider",
    ]


class FleetDataView(RalphDetailViewAdmin):
    icon = "tachometer"
    name = "data"
    label = _("Telemetry")
    url_name = "telemetry"
    inlines = [TelemetryReadingInline]
    summary_fields = [
        "odometer_km",
        "hours_used",
        "fuel_type",
        "fuel_level_percent",
        "last_service_date",
        "last_telematics_status",
        "last_known_latitude",
        "last_known_longitude",
        "last_known_heading_deg",
    ]


class FleetAssetAdmin(
    AttachmentsMixin,
    TransitionAdminMixin,
    CustomFieldValueAdminMixin,
    RalphAdmin,
):
    show_transition_history = True
    form = FleetAssetAdminForm
    inlines = [MaintenanceRecordInline]
    list_display = (
        "status",
        "license_plate",
        "vin",
        "vehicle_type",
        "make",
        "vehicle_model",
        "fuel_type",
        "registration_expiry",
        "insurance_expiry",
        "last_telematics_at",
        "owner",
        "user",
        "assigned_location",
        "region",
        "service_env",
        "model",
        "maintenance_status",
        "compliance_status",
    )
    search_fields = (
        "license_plate",
        "vin",
        "registration_number",
        "telematics_device_id",
        "fuel_card_identifier",
        "barcode",
        "hostname",
        "model__name",
    )
    list_filter = (
        "status",
        "vehicle_type",
        "fuel_type",
        "registration_expiry",
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
        "region",
        "service_env",
        "service_env__service",
        "service_env__environment",
    )
    raw_id_fields = (
        "model",
        "owner",
        "user",
        "org_location",
        "region",
        "service_env",
        "budget_info",
        "property_of",
    )
    readonly_fields = ("maintenance_status", "compliance_status")
    change_views = [
        FleetOperationsView,
        FleetComplianceView,
        FleetDataView,
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
                    "license_plate",
                    "vin",
                    "barcode",
                    "sn",
                    "model",
                    "vehicle_type",
                    "make",
                    "vehicle_model",
                    "manufacture_year",
                    "body_style",
                    "drivetrain",
                    "color",
                )
            },
        ),
        (
            _("Compliance & Documentation"),
            {
                "fields": (
                    "registration_number",
                    "registration_state",
                    "registration_authority",
                    "registration_expiry",
                    "inspection_due_date",
                    "insurance_policy_number",
                    "insurance_provider",
                    "insurance_expiry",
                    "roadworthiness_certificate_expiry",
                    "emissions_class",
                    "fuel_card_identifier",
                )
            },
        ),
        (
            _("Telematics & Location"),
            {
                "fields": (
                    "status",
                    "last_status_change",
                    "odometer_km",
                    "hours_used",
                    "engine_hours",
                    "last_service_date",
                    "next_service_date",
                    "next_service_odometer",
                    "last_telematics_at",
                    "telematics_device_id",
                    "telematics_provider",
                    "last_telematics_status",
                    "last_known_latitude",
                    "last_known_longitude",
                    "last_known_heading_deg",
                    "last_known_speed_kmh",
                    "fuel_level_percent",
                    "maintenance_status",
                    "compliance_status",
                )
            },
        ),
        (
            _("Specifications"),
            {
                "fields": (
                    "fuel_type",
                    "seating_capacity",
                    "gross_vehicle_weight_rating_kg",
                    "emergency_equipment_inventory",
                )
            },
        ),
        (
            _("Assignments"),
            {
                "fields": (
                    "owner",
                    "user",
                    "org_location",
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


class FleetAssetGroupAdmin(FleetAssetAdmin):
    functional_group_filter = None
    change_views = []

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        group = self.functional_group_filter or getattr(
            self.model, "functional_group_filter", None
        )
        if not group:
            return queryset
        vehicle_values = FLEET_GROUP_MAP.get(group, set())
        if not vehicle_values:
            return queryset.none()
        return queryset.filter(vehicle_type__in=vehicle_values)


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


class FleetLightVehicleAdmin(FleetAssetGroupAdmin):
    functional_group_filter = FleetAssetFunctionalGroup.light.id


class FleetTruckHaulerAdmin(FleetAssetGroupAdmin):
    functional_group_filter = FleetAssetFunctionalGroup.trucks.id


class FleetUtilityVehicleAdmin(FleetAssetGroupAdmin):
    functional_group_filter = FleetAssetFunctionalGroup.utility.id


class FleetEmergencyVehicleAdmin(FleetAssetGroupAdmin):
    functional_group_filter = FleetAssetFunctionalGroup.emergency.id


class FleetPassengerVehicleAdmin(FleetAssetGroupAdmin):
    functional_group_filter = FleetAssetFunctionalGroup.passenger.id


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
    (FleetAsset, FleetAssetAdmin),
    (FleetLightVehicle, FleetLightVehicleAdmin),
    (FleetTruckHauler, FleetTruckHaulerAdmin),
    (FleetUtilityVehicle, FleetUtilityVehicleAdmin),
    (FleetEmergencyVehicle, FleetEmergencyVehicleAdmin),
    (FleetPassengerVehicle, FleetPassengerVehicleAdmin),
    (Vehicle, VehicleAdmin),
    (VehicleAssignment, VehicleAssignmentAdmin),
    (VehicleUsageLog, VehicleUsageLogAdmin),
    (VehicleMaintenanceLog, VehicleMaintenanceLogAdmin),
    (VehicleStatusLog, VehicleStatusLogAdmin),
]:
    _register(_model, _admin)
