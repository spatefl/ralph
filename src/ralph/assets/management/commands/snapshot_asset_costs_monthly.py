# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ralph.assets.models import BaseObject
from ralph.assets.models.assets import AssetCostSnapshot
from ralph.assets.services.costs import summarise_asset_costs


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _last_of_month(d: date) -> date:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


class Command(BaseCommand):
    help = "Create monthly asset cost snapshots (capex/opex/fuel/parts and active/idle hours)."

    def add_arguments(self, parser):
        parser.add_argument("--month", dest="target", default=None, help="Month ISO (YYYY-MM), defaults to current month")
        parser.add_argument("--limit", type=int, default=0, help="Max assets to snapshot (for testing)")

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get("target"):
            year, month = map(int, options["target"].split("-"))
            snapshot_month = date(year, month, 1)
        else:
            now = timezone.now().date()
            snapshot_month = date(now.year, now.month, 1)

        start = _first_of_month(snapshot_month)
        end = _last_of_month(snapshot_month)

        qs = BaseObject.polymorphic_objects.all()
        if options.get("limit"):
            qs = qs[: options["limit"]]

        created, updated = 0, 0
        for base in qs:
            # summarise_asset_costs expects Asset-like; we pass via base since BaseObject descends
            summary = summarise_asset_costs(base, start=start, end=end)
            obj, was_created = AssetCostSnapshot.objects.update_or_create(
                base_object=base,
                month=start,
                defaults={
                    "capex": summary.get("capex_actual", 0),
                    "opex": summary.get("opex_actual", 0),
                    "maintenance": summary.get("maintenance_actual", 0),
                    "parts": summary.get("parts_actual", 0),
                    "fuel": summary.get("fuel_actual", 0),
                    "active_hours": summary.get("active_hours", 0),
                    "idle_hours": summary.get("idle_hours", 0),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Cost snapshots: created={created} updated={updated} for {snapshot_month:%Y-%m}"))

