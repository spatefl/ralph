from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from ralph.assets.models.assets import Asset, AssetUtilizationSnapshot, TelemetryReading


@dataclass
class TelemetryPayload:
    source: str
    captured_at: datetime
    metric: str
    value: Optional[Decimal] = None
    unit: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kmh: Optional[float] = None
    status: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


def _base_object(asset: Asset):
    return getattr(asset, "baseobject_ptr", None) or asset


@transaction.atomic
def ingest_telemetry(asset: Asset, payload: TelemetryPayload):
    base_object = _base_object(asset)
    deployment_entry = (
        base_object.deployment_entries.filter(ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    reading = TelemetryReading.objects.create(
        base_object=base_object,
        deployment_entry=deployment_entry,
        source=payload.source,
        metric=payload.metric,
        unit=payload.unit,
        value_numeric=payload.value,
        value_text=str(payload.value) if payload.value is not None else "",
        captured_at=payload.captured_at,
        raw_payload=payload.extra or {},
    )

    speed = payload.speed_kmh or 0
    status = (payload.status or "").lower()
    active = speed > 1 or status in {"active", "moving", "in_use"}

    now = timezone.now()
    last_captured_at = asset.last_usage_captured_at or now
    delta_seconds = max(int((payload.captured_at - last_captured_at).total_seconds()), 0)
    if delta_seconds == 0:
        delta_seconds = 60  # assume 1 minute granularity if timestamps equal

    distance_delta = Decimal("0")
    if payload.metric in {"odometer", "odometer_km", "distance"} and payload.value is not None:
        if asset.last_usage_value is not None:
            distance_delta = max(payload.value - asset.last_usage_value, Decimal("0"))
        asset.last_usage_value = payload.value

    asset.last_usage_captured_at = payload.captured_at

    updates = {"last_usage_value", "last_usage_captured_at"}

    if hasattr(asset, "last_telematics_at"):
        asset.last_telematics_at = payload.captured_at
        updates.add("last_telematics_at")
    if hasattr(asset, "last_known_latitude") and payload.latitude is not None:
        asset.last_known_latitude = payload.latitude
        updates.add("last_known_latitude")
    if hasattr(asset, "last_known_longitude") and payload.longitude is not None:
        asset.last_known_longitude = payload.longitude
        updates.add("last_known_longitude")
    if hasattr(asset, "last_known_speed_kmh") and payload.speed_kmh is not None:
        asset.last_known_speed_kmh = payload.speed_kmh
        updates.add("last_known_speed_kmh")
    if hasattr(asset, "engine_hours") and payload.metric in {"engine_hours", "runtime_hours"} and payload.value is not None:
        asset.engine_hours = payload.value
        updates.add("engine_hours")
    if hasattr(asset, "hours_used") and payload.metric in {"hours_used", "runtime_hours", "engine_hours"} and payload.value is not None:
        asset.hours_used = payload.value
        updates.add("hours_used")
    if hasattr(asset, "last_runtime_hours") and payload.metric in {"runtime_hours", "engine_hours"} and payload.value is not None:
        asset.last_runtime_hours = payload.value
        updates.add("last_runtime_hours")
    if hasattr(asset, "odometer_km") and payload.metric in {"odometer", "odometer_km"} and payload.value is not None:
        asset.odometer_km = int(payload.value)
        updates.add("odometer_km")
    if payload.value is not None:
        def _clamp_percent(value: Decimal) -> Decimal:
            if value < 0:
                return Decimal("0")
            if value > 100:
                return Decimal("100")
            return value

        percent_metric_map = {
            "fuel_level_percent": {"fuel_level_percent"},
            "water_level_percent": {"water_level_percent"},
            "waste_level_percent": {"waste_level_percent"},
            "battery_level_percent": {"battery_level_percent"},
        }
        for field_name, metrics in percent_metric_map.items():
            if hasattr(asset, field_name) and payload.metric in metrics:
                percent = _clamp_percent(payload.value)
                setattr(asset, field_name, percent)
                updates.add(field_name)

        if payload.metric in {"occupancy_percent", "occupancy_level_percent"} and hasattr(
            asset, "set_occupancy_level"
        ):
            asset.set_occupancy_level(payload.value, captured_at=payload.captured_at)
            updates.add("occupancy_level_percent")
            updates.add("occupancy_status")
            if hasattr(asset, "occupancy_last_reported_at"):
                updates.add("occupancy_last_reported_at")

    asset.save(update_fields=list(updates))

    active_seconds = delta_seconds if active else 0
    idle_seconds = 0 if active else delta_seconds
    AssetUtilizationSnapshot.record_activity(
        base_object,
        active_seconds=active_seconds,
        idle_seconds=idle_seconds,
        distance_km=distance_delta,
        date=payload.captured_at.date(),
    )

    if deployment_entry is not None:
        speed_value = None
        if payload.speed_kmh is not None:
            speed_value = Decimal(str(payload.speed_kmh))
        latitude = Decimal(str(payload.latitude)) if payload.latitude is not None else None
        longitude = Decimal(str(payload.longitude)) if payload.longitude is not None else None
        deployment_entry.record_telemetry_snapshot(
            captured_at=payload.captured_at,
            latitude=latitude,
            longitude=longitude,
            speed=speed_value,
            reading=reading,
        )

    return {
        "active_seconds": active_seconds,
        "idle_seconds": idle_seconds,
        "distance_delta": float(distance_delta),
    }


def build_payload(data: Dict[str, Any]) -> TelemetryPayload:
    captured_at = data.get("captured_at")
    if isinstance(captured_at, str):
        captured_at = datetime.fromisoformat(captured_at)
    captured_at = captured_at or timezone.now()
    value = data.get("value")
    if value is not None:
        value = Decimal(str(value))
    return TelemetryPayload(
        source=data.get("source", "unknown"),
        captured_at=captured_at,
        metric=data.get("metric", "status"),
        value=value,
        unit=data.get("unit", ""),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        speed_kmh=data.get("speed"),
        status=data.get("status"),
        extra=data.get("extra") or {},
    )
