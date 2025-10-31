# -*- coding: utf-8 -*-
from rest_framework.decorators import action
from rest_framework.response import Response

from ralph.api import RalphAPIViewSet, router
from ralph.assets.api.serializers import (
    AssetIncidentSerializer,
    OperatorCertificationSerializer,
    SafetyChecklistEntrySerializer,
    SafetyChecklistTemplateSerializer,
)
from ralph.assets.models import (
    AssetIncident,
    OperatorCertification,
    SafetyChecklistEntry,
    SafetyChecklistTemplate,
)


class SafetyChecklistTemplateViewSet(RalphAPIViewSet):
    queryset = SafetyChecklistTemplate.objects.prefetch_related("items")
    serializer_class = SafetyChecklistTemplateSerializer
    filterset_fields = ("trigger", "is_active", "content_type")
    search_fields = ("name", "notes")


class SafetyChecklistEntryViewSet(RalphAPIViewSet):
    queryset = SafetyChecklistEntry.objects.select_related("template", "base_object", "completed_by").prefetch_related(
        "responses__item"
    )
    serializer_class = SafetyChecklistEntrySerializer
    filterset_fields = ("template", "status", "base_object")
    search_fields = (
        "base_object__hostname",
        "base_object__barcode",
        "template__name",
    )

    @action(detail=False, methods=["get"], url_path="latest")
    def latest(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).order_by("-completed_at")[:20]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class OperatorCertificationViewSet(RalphAPIViewSet):
    queryset = OperatorCertification.objects.select_related("user", "content_type")
    serializer_class = OperatorCertificationSerializer
    filterset_fields = ("content_type", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "name")


class AssetIncidentViewSet(RalphAPIViewSet):
    queryset = AssetIncident.objects.select_related("base_object", "reported_by", "assigned_to").prefetch_related(
        "tasks"
    )
    serializer_class = AssetIncidentSerializer
    filterset_fields = ("severity", "status", "base_object")
    search_fields = ("title", "description")


router.register(r"safety/checklist-templates", SafetyChecklistTemplateViewSet)
router.register(r"safety/checklists", SafetyChecklistEntryViewSet)
router.register(r"safety/certifications", OperatorCertificationViewSet)
router.register(r"safety/incidents", AssetIncidentViewSet)


urlpatterns = []
