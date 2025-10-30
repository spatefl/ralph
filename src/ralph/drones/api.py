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
from ralph.drones.admin import DroneAssetAdmin
from ralph.drones.models import DroneAsset


class DroneAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = DroneAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class DroneAssetSerializer(AssetLifecycleSerializerMixin, AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    drone_type_display = serializers.CharField(
        source="get_drone_type_display", read_only=True
    )
    mission_profile_display = serializers.CharField(
        source="get_mission_profile_display_value", read_only=True
    )

    class Meta(AssetSerializer.Meta):
        model = DroneAsset
        depth = 2


class DroneAssetViewSet(RalphAPIViewSet):
    select_related = DroneAssetAdmin.list_select_related + (
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
        "disposal_record__tasks",
    ]
    queryset = DroneAsset.objects.all()
    serializer_class = DroneAssetSerializer


router.register(r"drone-assets", DroneAssetViewSet)
urlpatterns = []
