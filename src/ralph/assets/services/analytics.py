# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional

from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from ralph.assets.models import Asset
from ralph.assets.models.assets import MaintenanceRecord, AssetIncidentStatus
from ralph.lib.transitions.models import TransitionsHistory


def _base_object(asset: Asset):
    return getattr(asset, "baseobject_ptr", None) or asset


def _filter_records(records: Iterable[MaintenanceRecord], start=None, end=None):
    if start:
        records = records.filter(opened_at__gte=start)
    if end:
        records = records.filter(opened_at__lte=end)
    return records


def mttr_hours(asset: Asset, *, start: Optional[datetime] = None, end: Optional[datetime] = None) -> float:
    records = _filter_records(
        asset.maintenance_records.filter(out_of_service=True, closed_at__isnull=False),
        start,
        end,
    )
    durations = []
    for record in records:
        opened = record.opened_at
        closed = record.closed_at or timezone.now()
        durations.append((closed - opened).total_seconds())
    if not durations:
        return 0.0
    return float(sum(durations) / len(durations) / 3600)


def mtbf_hours(asset: Asset, *, start: Optional[datetime] = None, end: Optional[datetime] = None) -> float:
    records = _filter_records(
        asset.maintenance_records.filter(out_of_service=True).order_by("opened_at"),
        start,
        end,
    )
    opened_times: List[datetime] = [record.opened_at for record in records if record.opened_at]
    if len(opened_times) < 2:
        return 0.0
    intervals = []
    for previous, current in zip(opened_times, opened_times[1:]):
        intervals.append((current - previous).total_seconds())
    if not intervals:
        return 0.0
    return float(sum(intervals) / len(intervals) / 3600)


def time_in_state(asset: Asset, *, reference: Optional[datetime] = None) -> dict:
    reference = reference or timezone.now()
    ct = ContentType.objects.get_for_model(asset.__class__)
    history = list(
        TransitionsHistory.objects.filter(
            content_type=ct,
            object_id=asset.pk,
        ).order_by("created")
    )
    durations = defaultdict(Decimal)
    last_timestamp = asset.created if hasattr(asset, "created") else reference
    current_state = history[0].source if history and history[0].source else getattr(asset, "get_status_display", lambda: "unknown")()

    for entry in history:
        timestamp = entry.created
        if last_timestamp and current_state:
            delta = Decimal((timestamp - last_timestamp).total_seconds())
            durations[current_state] += delta
        current_state = entry.target or current_state
        last_timestamp = timestamp

    if current_state and last_timestamp:
        delta = Decimal((reference - last_timestamp).total_seconds())
        durations[current_state] += delta

    return {state: float(seconds / Decimal(3600)) for state, seconds in durations.items()}


def transition_counts(asset: Asset, *, start: Optional[datetime] = None, end: Optional[datetime] = None) -> dict:
    ct = ContentType.objects.get_for_model(asset.__class__)
    history = TransitionsHistory.objects.filter(content_type=ct, object_id=asset.pk)
    if start:
        history = history.filter(created__gte=start)
    if end:
        history = history.filter(created__lte=end)
    counter = Counter(history.values_list("transition_name", flat=True))
    return dict(counter)


def compute_asset_metrics(asset: Asset, *, start: Optional[datetime] = None, end: Optional[datetime] = None) -> dict:
    return {
        "asset_id": asset.pk,
        "mttr_hours": mttr_hours(asset, start=start, end=end),
        "mtbf_hours": mtbf_hours(asset, start=start, end=end),
        "time_in_state_hours": time_in_state(asset, reference=end or timezone.now()),
        "transition_counts": transition_counts(asset, start=start, end=end),
        "open_incidents": asset.incidents.filter(status__lt=AssetIncidentStatus.resolved.id).count()
        if hasattr(asset, "incidents")
        else 0,
    }


def aggregate_metrics(assets: Iterable[Asset], *, start: Optional[datetime] = None, end: Optional[datetime] = None) -> dict:
    assets = list(assets)
    if not assets:
        return {
            "mttr_hours": 0.0,
            "mtbf_hours": 0.0,
            "time_in_state_hours": {},
            "transition_counts": {},
            "asset_count": 0,
        }

    mttr_total = Decimal("0")
    mtbf_total = Decimal("0")
    time_state_totals = defaultdict(Decimal)
    transition_totals = Counter()

    for asset in assets:
        metrics = compute_asset_metrics(asset, start=start, end=end)
        mttr_total += Decimal(str(metrics["mttr_hours"]))
        mtbf_total += Decimal(str(metrics["mtbf_hours"]))
        for state, hours in metrics["time_in_state_hours"].items():
            time_state_totals[state] += Decimal(str(hours))
        transition_totals.update(metrics["transition_counts"])

    count = len(assets)
    return {
        "asset_count": count,
        "mttr_hours": float(mttr_total / Decimal(count)),
        "mtbf_hours": float(mtbf_total / Decimal(count)),
        "time_in_state_hours": {state: float(hours / Decimal(count)) for state, hours in time_state_totals.items()},
        "transition_counts": dict(transition_totals),
    }


def trailer_status_metrics() -> dict:
    from ralph.trailers.models import TrailerAsset, TrailerOccupancyStatus

    queryset = TrailerAsset.objects.all()
    total = queryset.count()
    status_counts = {
        row["occupancy_status"]: row["count"]
        for row in queryset.values("occupancy_status").annotate(count=Count("pk"))
    }
    available = status_counts.get(TrailerOccupancyStatus.AVAILABLE, 0)
    occupied = status_counts.get(TrailerOccupancyStatus.OCCUPIED, 0)
    servicing = status_counts.get(TrailerOccupancyStatus.CLEANING, 0) + status_counts.get(
        TrailerOccupancyStatus.OUT_OF_SERVICE, 0
    )
    avg_occupancy = queryset.aggregate(avg=Avg("occupancy_level_percent"))["avg"] or Decimal("0")
    low_fuel = queryset.filter(
        fuel_level_percent__isnull=False,
    ).filter(
        Q(
            fuel_level_threshold_percent__isnull=False,
            fuel_level_percent__lte=F("fuel_level_threshold_percent"),
        )
        | Q(
            fuel_level_threshold_percent__isnull=True,
            fuel_level_percent__lte=Decimal("15"),
        )
    ).count()
    return {
        "total": total,
        "available": available,
        "occupied": occupied,
        "servicing": servicing,
        "low_fuel": low_fuel,
        "average_occupancy_percent": float(avg_occupancy or 0),
    }


def power_utilization_metrics() -> dict:
    from ralph.heavy_equipment.models import HeavyEquipmentAssetStatus, HeavyEquipmentDeploymentStatus
    from ralph.power.models import PowerAsset, PowerAssetType

    queryset = PowerAsset.objects.all()
    total = queryset.count()
    low_fuel = queryset.filter(
        fuel_level_percent__isnull=False,
    ).filter(
        Q(
            fuel_level_threshold_percent__isnull=False,
            fuel_level_percent__lte=F("fuel_level_threshold_percent"),
        )
        | Q(
            fuel_level_threshold_percent__isnull=True,
            fuel_level_percent__lte=Decimal("20"),
        )
    ).count()
    in_maintenance = queryset.filter(status=HeavyEquipmentAssetStatus.under_maintenance.id).count()
    avg_runtime = queryset.aggregate(avg=Avg("hours_used"))["avg"] or Decimal("0")
    avg_fuel = queryset.aggregate(avg=Avg("fuel_level_percent"))["avg"] or Decimal("0")

    type_metrics = []
    for value, label in PowerAssetType.choices:
        subset = queryset.filter(power_asset_type=value)
        count = subset.count()
        if not count:
            continue
        deployed = subset.filter(deployment_status=HeavyEquipmentDeploymentStatus.DEPLOYED).count()
        type_low_fuel = subset.filter(
            fuel_level_percent__isnull=False,
        ).filter(
            Q(
                fuel_level_threshold_percent__isnull=False,
                fuel_level_percent__lte=F("fuel_level_threshold_percent"),
            )
            | Q(
                fuel_level_threshold_percent__isnull=True,
                fuel_level_percent__lte=Decimal("20"),
            )
        ).count()
        type_metrics.append(
            {
                "value": value,
                "label": label,
                "count": count,
                "deployed": deployed,
                "low_fuel": type_low_fuel,
                "average_runtime_hours": float(subset.aggregate(avg=Avg("hours_used"))["avg"] or 0),
                "average_fuel_percent": float(subset.aggregate(avg=Avg("fuel_level_percent"))["avg"] or 0),
            }
        )

    return {
        "total": total,
        "low_fuel": low_fuel,
        "in_maintenance": in_maintenance,
        "average_runtime_hours": float(avg_runtime or 0),
        "average_fuel_percent": float(avg_fuel or 0),
        "types": type_metrics,
    }
