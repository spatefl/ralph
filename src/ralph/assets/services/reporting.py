# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from django.apps import apps
from django.db.models import Avg, Count, F, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ralph.assets.models import (
    Asset,
    AssetUtilizationSnapshot,
    ComplianceRecord,
    DisposalRecord,
    MaintenanceRecord,
)
from ralph.assets.models.assets import (
    ComplianceRecordStatus,
    DisposalStatus,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
)
from ralph.assets.services.analytics import aggregate_metrics
from ralph.assets.services.costs import summarise_costs


DEFAULT_FUEL_THRESHOLD = Decimal("15")
DEFAULT_WATER_THRESHOLD = Decimal("20")


@dataclass
class AssetFilters:
    model_label: Optional[str] = None
    service_env: Optional[str] = None
    owner: Optional[str] = None
    user: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    deployment_status: Optional[str] = None
    location: Optional[str] = None
    project: Optional[str] = None


def resolve_asset_queryset(filters: AssetFilters) -> Tuple[QuerySet, type]:
    model = Asset
    if filters.model_label:
        try:
            model = apps.get_model(filters.model_label)
        except (LookupError, ValueError):
            model = Asset
    queryset = model._default_manager.all()

    field_names = {field.name for field in model._meta.get_fields()}

    if filters.service_env:
        queryset = queryset.filter(service_env_id=filters.service_env)
    if filters.owner and "owner" in field_names:
        queryset = queryset.filter(owner_id=filters.owner)
    if filters.user and "user" in field_names:
        queryset = queryset.filter(user_id=filters.user)
    if filters.region and "region" in field_names:
        queryset = queryset.filter(region_id=filters.region)
    if filters.status and "status" in field_names:
        queryset = queryset.filter(status=filters.status)
    if filters.deployment_status and "deployment_status" in field_names:
        queryset = queryset.filter(deployment_status=filters.deployment_status)

    if filters.location:
        if "assigned_location" in field_names:
            queryset = queryset.filter(assigned_location__icontains=filters.location)
        elif "location" in field_names:
            queryset = queryset.filter(location__icontains=filters.location)
        elif "deployment_site" in field_names:
            queryset = queryset.filter(deployment_site__icontains=filters.location)

    if filters.project and "deployment_site" in field_names:
        queryset = queryset.filter(deployment_site__icontains=filters.project)

    return queryset, model


def _choice_map(model, field_name: str) -> Dict:
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return {}
    choices = getattr(field, "choices", None) or getattr(field, "_choices", None)
    if not choices:
        return {}
    return {choice[0]: choice[1] for choice in choices}


def _serialize_asset(asset) -> dict:
    base = getattr(asset, "baseobject_ptr", None) or asset
    service_env = getattr(asset, "service_env", None)
    return {
        "asset_id": asset.pk,
        "name": str(asset),
        "hostname": getattr(asset, "hostname", ""),
        "content_type": base.content_type.model if base else "",
        "model": str(getattr(asset, "model", "")) if getattr(asset, "model", None) else "",
        "service_env": str(service_env) if service_env else "",
        "deployment_site": getattr(asset, "deployment_site", ""),
        "assigned_location": getattr(asset, "assigned_location", ""),
        "status": getattr(asset, "status", None),
    }


def inventory_report(queryset: QuerySet, model) -> dict:
    assets = list(queryset.select_related("service_env", "service_env__service"))
    total = len(assets)

    by_type_counter = Counter()
    by_service_counter = Counter()
    by_location_counter = Counter()
    by_status_counter = Counter()

    status_choices = _choice_map(model, "status")

    for asset in assets:
        base = getattr(asset, "baseobject_ptr", None) or asset
        by_type_counter[base.content_type.model if base else model._meta.model_name] += 1
        service = getattr(asset.service_env, "service", None) if getattr(asset, "service_env", None) else None
        if service:
            by_service_counter[str(service)] += 1
        location = getattr(asset, "deployment_site", None) or getattr(asset, "assigned_location", None)
        if location:
            by_location_counter[location] += 1
        status_value = getattr(asset, "status", None)
        if status_value is not None:
            status_label = status_choices.get(status_value, status_value)
            by_status_counter[status_label] += 1

    summary = {
        "total": total,
        "by_type": [{"value": key, "count": value} for key, value in sorted(by_type_counter.items(), key=lambda x: (-x[1], x[0]))],
        "by_service": [{"value": key, "count": value} for key, value in sorted(by_service_counter.items(), key=lambda x: (-x[1], x[0]))],
        "by_location": [{"value": key, "count": value} for key, value in sorted(by_location_counter.items(), key=lambda x: (-x[1], x[0]))],
        "by_status": [{"value": key, "count": value} for key, value in sorted(by_status_counter.items(), key=lambda x: (-x[1], x[0]))],
    }

    asset_rows = []
    for asset in assets:
        row = _serialize_asset(asset)
        status_label = status_choices.get(row["status"], row["status"]) if status_choices else row.get("status")
        row["status_display"] = status_label or ""
        asset_rows.append(row)

    return {"summary": summary, "assets": asset_rows}


def utilization_report(queryset: QuerySet, *, start: Optional[datetime] = None, end: Optional[datetime] = None) -> dict:
    if start and timezone.is_naive(start):
        start = timezone.make_aware(start)
    end = end or timezone.now()
    if end and timezone.is_naive(end):
        end = timezone.make_aware(end)

    base_ids = list(
        queryset.values_list("baseobject_ptr_id", flat=True)
    ) or list(queryset.values_list("pk", flat=True))

    snapshots = AssetUtilizationSnapshot.objects.filter(base_object_id__in=base_ids)
    if start:
        snapshots = snapshots.filter(date__gte=start.date())
    if end:
        snapshots = snapshots.filter(date__lte=end.date())

    utilization = snapshots.values("base_object_id").annotate(
        active_seconds=Sum("active_seconds"),
        idle_seconds=Sum("idle_seconds"),
        distance_km=Coalesce(Sum("distance_km"), Decimal("0")),
    )
    utilization_lookup = {
        row["base_object_id"]: row for row in utilization
    }

    maintenance = MaintenanceRecord.objects.filter(
        base_object_id__in=base_ids,
        out_of_service=True,
    )
    if start:
        maintenance = maintenance.filter(opened_at__gte=start)
    if end:
        maintenance = maintenance.filter(opened_at__lte=end)

    downtime_hours = defaultdict(Decimal)
    for record in maintenance:
        start_time = record.opened_at
        end_time = record.closed_at or end
        if start and start_time < start:
            start_time = start
        if end and end_time > end:
            end_time = end
        delta = max((end_time - start_time).total_seconds(), 0)
        downtime_hours[record.base_object_id] += Decimal(delta) / Decimal(3600)

    assets = []
    total_active = Decimal("0")
    total_idle = Decimal("0")
    total_distance = Decimal("0")
    total_downtime = Decimal("0")
    availability_rates: List[Decimal] = []

    window_seconds = Decimal("0")
    if start and end:
        window_seconds = Decimal((end - start).total_seconds())
    elif end:
        # fallback 24h window when only end is provided
        window_seconds = Decimal(24 * 3600)

    asset_lookup = {asset.pk: asset for asset in queryset}
    for asset in queryset:
        base_id = getattr(asset, "baseobject_ptr_id", None) or asset.pk
        utilization_row = utilization_lookup.get(base_id, {})
        active_seconds = Decimal(utilization_row.get("active_seconds") or 0)
        idle_seconds = Decimal(utilization_row.get("idle_seconds") or 0)
        distance_km = Decimal(utilization_row.get("distance_km") or 0)
        active_hours = active_seconds / Decimal(3600) if active_seconds else Decimal("0")
        idle_hours = idle_seconds / Decimal(3600) if idle_seconds else Decimal("0")
        downtime = downtime_hours.get(base_id, Decimal("0"))

        total = active_hours + idle_hours
        utilization_rate = float(active_hours / total) if total else 0.0

        availability_rate = None
        if window_seconds > 0:
            availability_rate = float(max(Decimal(0), (window_seconds / Decimal(3600)) - downtime) / (window_seconds / Decimal(3600)))
            availability_rates.append(Decimal(str(availability_rate)))

        assets.append(
            {
                **_serialize_asset(asset),
                "active_hours": float(active_hours),
                "idle_hours": float(idle_hours),
                "downtime_hours": float(downtime),
                "utilization_rate": round(utilization_rate, 4),
                "availability_rate": round(availability_rate, 4) if availability_rate is not None else None,
                "distance_km": float(distance_km),
            }
        )
        total_active += active_hours
        total_idle += idle_hours
        total_distance += distance_km
        total_downtime += downtime

    period = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }
    avg_availability = float(
        (sum(availability_rates) / Decimal(len(availability_rates)))
    ) if availability_rates else 0.0

    summary = {
        "total_active_hours": float(total_active),
        "total_idle_hours": float(total_idle),
        "total_downtime_hours": float(total_downtime),
        "total_distance_km": float(total_distance),
        "average_utilization_rate": round(
            float(total_active / (total_active + total_idle)) if (total_active + total_idle) else 0.0,
            4,
        ),
        "average_availability_rate": round(avg_availability, 4),
    }
    return {"period": period, "summary": summary, "assets": assets}


def maintenance_compliance_report(queryset: QuerySet, *, reference: Optional[datetime] = None) -> dict:
    reference = reference or timezone.now()
    base_ids = list(
        queryset.values_list("baseobject_ptr_id", flat=True)
    ) or list(queryset.values_list("pk", flat=True))

    maintenance_qs = MaintenanceRecord.objects.filter(base_object_id__in=base_ids)
    maintenance_open = maintenance_qs.filter(
        status__in=[
            MaintenanceRecordStatus.open.id,
            MaintenanceRecordStatus.in_progress.id,
        ]
    )
    maintenance_overdue = [
        record.pk for record in maintenance_open if record.is_overdue()
    ]

    due_soon = maintenance_qs.filter(
        expected_completion__isnull=False,
        expected_completion__lte=reference.date() + timezone.timedelta(days=7),
        status__in=[
            MaintenanceRecordStatus.open.id,
            MaintenanceRecordStatus.in_progress.id,
        ],
    )

    maintenance_assets = []
    for record in maintenance_open.select_related("base_object"):
        asset_obj = queryset.model.objects.filter(pk=record.base_object_id).first()
        if not asset_obj:
            continue
        maintenance_assets.append(
            {
                **_serialize_asset(asset_obj),
                "record_id": record.pk,
                "opened_at": record.opened_at.isoformat(),
                "expected_completion": record.expected_completion.isoformat()
                if record.expected_completion
                else None,
                "is_overdue": record.pk in maintenance_overdue,
                "record_type": record.get_record_type_display(),
            }
        )

    compliance_qs = ComplianceRecord.objects.filter(base_object_id__in=base_ids)
    compliance_summary = {
        "compliant": compliance_qs.filter(status=ComplianceRecordStatus.compliant.id).count(),
        "due_soon": compliance_qs.filter(status=ComplianceRecordStatus.due_soon.id).count(),
        "overdue": compliance_qs.filter(status__in=[ComplianceRecordStatus.overdue.id, ComplianceRecordStatus.failed.id]).count(),
        "total": compliance_qs.count(),
    }

    compliance_assets = []
    for record in compliance_qs.select_related("base_object"):
        asset_obj = queryset.model.objects.filter(pk=record.base_object_id).first()
        if not asset_obj:
            continue
        compliance_assets.append(
            {
                **_serialize_asset(asset_obj),
                "record_id": record.pk,
                "title": record.title,
                "status": record.get_status_display(),
                "record_type": record.get_record_type_display(),
                "expires_on": record.expires_on.isoformat()
                if record.expires_on
                else None,
            }
        )

    maintenance_summary = {
        "open": maintenance_open.count(),
        "overdue": len(maintenance_overdue),
        "due_within_7d": due_soon.count(),
        "total": maintenance_qs.count(),
    }

    return {
        "maintenance": {
            "summary": maintenance_summary,
            "records": maintenance_assets,
        },
        "compliance": {
            "summary": compliance_summary,
            "records": compliance_assets,
        },
    }


def financial_report(queryset: QuerySet, *, start=None, end=None) -> dict:
    assets = list(queryset)
    summary = summarise_costs(assets, start=start, end=end)
    return summary


def lifecycle_report(queryset: QuerySet, model) -> dict:
    assets = list(queryset)
    status_choices = _choice_map(model, "status")
    status_counts = Counter()
    for asset in assets:
        status_value = getattr(asset, "status", None)
        status_label = status_choices.get(status_value, status_value)
        if status_label is not None:
            status_counts[status_label] += 1

    disposal_records = DisposalRecord.objects.filter(
        base_object_id__in=[
            getattr(asset, "baseobject_ptr_id", None) or asset.pk for asset in assets
        ]
    )
    disposal_counts = Counter(
        disposal_records.values_list("status", flat=True)
    )
    disposal_status_map = {choice[0]: choice[1] for choice in DisposalStatus()}

    metrics = aggregate_metrics(assets)

    return {
        "status_breakdown": [{"status": key, "count": value} for key, value in status_counts.items()],
        "disposal": [
            {
                "status": disposal_status_map.get(key, key),
                "count": value,
            }
            for key, value in disposal_counts.items()
        ],
        "transition_metrics": metrics,
    }


def _threshold_for(asset, field: str, default: Decimal) -> Decimal:
    method_name = f"{field}_threshold"
    if hasattr(asset, method_name):
        try:
            threshold = getattr(asset, method_name)()
            return Decimal(str(threshold))
        except Exception:
            pass
    value = getattr(asset, f"{field}_threshold_percent", None)
    if value is not None:
        return Decimal(str(value))
    return default


def resource_report(queryset: QuerySet, *, reference: Optional[datetime] = None) -> dict:
    reference = reference or timezone.now()
    assets = list(queryset)
    fuel_assets = []
    water_assets = []
    anomalies = []

    total_fuel_capacity = Decimal("0")
    total_fuel_available = Decimal("0")
    total_water_capacity = Decimal("0")
    total_water_available = Decimal("0")

    for asset in assets:
        basic = _serialize_asset(asset)
        if hasattr(asset, "fuel_capacity_liters") and asset.fuel_capacity_liters:
            threshold = _threshold_for(asset, "fuel_level", DEFAULT_FUEL_THRESHOLD)
            level_percent = Decimal(str(asset.fuel_level_percent or 0))
            capacity = Decimal(str(asset.fuel_capacity_liters or 0))
            available = (capacity * level_percent) / Decimal(100) if capacity else Decimal("0")
            total_fuel_capacity += capacity
            total_fuel_available += available
            record = {
                **basic,
                "capacity_liters": float(capacity),
                "level_percent": float(level_percent),
                "available_liters": float(available),
                "threshold_percent": float(threshold),
                "last_reported_at": getattr(asset, "last_status_change", None).isoformat()
                if getattr(asset, "last_status_change", None)
                else None,
            }
            fuel_assets.append(record)
            if level_percent <= threshold:
                anomalies.append({**record, "resource": "fuel"})

        if hasattr(asset, "water_tank_capacity_liters") and asset.water_tank_capacity_liters:
            threshold = _threshold_for(asset, "water_level", DEFAULT_WATER_THRESHOLD)
            level_percent = Decimal(str(asset.water_level_percent or 0))
            capacity = Decimal(str(asset.water_tank_capacity_liters or 0))
            available = (capacity * level_percent) / Decimal(100) if capacity else Decimal("0")
            total_water_capacity += capacity
            total_water_available += available
            record = {
                **basic,
                "capacity_liters": float(capacity),
                "level_percent": float(level_percent),
                "available_liters": float(available),
                "threshold_percent": float(threshold),
                "last_reported_at": getattr(asset, "last_status_change", None).isoformat()
                if getattr(asset, "last_status_change", None)
                else None,
            }
            water_assets.append(record)
            if level_percent <= threshold:
                anomalies.append({**record, "resource": "water"})

    def _safe_percentage(available: Decimal, capacity: Decimal) -> float:
        if not capacity:
            return 0.0
        return float((available / capacity) * Decimal(100))

    return {
        "reference": reference.isoformat(),
        "fuel": {
            "total_capacity_liters": float(total_fuel_capacity),
            "available_liters": float(total_fuel_available),
            "average_level_percent": _safe_percentage(total_fuel_available, total_fuel_capacity),
            "assets": fuel_assets,
        },
        "water": {
            "total_capacity_liters": float(total_water_capacity),
            "available_liters": float(total_water_available),
            "average_level_percent": _safe_percentage(total_water_available, total_water_capacity),
            "assets": water_assets,
        },
        "anomalies": anomalies,
    }


def operations_dashboard(queryset: QuerySet, model) -> dict:
    reference = timezone.now()
    inventory = inventory_report(queryset, model)
    utilization = utilization_report(queryset, start=reference - timezone.timedelta(days=30), end=reference)
    maintenance = maintenance_compliance_report(queryset, reference=reference)
    resources = resource_report(queryset, reference=reference)
    return {
        "inventory": inventory["summary"],
        "utilization": utilization["summary"],
        "maintenance": maintenance["maintenance"]["summary"],
        "resources": {
            "fuel": resources["fuel"],
            "water": resources["water"],
            "anomalies": resources["anomalies"],
        },
    }


def compliance_dashboard(queryset: QuerySet, model) -> dict:
    reference = timezone.now()
    maintenance = maintenance_compliance_report(queryset, reference=reference)
    lifecycle = lifecycle_report(queryset, model)
    return {
        "maintenance": maintenance["maintenance"]["summary"],
        "compliance": maintenance["compliance"]["summary"],
        "lifecycle": lifecycle["status_breakdown"],
        "disposal": lifecycle["disposal"],
    }


def finance_dashboard(queryset: QuerySet, *, start=None, end=None) -> dict:
    now = timezone.now().date()
    start = start or now.replace(month=1, day=1)
    summary = summarise_costs(list(queryset), start=start, end=end or now)
    return summary
