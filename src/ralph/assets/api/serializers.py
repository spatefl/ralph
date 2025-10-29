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
    Environment,
    Manufacturer,
    ManufacturerKind,
    MaintenanceRecord,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
    ProfitCenter,
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


class EnvironmentSerializer(RalphAPISerializer):
    class Meta:
        model = Environment
        fields = "__all__"


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
        )


class ComplianceRecordSerializer(RalphAPISerializer):
    record_type_display = serializers.CharField(
        source="get_record_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

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
            "notes",
        )


class DeploymentEntrySerializer(RalphAPISerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    assigned_to_user = SimpleRalphUserSerializer(read_only=True)
    assigned_to_team = SimpleTeamSerializer(read_only=True)

    class Meta:
        model = DeploymentEntry
        fields = (
            "id",
            "status",
            "status_display",
            "assigned_to_user",
            "assigned_to_team",
            "location",
            "latitude",
            "longitude",
            "started_at",
            "ended_at",
            "notes",
        )


class TelemetryReadingSerializer(RalphAPISerializer):
    class Meta:
        model = TelemetryReading
        fields = (
            "id",
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
    maintenance_summary = serializers.SerializerMethodField()
    compliance_summary = serializers.SerializerMethodField()

    maintenance_records_limit = 10
    compliance_records_limit = 10
    deployment_entries_limit = 10
    telemetry_readings_limit = 25

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
