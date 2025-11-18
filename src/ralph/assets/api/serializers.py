from datetime import date as datetime_date
from operator import attrgetter

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import fields, serializers

from ralph.accounts.api_simple import SimpleRalphUserSerializer
from ralph.accounts.models import Team
from ralph.api import RalphAPISerializer
from ralph.api.fields import StrField
from ralph.api.serializers import (
    AdditionalLookupRelatedField,
    RalphAPISaveSerializer,
    ReversionHistoryAPISerializerMixin,
)
from ralph.api.utils import PolymorphicSerializer
from ralph.assets.models import (
    Asset,
    AssetHolder,
    AssetModel,
    BaseObject,
    BudgetInfo,
    BusinessSegment,
    Category,
    ComplianceRecord,
    ConfigurationClass,
    ConfigurationModule,
    DeploymentEntry,
    DeploymentAssignment,
    Environment,
    Manufacturer,
    ManufacturerKind,
    MaintenanceRecord,
    MaintenancePartUsage,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
    SafetyChecklistItem,
    SafetyChecklistTemplate,
    SafetyChecklistEntry,
    SafetyChecklistResponse,
    OperatorCertification,
    AssetIncident,
    AssetIncidentTask,
    SparePart,
    SparePartCategory,
    SparePartStock,
    DisposalStatus,
    ProfitCenter,
    Project,
    Location,
    DeploymentStatus,
    Service,
    ServiceEnvironment,
    TelemetryReading,
    ComplianceRecordStatus,
)
from ralph.assets.models.components import (
    Disk,
    Ethernet,
    FibreChannelCard,
    Memory,
    Processor,
)
from ralph.lib.custom_fields.api import WithCustomFieldsSerializerMixin
from ralph.licences.api_simple import SimpleBaseObjectLicenceSerializer
from ralph.networks.api_simple import IPAddressSimpleSerializer


class TypeFromContentTypeSerializerMixin(RalphAPISerializer):
    object_type = fields.SerializerMethodField(read_only=True)

    def get_object_type(self, instance):
        return instance.content_type.model


class OwnersFromServiceEnvSerializerMixin(RalphAPISerializer):
    business_owners = SimpleRalphUserSerializer(
        many=True, source="service_env.service.business_owners", required=False
    )
    technical_owners = SimpleRalphUserSerializer(
        many=True, source="service_env.service.technical_owners", required=False
    )


class BusinessSegmentSerializer(RalphAPISerializer):
    class Meta:
        model = BusinessSegment
        fields = "__all__"


class BudgetInfoSerializer(RalphAPISerializer):
    class Meta:
        model = BudgetInfo
        fields = "__all__"


class ProfitCenterSerializer(RalphAPISerializer):
    class Meta:
        model = ProfitCenter
        fields = ("id", "name", "description", "url")
        depth = 1


class SimpleTeamSerializer(RalphAPISerializer):
    class Meta:
        model = Team
        fields = ("id", "name", "url")


class LocationSerializer(RalphAPISerializer):
    class Meta:
        model = Location
        fields = (
            "id",
            "url",
            "name",
            "code",
            "external_id",
            "color_hex",
            "description",
            "latitude",
            "longitude",
            "notes",
            "created",
            "modified",
        )


class ProjectSerializer(RalphAPISerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    manager = SimpleRalphUserSerializer(read_only=True)
    default_team = SimpleTeamSerializer(read_only=True)
    location = LocationSerializer(read_only=True)
    location_id = serializers.IntegerField(source="location_id", read_only=True)
    active_assets_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "url",
            "name",
            "code",
            "external_id",
            "status",
            "status_display",
            "manager",
            "default_team",
            "location",
            "location_id",
            "location_name",
            "latitude",
            "longitude",
            "start_date",
            "end_date",
            "description",
            "notes",
            "active_assets_count",
            "created",
            "modified",
        )


class ProjectSaveSerializer(RalphAPISaveSerializer):
    manager = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), allow_null=True, required=False
    )
    default_team = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), allow_null=True, required=False
    )
    location = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Project
        fields = (
            "name",
            "code",
            "external_id",
            "status",
            "manager",
            "default_team",
            "location",
            "location_name",
            "latitude",
            "longitude",
            "start_date",
            "end_date",
            "description",
            "notes",
        )


class ProjectDetailSerializer(ProjectSerializer):
    deployments = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ("deployments",)

    def get_deployments(self, obj):
        entries = obj.deployment_entries.select_related(
            "base_object",
            "assigned_to_user",
            "assigned_to_team",
            "project",
            "location_ref",
        ).order_by("-started_at", "-pk")
        return DeploymentEntrySerializer(
            entries, many=True, context=self.context
        ).data


class ProjectAssignmentItemSerializer(serializers.Serializer):
    asset = serializers.PrimaryKeyRelatedField(
        queryset=BaseObject.polymorphic_objects.all()
    )
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), allow_null=True, required=False
    )
    status = serializers.ChoiceField(
        choices=DeploymentStatus(), required=False, allow_null=True
    )
    shift_label = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        required=False,
        allow_null=True,
        source="location_ref",
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    handover_notes = serializers.CharField(required=False, allow_blank=True)


class ProjectBulkAssignmentSerializer(serializers.Serializer):
    assignments = ProjectAssignmentItemSerializer(many=True)


class EnvironmentSerializer(RalphAPISerializer):
    class Meta:
        model = Environment
        fields = "__all__"


class SparePartStockSerializer(RalphAPISerializer):
    class Meta:
        model = SparePartStock
        fields = (
            "id",
            "location",
            "quantity_on_hand",
            "quantity_reserved",
            "reorder_point",
            "reorder_quantity",
            "last_restocked_at",
            "is_active",
        )


class SparePartSerializer(RalphAPISerializer):
    stocks = SparePartStockSerializer(many=True, read_only=True)

    class Meta:
        model = SparePart
        fields = (
            "id",
            "name",
            "sku",
            "vendor_name",
            "vendor_sku",
            "unit_cost",
            "restock_threshold",
            "restock_quantity",
            "external_reference",
            "is_active",
            "stocks",
        )


class SparePartCategorySerializer(RalphAPISerializer):
    parts = SparePartSerializer(many=True, read_only=True)

    class Meta:
        model = SparePartCategory
        fields = ("id", "name", "description", "parts")


class MaintenancePartUsageSerializer(RalphAPISerializer):
    part = SparePartSerializer(read_only=True)
    stock = SparePartStockSerializer(read_only=True)
    effective_unit_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    extended_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = MaintenancePartUsage
        fields = (
            "id",
            "part",
            "stock",
            "quantity_used",
            "unit_cost",
            "effective_unit_cost",
            "extended_cost",
            "notes",
        )


class SafetyChecklistItemSerializer(RalphAPISerializer):
    class Meta:
        model = SafetyChecklistItem
        fields = ("id", "prompt", "item_type", "is_required", "require_attachment")


class SafetyChecklistTemplateSerializer(RalphAPISerializer):
    items = SafetyChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = SafetyChecklistTemplate
        fields = (
            "id",
            "name",
            "trigger",
            "content_type",
            "is_active",
            "require_all_pass",
            "validity_period_hours",
            "notes",
            "items",
        )


class SafetyChecklistResponseSerializer(RalphAPISerializer):
    item = SafetyChecklistItemSerializer(read_only=True)

    class Meta:
        model = SafetyChecklistResponse
        fields = (
            "id",
            "item",
            "value_boolean",
            "value_text",
            "value_decimal",
        )


class SafetyChecklistEntrySerializer(RalphAPISerializer):
    template = SafetyChecklistTemplateSerializer(read_only=True)
    completed_by = SimpleRalphUserSerializer(read_only=True)
    responses = SafetyChecklistResponseSerializer(many=True, read_only=True)

    class Meta:
        model = SafetyChecklistEntry
        fields = (
            "id",
            "template",
            "status",
            "completed_by",
            "completed_at",
            "notes",
            "responses",
        )


class OperatorCertificationSerializer(RalphAPISerializer):
    user = SimpleRalphUserSerializer(read_only=True)

    class Meta:
        model = OperatorCertification
        fields = (
            "id",
            "user",
            "name",
            "content_type",
            "issued_on",
            "expires_on",
            "is_active",
            "notes",
        )


class AssetIncidentTaskSerializer(RalphAPISerializer):
    completed_by = SimpleRalphUserSerializer(read_only=True)

    class Meta:
        model = AssetIncidentTask
        fields = ("id", "description", "due_at", "completed_at", "completed_by")


class AssetIncidentSerializer(RalphAPISerializer):
    reported_by = SimpleRalphUserSerializer(read_only=True)
    assigned_to = SimpleRalphUserSerializer(read_only=True)
    tasks = AssetIncidentTaskSerializer(many=True, read_only=True)

    class Meta:
        model = AssetIncident
        fields = (
            "id",
            "title",
            "description",
            "severity",
            "status",
            "opened_at",
            "closed_at",
            "reported_by",
            "assigned_to",
            "tasks",
        )


class SaveServiceSerializer(ReversionHistoryAPISerializerMixin, RalphAPISerializer):
    """
    Serializer to save (create or update) services. Environments should be
    passed as a list of ids.

    DRF doesn't work out-of-the-box with many-to-many with through table
    (ex. `ServiceEnvironment`). We're overwriting save mechanism to handle
    this m2m relationship ourself.
    """

    environments = AdditionalLookupRelatedField(
        many=True,
        read_only=False,
        queryset=Environment.objects.all(),
        lookup_fields=["name"],
    )
    business_owners = AdditionalLookupRelatedField(
        many=True,
        read_only=False,
        queryset=get_user_model().objects.all(),
        lookup_fields=["username"],
        style={"base_template": "input.html"},
    )
    technical_owners = AdditionalLookupRelatedField(
        many=True,
        read_only=False,
        queryset=get_user_model().objects.all(),
        lookup_fields=["username"],
        style={"base_template": "input.html"},
    )
    support_team = AdditionalLookupRelatedField(
        read_only=False,
        queryset=Team.objects.all(),
        lookup_fields=["name"],
        required=False,
        allow_null=True,
    )
    profit_center = AdditionalLookupRelatedField(
        read_only=False,
        queryset=ProfitCenter.objects.all(),
        lookup_fields=["name"],
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Service
        fields = "__all__"

    @transaction.atomic
    def _save_environments(self, instance, environments):
        """
        Save service-environments many-to-many records.
        """
        # delete ServiceEnv for missing environments
        ServiceEnvironment.objects.filter(service=instance).exclude(
            environment__in=environments
        ).delete()
        current_environments = set(
            ServiceEnvironment.objects.filter(service=instance).values_list(
                "environment_id", flat=True
            )
        )
        # create ServiceEnv for new environments
        for environment in environments:
            if environment.id not in current_environments:
                ServiceEnvironment.objects.create(
                    service=instance, environment=environment
                )

    def create(self, validated_data):
        environments = validated_data.pop("environments", [])
        instance = super().create(validated_data)
        self._save_environments(instance, environments)
        return instance

    def update(self, instance, validated_data):
        environments = validated_data.pop("environments", None)
        result = super().update(instance, validated_data)
        if environments is not None:
            self._save_environments(instance, environments)
        return result


class ServiceSerializer(RalphAPISerializer):
    business_owners = SimpleRalphUserSerializer(many=True)
    technical_owners = SimpleRalphUserSerializer(many=True)

    class Meta:
        model = Service
        depth = 1
        fields = "__all__"


class ServiceEnvironmentSimpleSerializer(RalphAPISerializer):
    service = serializers.CharField(source="service_name", read_only=True)
    environment = serializers.CharField(source="environment_name", read_only=True)
    service_uid = serializers.CharField(read_only=True)

    class Meta:
        model = ServiceEnvironment
        fields = (
            "id",
            "service",
            "environment",
            "url",
            "service_uid",
        )
        _skip_tags_field = True


class ServiceEnvironmentSerializer(
    TypeFromContentTypeSerializerMixin,
    WithCustomFieldsSerializerMixin,
    RalphAPISerializer,
):
    __str__ = StrField(show_type=True)
    business_owners = SimpleRalphUserSerializer(
        many=True, source="service.business_owners"
    )
    technical_owners = SimpleRalphUserSerializer(
        many=True, source="service.technical_owners"
    )

    class Meta:
        model = ServiceEnvironment
        depth = 1
        exclude = ("content_type", "parent", "service_env")


class ManufacturerSerializer(RalphAPISerializer):
    class Meta:
        model = Manufacturer
        fields = "__all__"


class ManufacturerKindSerializer(RalphAPISerializer):
    class Meta:
        model = ManufacturerKind
        fields = "__all__"


class CategorySerializer(RalphAPISerializer):
    depreciation_rate = serializers.FloatField(source="get_default_depreciation_rate")

    class Meta:
        model = Category
        fields = "__all__"


class AssetModelSerializer(WithCustomFieldsSerializerMixin, RalphAPISerializer):
    category = CategorySerializer()

    class Meta:
        model = AssetModel
        fields = (
            "id",
            "url",
            "custom_fields",
            "configuration_variables",
            "category",
            "name",
            "created",
            "modified",
            "type",
            "power_consumption",
            "height_of_device",
            "cores_count",
            "visualization_layout_front",
            "visualization_layout_back",
            "has_parent",
            "manufacturer",
        )
        depth = 1


class AssetModelSaveSerializer(RalphAPISaveSerializer):
    class Meta:
        model = AssetModel
        fields = "__all__"


class BaseObjectPolymorphicSerializer(
    TypeFromContentTypeSerializerMixin, PolymorphicSerializer, RalphAPISerializer
):
    """
    Serializer for BaseObjects viewset (serialize each model using dedicated
    serializer).
    """

    __str__ = StrField(show_type=True)
    service_env = ServiceEnvironmentSerializer()

    class Meta:
        model = BaseObject
        exclude = ("content_type",)


class AssetHolderSerializer(RalphAPISerializer):
    class Meta:
        model = AssetHolder
        fields = "__all__"


class BaseObjectSimpleSerializer(
    TypeFromContentTypeSerializerMixin,
    WithCustomFieldsSerializerMixin,
    RalphAPISerializer,
):
    __str__ = StrField(show_type=True)

    class Meta:
        model = BaseObject
        exclude = ("content_type",)


class ConfigurationModuleSimpleSerializer(RalphAPISerializer):
    class Meta:
        model = ConfigurationModule
        fields = ("id", "url", "name", "parent", "support_team")


class ConfigurationModuleSerializer(
    WithCustomFieldsSerializerMixin, ConfigurationModuleSimpleSerializer
):
    children_modules = serializers.HyperlinkedRelatedField(
        view_name="configurationmodule-detail",
        many=True,
        read_only=True,
        required=False,
    )

    class Meta(ConfigurationModuleSimpleSerializer.Meta):
        fields = ConfigurationModuleSimpleSerializer.Meta.fields + (
            "children_modules",
            "custom_fields",
        )


class ConfigurationClassSimpleSerializer(RalphAPISerializer):
    module = ConfigurationModuleSimpleSerializer()

    class Meta:
        model = ConfigurationClass
        exclude = ("content_type", "configuration_path", "parent")


# TODO: Is there a better way to make it work since drf 3.5?
del ConfigurationClassSimpleSerializer._declared_fields["tags"]


class ConfigurationClassSerializer(
    TypeFromContentTypeSerializerMixin,
    WithCustomFieldsSerializerMixin,
    RalphAPISerializer,
):
    __str__ = StrField(show_type=True)
    module = ConfigurationModuleSimpleSerializer()

    class Meta:
        model = ConfigurationClass
        exclude = ("content_type", "service_env", "configuration_path")


class BaseObjectSerializer(BaseObjectSimpleSerializer):
    """
    Base class for other serializers inheriting from `BaseObject`.
    """

    service_env = ServiceEnvironmentSimpleSerializer()
    licences = SimpleBaseObjectLicenceSerializer(read_only=True, many=True)
    configuration_path = ConfigurationClassSimpleSerializer()

    class Meta(BaseObjectSimpleSerializer.Meta):
        pass


class AssetSerializer(BaseObjectSerializer):
    class Meta(BaseObjectSerializer.Meta):
        model = Asset


class EthernetSimpleSerializer(RalphAPISerializer):
    ipaddress = IPAddressSimpleSerializer()

    class Meta:
        model = Ethernet
        fields = ("id", "mac", "ipaddress", "url")


class EthernetSerializer(EthernetSimpleSerializer):
    class Meta:
        model = Ethernet
        depth = 1
        fields = "__all__"


class MemorySimpleSerializer(RalphAPISerializer):
    class Meta:
        model = Memory
        fields = ("id", "url", "size", "speed")


class MemorySerializer(MemorySimpleSerializer):
    class Meta:
        depth = 1
        model = Memory
        exclude = ("model",)


class FibreChannelCardSimpleSerializer(RalphAPISerializer):
    class Meta:
        model = FibreChannelCard
        fields = ("id", "url", "firmware_version", "speed", "wwn")


class FibreChannelCardSerializer(FibreChannelCardSimpleSerializer):
    class Meta:
        depth = 1
        model = FibreChannelCard
        exclude = ("model",)


class ProcessorSimpleSerializer(RalphAPISerializer):
    class Meta:
        model = Processor
        fields = ("id", "url", "speed", "cores", "logical_cores")


class ProcessorSerializer(ProcessorSimpleSerializer):
    class Meta:
        depth = 1
        model = Processor
        exclude = ("model",)


class DiskSimpleSerializer(RalphAPISerializer):
    class Meta:
        model = Disk
        fields = (
            "id",
            "url",
            "size",
            "serial_number",
            "slot",
            "firmware_version",
        )


class DiskSerializer(DiskSimpleSerializer):
    class Meta:
        depth = 1
        model = Disk
        exclude = ("model",)


class MaintenanceRecordSerializer(RalphAPISerializer):
    record_type_display = serializers.CharField(
        source="get_record_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reported_by = SimpleRalphUserSerializer(read_only=True)
    closed_by = SimpleRalphUserSerializer(read_only=True)
    is_sla_overdue = serializers.BooleanField(read_only=True)
    parts = MaintenancePartUsageSerializer(
        source="part_usages", many=True, read_only=True
    )
    parts_cost_total = serializers.DecimalField(
        source="parts_cost_total", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = MaintenanceRecord
        fields = (
            "id",
            "record_type",
            "record_type_display",
            "status",
            "status_display",
            "title",
            "description",
            "resolution",
            "opened_at",
            "expected_completion",
            "closed_at",
            "cost",
            "out_of_service",
            "reported_by",
            "performed_by",
            "service_provider",
            "sla_due_at",
            "closed_by",
            "closure_notes",
            "closure_acknowledged",
            "closure_acknowledged_at",
            "extra_data",
            "is_sla_overdue",
            "parts",
            "parts_cost_total",
        )


class ComplianceRecordSerializer(RalphAPISerializer):
    record_type_display = serializers.CharField(
        source="get_record_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    document = serializers.FileField(read_only=True)

    class Meta:
        model = ComplianceRecord
        fields = (
            "id",
            "record_type",
            "record_type_display",
            "status",
            "status_display",
            "title",
            "description",
            "performed_on",
            "expires_on",
            "performed_by",
            "reference",
            "document_url",
            "document",
            "notes",
            "extra_data",
            "template",
        )


class DeploymentAssignmentSerializer(RalphAPISerializer):
    user = SimpleRalphUserSerializer(read_only=True)

    class Meta:
        model = DeploymentAssignment
        fields = (
            "id",
            "user",
            "role",
            "started_at",
            "ended_at",
            "handover_notes",
            "last_reported_at",
            "last_reported_metric",
        )


class DeploymentEntrySerializer(RalphAPISerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    assigned_to_user = SimpleRalphUserSerializer(read_only=True)
    assigned_to_team = SimpleTeamSerializer(read_only=True)
    assignments = DeploymentAssignmentSerializer(many=True, read_only=True)
    roster_summary = serializers.CharField(read_only=True)
    project = serializers.PrimaryKeyRelatedField(read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True)
    asset = BaseObjectSimpleSerializer(source="base_object", read_only=True)
    asset_id = serializers.IntegerField(source="base_object_id", read_only=True)
    location_id = serializers.IntegerField(
        source="location_ref_id", read_only=True, allow_null=True
    )
    location_name = serializers.CharField(
        source="location_ref.name", read_only=True, allow_null=True
    )
    location_color = serializers.CharField(
        source="location_ref.color_hex", read_only=True, allow_null=True
    )

    class Meta:
        model = DeploymentEntry
        fields = (
            "id",
            "status",
            "status_display",
            "project",
            "project_name",
            "project_code",
            "asset",
            "asset_id",
            "shift_label",
            "shift_start",
            "shift_end",
            "roster_summary",
            "assigned_to_user",
            "assigned_to_team",
            "location",
            "location_id",
            "location_name",
            "location_color",
            "latitude",
            "longitude",
            "current_speed_kmh",
            "started_at",
            "ended_at",
            "notes",
            "handover_notes",
            "last_telemetry_at",
            "assignments",
        )


class TelemetryReadingSerializer(RalphAPISerializer):
    deployment_entry = serializers.PrimaryKeyRelatedField(read_only=True)
    deployment_shift = serializers.CharField(
        source="deployment_entry.shift_label", read_only=True
    )

    class Meta:
        model = TelemetryReading
        fields = (
            "id",
            "deployment_entry",
            "deployment_shift",
            "source",
            "metric",
            "unit",
            "value_numeric",
            "value_text",
            "captured_at",
            "ingested_at",
        )


class AssetLifecycleSerializerMixin(RalphAPISerializer):
    maintenance_records = serializers.SerializerMethodField()
    compliance_records = serializers.SerializerMethodField()
    deployment_entries = serializers.SerializerMethodField()
    telemetry_readings = serializers.SerializerMethodField()
    safety_checklists = serializers.SerializerMethodField()
    incidents = serializers.SerializerMethodField()
    maintenance_summary = serializers.SerializerMethodField()
    compliance_summary = serializers.SerializerMethodField()
    disposal_summary = serializers.SerializerMethodField()

    maintenance_records_limit = 10
    compliance_records_limit = 10
    deployment_entries_limit = 10
    telemetry_readings_limit = 25
    safety_checklists_limit = 5
    incidents_limit = 10

    def _get_related(self, obj, attr):
        cache = getattr(obj, "_prefetched_objects_cache", {})
        related = cache.get(attr)
        if related is None:
            related = getattr(obj, attr).all()
        return related

    def _order_queryset(self, items, order_attr, reverse=True):
        if hasattr(items, "order_by"):
            prefix = "-" if reverse else ""
            return items.order_by(f"{prefix}{order_attr}")
        return sorted(items, key=attrgetter(order_attr), reverse=reverse)

    def get_maintenance_records(self, obj):
        records = self._order_queryset(
            self._get_related(obj, "maintenance_records"),
            "opened_at",
            reverse=True,
        )
        if self.maintenance_records_limit is not None:
            records = records[: self.maintenance_records_limit]
        return MaintenanceRecordSerializer(records, many=True, context=self.context).data

    def get_compliance_records(self, obj):
        records = self._get_related(obj, "compliance_records")
        if hasattr(records, "order_by"):
            records = records.order_by("expires_on", "title")
        else:
            records = sorted(
                records,
                key=lambda record: (
                    record.expires_on or datetime_date.max,
                    record.title or "",
                ),
            )
        if self.compliance_records_limit is not None:
            records = records[: self.compliance_records_limit]
        return ComplianceRecordSerializer(records, many=True, context=self.context).data

    def get_deployment_entries(self, obj):
        entries = self._order_queryset(
            self._get_related(obj, "deployment_entries"),
            "started_at",
            reverse=True,
        )
        if self.deployment_entries_limit is not None:
            entries = entries[: self.deployment_entries_limit]
        return DeploymentEntrySerializer(entries, many=True, context=self.context).data

    def get_telemetry_readings(self, obj):
        readings = self._get_related(obj, "telemetry_readings")
        if hasattr(readings, "order_by"):
            readings = readings.order_by("-captured_at", "-ingested_at")
        else:
            readings = sorted(
                readings,
                key=lambda reading: reading.captured_at or reading.ingested_at,
                reverse=True,
            )
        if self.telemetry_readings_limit is not None:
            readings = readings[: self.telemetry_readings_limit]
        return TelemetryReadingSerializer(readings, many=True, context=self.context).data

    def get_safety_checklists(self, obj):
        entries = self._get_related(obj, "safety_checklists")
        if hasattr(entries, "order_by"):
            entries = entries.order_by("-completed_at", "-created")
        else:
            entries = sorted(entries, key=lambda entry: entry.completed_at or entry.created, reverse=True)
        if self.safety_checklists_limit is not None:
            entries = entries[: self.safety_checklists_limit]
        return SafetyChecklistEntrySerializer(entries, many=True, context=self.context).data

    def get_incidents(self, obj):
        incidents = self._get_related(obj, "incidents")
        if hasattr(incidents, "order_by"):
            incidents = incidents.order_by("-opened_at")
        else:
            incidents = sorted(incidents, key=lambda incident: incident.opened_at, reverse=True)
        if self.incidents_limit is not None:
            incidents = incidents[: self.incidents_limit]
        return AssetIncidentSerializer(incidents, many=True, context=self.context).data

    def get_maintenance_summary(self, obj):
        open_statuses = {
            MaintenanceRecordStatus.open.id,
            MaintenanceRecordStatus.in_progress.id,
        }
        records = self._get_related(obj, "maintenance_records")
        if hasattr(records, "filter"):
            open_records = records.filter(status__in=open_statuses)
        else:
            open_records = [r for r in records if r.status in open_statuses]
        if hasattr(open_records, "filter"):
            overdue_count = open_records.filter(
                expected_completion__isnull=False,
                expected_completion__lt=timezone.now().date(),
            ).count()
            approval_required = open_records.filter(
                record_type=MaintenanceRecordType.approval.id
            ).exists()
            open_count = open_records.count()
        else:
            overdue_count = sum(
                1
                for r in open_records
                if r.expected_completion
                and r.expected_completion < timezone.now().date()
            )
            approval_required = any(
                r.record_type == MaintenanceRecordType.approval.id
                for r in open_records
            )
            open_count = len(open_records)
        summary = {
            "open_count": open_count,
            "overdue_count": overdue_count,
            "approval_required": approval_required,
            "alerts": [],
        }
        alerts_func = getattr(obj, "maintenance_alerts", None)
        if callable(alerts_func):
            summary["alerts"] = alerts_func()
        for attr in [
            "next_service_date",
            "next_service_hours",
            "next_service_odometer",
            "next_maintenance_date",
            "next_maintenance_flight_hours",
        ]:
            value = getattr(obj, attr, None)
            if value is None:
                continue
            if hasattr(value, "isoformat"):
                summary[attr] = value.isoformat()
            else:
                summary[attr] = value
        return summary

    def get_compliance_summary(self, obj):
        records = self._get_related(obj, "compliance_records")
        if hasattr(records, "filter"):
            due_soon = records.filter(status=ComplianceRecordStatus.due_soon.id).count()
            overdue = records.filter(status=ComplianceRecordStatus.overdue.id).count()
            next_expiry_obj = (
                records.exclude(expires_on__isnull=True)
                .order_by("expires_on")
                .first()
            )
        else:
            due_soon = sum(
                1 for r in records if r.status == ComplianceRecordStatus.due_soon.id
            )
            overdue = sum(
                1 for r in records if r.status == ComplianceRecordStatus.overdue.id
            )
            next_expiry_obj = None
            for r in records:
                if not r.expires_on:
                    continue
                if (
                    next_expiry_obj is None
                    or r.expires_on < next_expiry_obj.expires_on
                ):
                    next_expiry_obj = r
        summary = {
            "due_soon_count": due_soon,
            "overdue_count": overdue,
            "next_expiry": next_expiry_obj.expires_on.isoformat()
            if next_expiry_obj and next_expiry_obj.expires_on
            else None,
        }
        return summary

    def get_disposal_summary(self, obj):
        record = getattr(obj, "disposal_record", None)
        if not record:
            return None
        status_choice = DisposalStatus.from_id(record.status)
        status_desc = status_choice.desc if status_choice else ""
        return {
            "status": status_desc,
            "method": record.method,
            "approved_by": record.approved_by.pk if record.approved_by else None,
            "approved_at": record.approved_at.isoformat() if record.approved_at else None,
            "tasks": [
                {
                    "id": task.pk,
                    "name": task.name,
                    "is_required": task.is_required,
                    "is_completed": task.is_completed,
                    "completed_at": task.completed_at.isoformat()
                    if task.completed_at
                    else None,
                }
                for task in record.tasks.all()
            ],
        }

# used by DataCenterAsset and VirtualServer serializers
class NetworkComponentSerializerMixin(OwnersFromServiceEnvSerializerMixin):
    # TODO(xor-xor): ethernet -> ethernets
    ethernet = EthernetSimpleSerializer(many=True, source="ethernet_set")
    ipaddresses = fields.SerializerMethodField()

    def get_ipaddresses(self, instance):
        """
        Return list of ip addresses for passed instance.

        Returns:
            list of ip addresses (as strings)
        """
        # don't use `ipaddresses` property here to make use of
        # `ethernet__ipaddresses` in prefetch related
        ipaddresses = []
        for eth in instance.ethernet_set.all():
            try:
                ipaddresses.append(eth.ipaddress.address)
            except AttributeError:
                pass
        return ipaddresses


# used by DataCenterAsset and VirtualServer serializers
class ComponentSerializerMixin(NetworkComponentSerializerMixin):
    disk = DiskSimpleSerializer(many=True, source="disk_set")
    memory = MemorySimpleSerializer(many=True, source="memory_set")
    processors = ProcessorSimpleSerializer(many=True, source="processor_set")
