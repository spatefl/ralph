# -*- coding: utf-8 -*-
from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from django.db.models import Prefetch
from rest_framework import serializers
from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer, AssetLifecycleSerializerMixin
from ralph.assets.models import (
    MaintenanceRecord,
    ComplianceRecord,
    DeploymentEntry,
    TelemetryReading,
)
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.fleet.admin import FleetAssetAdmin
from ralph.fleet.models import FleetAsset


class FleetAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = FleetAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class FleetAssetSerializer(AssetLifecycleSerializerMixin, AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    vehicle_type_display = serializers.CharField(
        source="get_vehicle_type_display", read_only=True
    )
    fuel_type_display = serializers.CharField(
        source="get_fuel_type_display", read_only=True
    )

    class Meta(AssetSerializer.Meta):
        model = FleetAsset
        depth = 2


class FleetAssetViewSet(RalphAPIViewSet):
    select_related = FleetAssetAdmin.list_select_related + (
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
    queryset = FleetAsset.objects.all()
    serializer_class = FleetAssetSerializer


router.register(r"fleet-assets", FleetAssetViewSet)
urlpatterns = []
