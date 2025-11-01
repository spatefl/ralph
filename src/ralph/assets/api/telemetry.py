from __future__ import annotations

from django.urls import re_path
from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ralph.assets.models.assets import Asset
from ralph.assets.services.telemetry import build_payload, ingest_telemetry


class TelemetryIngestionView(APIView):
    """Accept telemetry events pushed from external systems."""

    def post(self, request, *args, **kwargs):
        # Optional shared-secret header for simple auth
        shared = getattr(settings, "TELEMETRY_INGEST_TOKEN", None)
        if shared:
            token = request.headers.get("X-Ingest-Token") or request.headers.get("X-Api-Key")
            if token != shared:
                return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        asset_id = request.data.get("asset_id")
        if not asset_id:
            return Response({"detail": "asset_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            asset = Asset.objects.get(pk=asset_id)
        except Asset.DoesNotExist:
            return Response({"detail": "Asset not found."}, status=status.HTTP_404_NOT_FOUND)

        # Simple rate limiter (per IP + asset) – defaults to 120/min
        try:
            limit = int(getattr(settings, "TELEMETRY_RATE_PER_MINUTE", 120))
        except Exception:
            limit = 120
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR", "") or "unknown"
        key = f"telemetry_rate:{ip}:{asset_id}"
        count = cache.get(key, 0)
        if count and int(count) >= limit:
            return Response({"detail": "Rate limit exceeded."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        cache.incr(key) if cache.get(key) else cache.set(key, 1, timeout=60)

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
