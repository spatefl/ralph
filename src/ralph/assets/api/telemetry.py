from __future__ import annotations

from django.urls import re_path
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ralph.assets.models.assets import Asset
from ralph.assets.services.telemetry import build_payload, ingest_telemetry


class TelemetryIngestionView(APIView):
    """Accept telemetry events pushed from external systems."""

    def post(self, request, *args, **kwargs):
        asset_id = request.data.get("asset_id")
        if not asset_id:
            return Response({"detail": "asset_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            asset = Asset.objects.get(pk=asset_id)
        except Asset.DoesNotExist:
            return Response({"detail": "Asset not found."}, status=status.HTTP_404_NOT_FOUND)

        events = request.data.get("events") or [request.data]
        ingested = []
        for event in events:
            payload = build_payload(event)
            result = ingest_telemetry(asset, payload)
            ingested.append(result)
        return Response({"ingested": ingested}, status=status.HTTP_202_ACCEPTED)


urlpatterns = [
    re_path(r"^telemetry/ingest/$", TelemetryIngestionView.as_view()),
]
