# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand

from ralph.assets.models.assets import ReportConfig


DEFAULT_CONFIGS = [
    {
        "name": "Inventory – All families",
        "endpoint": "/api/reporting/inventory/",
        "params": {"family": "all"},
        "schedule_interval_seconds": 0,
    },
    {
        "name": "Operations – Utilization (weekly)",
        "endpoint": "/api/reporting/utilization/",
        "params": {"family": "all"},
        "schedule_interval_seconds": 7 * 24 * 3600,
        "initial_delay_seconds": 3600,
    },
    {
        "name": "Compliance – Due soon & overdue (daily)",
        "endpoint": "/api/reporting/maintenance-compliance/",
        "params": {"status": "due|overdue"},
        "schedule_interval_seconds": 24 * 3600,
        "initial_delay_seconds": 600,
    },
    {
        "name": "Finance – Monthly costs",
        "endpoint": "/api/reporting/financial/",
        "params": {"period": "month"},
        "schedule_interval_seconds": 0,
    },
]


class Command(BaseCommand):
    help = "Seed a few default ReportConfig templates for dashboards and exports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--activate",
            action="store_true",
            dest="activate",
            help="Mark seeded configs as active for scheduling (if interval > 0).",
        )

    def handle(self, *args, **options):
        activate = options.get("activate", False)
        created = 0
        for cfg in DEFAULT_CONFIGS:
            obj, was_created = ReportConfig.objects.get_or_create(
                name=cfg["name"],
                defaults={
                    "endpoint": cfg["endpoint"],
                    "params": cfg.get("params", {}),
                    "schedule_interval_seconds": cfg.get("schedule_interval_seconds", 0),
                    "initial_delay_seconds": cfg.get("initial_delay_seconds", 0),
                    "is_active": activate and cfg.get("schedule_interval_seconds", 0) > 0,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} report config(s)."))

