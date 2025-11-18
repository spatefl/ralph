# -*- coding: utf-8 -*-
from django.db.models import Prefetch

from ralph.api import RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetLifecycleSerializerMixin, AssetSerializer
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.assets.models import (
    MaintenanceRecord,
    ComplianceRecord,
    DeploymentEntry,
    TelemetryReading,
    SafetyChecklistEntry,
    AssetIncident,
)
from ralph.power.admin import PowerAssetAdmin
from ralph.power.models import PowerAsset


class PowerAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = PowerAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class PowerAssetSerializer(AssetLifecycleSerializerMixin, AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = PowerAsset
        depth = 2


class PowerAssetViewSet(RalphAPIViewSet):
    select_related = PowerAssetAdmin.list_select_related + (
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
            queryset=DeploymentEntry.objects.select_related(
                "project", "assigned_to_user", "assigned_to_team", "location_ref"
            )
            .order_by("-started_at", "-pk")
            .prefetch_related("assignments__user", "telemetry_events"),
        ),
        Prefetch(
            "telemetry_readings",
            queryset=TelemetryReading.objects.select_related("deployment_entry").order_by(
                "-captured_at", "-ingested_at"
            ),
        ),
        Prefetch(
            "safety_checklists",
            queryset=SafetyChecklistEntry.objects.select_related("template", "completed_by").prefetch_related(
                "responses__item"
            ),
        ),
        Prefetch(
            "incidents",
            queryset=AssetIncident.objects.select_related("reported_by", "assigned_to").prefetch_related(
                "tasks"
            ),
        ),
        "disposal_record__tasks",
    ]
    queryset = PowerAsset.objects.all()
    serializer_class = PowerAssetSerializer


router.register(r"power-assets", PowerAssetViewSet)
urlpatterns = []
