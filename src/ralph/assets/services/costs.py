from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Optional

from django.db.models import Sum
from django.utils import timezone

from ralph.assets.models.assets import (
    Asset,
    AssetUtilizationSnapshot,
    MaintenanceRecord,
    MaintenanceRecordType,
    MaintenancePartUsage,
)


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _base_object(asset: Asset):
    return getattr(asset, "baseobject_ptr", None) or asset


def summarise_asset_costs(
    asset: Asset,
    *,
    start=None,
    end=None,
) -> dict:
    start = start or asset.budget_period_start or timezone.now().date().replace(month=1, day=1)
    end = end or timezone.now().date()

    base_object = _base_object(asset)

    maintenance_qs = asset.maintenance_records.filter(
        opened_at__date__gte=start,
        opened_at__date__lte=end,
    )
    maintenance_cost_total = maintenance_qs.filter(cost__isnull=False).aggregate(total=Sum("cost"))["total"] or Decimal("0")
    fuel_total = maintenance_qs.filter(
        record_type=MaintenanceRecordType.refuel.id,
        cost__isnull=False,
    ).aggregate(total=Sum("cost"))["total"] or Decimal("0")

    part_cost_total = Decimal("0")
    part_usages = MaintenancePartUsage.objects.filter(maintenance_record__in=maintenance_qs).select_related("part")
    for usage in part_usages:
        part_cost_total += usage.extended_cost

    opex_total = maintenance_cost_total + part_cost_total

    snapshots = base_object.utilization_snapshots.filter(date__range=(start, end))
    utilization = snapshots.aggregate(
        active_seconds=Sum("active_seconds"),
        idle_seconds=Sum("idle_seconds"),
        distance_km=Sum("distance_km"),
    )
    active_seconds = utilization.get("active_seconds") or 0
    idle_seconds = utilization.get("idle_seconds") or 0
    distance_km = utilization.get("distance_km") or Decimal("0")

    active_hours = Decimal(active_seconds) / Decimal(3600) if active_seconds else Decimal("0")
    cost_per_hour = (opex_total / active_hours) if active_hours else Decimal("0")
    fuel_consumption_per_hour = (fuel_total / active_hours) if active_hours else Decimal("0")

    budget_status = asset.budget_status(reference=end)

    return {
        "asset_id": asset.pk,
        "name": str(asset),
        "capex_actual": float(asset.capex_actual()),
        "maintenance_actual": float(maintenance_cost_total),
        "parts_actual": float(part_cost_total),
        "opex_actual": float(opex_total),
        "fuel_actual": float(fuel_total),
        "distance_km": float(distance_km),
        "active_hours": float(active_hours),
        "idle_hours": float(Decimal(idle_seconds) / Decimal(3600) if idle_seconds else 0),
        "cost_per_hour": float(cost_per_hour),
        "fuel_consumption_per_hour": float(fuel_consumption_per_hour),
        "budget": budget_status,
    }


def summarise_costs(assets: Iterable[Asset], *, start=None, end=None) -> dict:
    start = start or timezone.now().date().replace(month=1, day=1)
    end = end or timezone.now().date()

    per_asset = [summarise_asset_costs(asset, start=start, end=end) for asset in assets]
    totals = defaultdict(Decimal)
    for summary in per_asset:
        totals["capex"] += Decimal(str(summary["capex_actual"]))
        totals["maintenance"] += Decimal(str(summary.get("maintenance_actual", 0)))
        totals["parts"] += Decimal(str(summary.get("parts_actual", 0)))
        totals["opex"] += Decimal(str(summary["opex_actual"]))
        totals["fuel"] += Decimal(str(summary["fuel_actual"]))
        totals["active_hours"] += Decimal(str(summary["active_hours"]))
        totals["idle_hours"] += Decimal(str(summary["idle_hours"]))
        totals["distance_km"] += Decimal(str(summary["distance_km"]))

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": {
            "capex": float(totals["capex"]),
            "maintenance": float(totals["maintenance"]),
            "parts": float(totals["parts"]),
            "opex": float(totals["opex"]),
            "fuel": float(totals["fuel"]),
            "active_hours": float(totals["active_hours"]),
            "idle_hours": float(totals["idle_hours"]),
            "distance_km": float(totals["distance_km"]),
        },
        "assets": per_asset,
    }
