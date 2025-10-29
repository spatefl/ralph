# -*- coding: utf-8 -*-
from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from django.db.models import Prefetch

from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer, AssetLifecycleSerializerMixin
from ralph.assets.models import (
    MaintenanceRecord,
    ComplianceRecord,
    DeploymentEntry,
    TelemetryReading,
)
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.heavy_equipment.admin import HeavyEquipmentAssetAdmin
from ralph.heavy_equipment.models import HeavyEquipmentAsset


class HeavyEquipmentAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = HeavyEquipmentAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class HeavyEquipmentAssetSerializer(AssetLifecycleSerializerMixin, AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()

    class Meta(AssetSerializer.Meta):
        model = HeavyEquipmentAsset
        depth = 2


class HeavyEquipmentAssetViewSet(RalphAPIViewSet):
    select_related = HeavyEquipmentAssetAdmin.list_select_related + (
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
    queryset = HeavyEquipmentAsset.objects.all()
    serializer_class = HeavyEquipmentAssetSerializer


router.register(r"heavy-equipment-assets", HeavyEquipmentAssetViewSet)
urlpatterns = []
