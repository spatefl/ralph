# -*- coding: utf-8 -*-
from django.db.models import Prefetch

from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer, AssetLifecycleSerializerMixin
from ralph.assets.models import (
    MaintenanceRecord,
    ComplianceRecord,
    DeploymentEntry,
    TelemetryReading,
)
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.sensors.admin import SensorAssetAdmin
from ralph.sensors.models import SensorAsset


class SensorAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = SensorAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class SensorAssetSerializer(AssetLifecycleSerializerMixin, AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()

    class Meta(AssetSerializer.Meta):
        model = SensorAsset
        depth = 2


class SensorAssetViewSet(RalphAPIViewSet):
    select_related = SensorAssetAdmin.list_select_related + (
        "service_env__service",
        "service_env__environment",
    )
    prefetch_related = base_object_descendant_prefetch_related + [
        "tags",
        "content_type",
        Prefetch(
            "maintenance_records",
            queryset=MaintenanceRecord.objects.order_by("-opened_at", "-pk"),
        ),
        Prefetch(
            "compliance_records",
            queryset=ComplianceRecord.objects.order_by("expires_on", "title"),
        ),
        Prefetch(
            "deployment_entries",
            queryset=DeploymentEntry.objects.order_by("-started_at", "-pk"),
        ),
        Prefetch(
            "telemetry_readings",
            queryset=TelemetryReading.objects.order_by("-captured_at", "-ingested_at"),
        ),
    ]
    queryset = SensorAsset.objects.all()
    serializer_class = SensorAssetSerializer


router.register(r"sensor-assets", SensorAssetViewSet)
urlpatterns = []
