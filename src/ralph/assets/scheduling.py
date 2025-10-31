# -*- coding: utf-8 -*-
import logging
import os
import sys
from dataclasses import dataclass
from datetime import timedelta

import django_rq
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledCommand:
    identifier: str
    command: str
    interval_seconds: int
    kwargs: dict
    initial_delay_seconds: int = 0


def _is_enabled() -> bool:
    return getattr(settings, "ASSETS_SCHEDULER_ENABLED", True)


def _interval(value: int, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _scheduled_commands():
    commands = [
        ScheduledCommand(
            identifier="assets.schedule_maintenance",
            command="schedule_maintenance",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_MAINTENANCE_INTERVAL", 3600),
                3600,
            ),
            kwargs={"verbosity": 0},
        ),
        ScheduledCommand(
            identifier="assets.check_compliance",
            command="check_compliance",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_COMPLIANCE_INTERVAL", 86400),
                86400,
            ),
            kwargs={"verbosity": 0},
            initial_delay_seconds=300,
        ),
        ScheduledCommand(
            identifier="assets.check_asset_budgets",
            command="check_asset_budgets",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_BUDGET_INTERVAL", 86400),
                86400,
            ),
            kwargs={"verbosity": 0},
            initial_delay_seconds=600,
        ),
        ScheduledCommand(
            identifier="assets.check_inventory",
            command="check_inventory",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_INVENTORY_INTERVAL", 21600),
                21600,
            ),
            kwargs={"verbosity": 0},
            initial_delay_seconds=900,
        ),
        ScheduledCommand(
            identifier="assets.send_asset_digest",
            command="send_asset_digest",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_DIGEST_INTERVAL", 604800),
                604800,
            ),
            kwargs={"verbosity": 0},
            initial_delay_seconds=1200,
        ),
        ScheduledCommand(
            identifier="assets.check_sla",
            command="check_sla",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_SLA_INTERVAL", 3600),
                3600,
            ),
            kwargs={"verbosity": 0},
        ),
        ScheduledCommand(
            identifier="assets.forecast_health",
            command="forecast_asset_health",
            interval_seconds=_interval(
                getattr(settings, "ASSETS_SCHEDULER_FORECAST_INTERVAL", 43200),
                43200,
            ),
            kwargs={"verbosity": 0},
            initial_delay_seconds=1800,
        ),
    ]
    # Dynamically register saved report configs
    try:
        from ralph.assets.models.assets import ReportConfig

        for cfg in ReportConfig.objects.filter(is_active=True, schedule_interval_seconds__gt=0):
            commands.append(
                ScheduledCommand(
                    identifier=f"report_config.{cfg.pk}",
                    command="run_report_config",
                    interval_seconds=int(cfg.schedule_interval_seconds or 0),
                    kwargs={"config_id": cfg.pk, "verbosity": 0},
                    initial_delay_seconds=int(cfg.initial_delay_seconds or 0),
                )
            )
    except Exception as exc:  # pragma: no cover – scheduler should not crash on import
        logger.warning("Unable to load ReportConfig scheduled jobs: %s", exc)

    return commands


def ensure_periodic_jobs():
    if not _is_enabled():
        logger.info("Asset background scheduler disabled via settings.")
        return

    queue_name = getattr(settings, "ASSETS_SCHEDULER_QUEUE", "default")
    try:
        scheduler = django_rq.get_scheduler(queue_name)
    except Exception as exc:  # pragma: no cover - defensive safeguard
        logger.warning(
            "Unable to initialise RQ scheduler for queue '%s': %s",
            queue_name,
            exc,
        )
        return

    existing_jobs = {
        job.meta.get("asset_scheduler_id"): job for job in scheduler.get_jobs()
    }
    configured_ids = set()

    for config in _scheduled_commands():
        configured_ids.add(config.identifier)
        if config.interval_seconds <= 0:
            logger.info(
                "Skipping scheduler registration for %s (disabled interval).",
                config.identifier,
            )
            continue

        job = existing_jobs.get(config.identifier)
        if job:
            current_interval = int(job.meta.get("interval_seconds", 0))
            if current_interval == config.interval_seconds:
                continue
            scheduler.cancel(job)
            logger.info(
                "Re-scheduling %s due to interval change (%s -> %s).",
                config.identifier,
                current_interval,
                config.interval_seconds,
            )

        schedule_at = timezone.now() + timedelta(seconds=config.initial_delay_seconds)
        job = scheduler.schedule(
            scheduled_time=schedule_at,
            func=call_command,
            args=(config.command,),
            kwargs=config.kwargs,
            interval=config.interval_seconds,
            repeat=None,
            meta={
                "asset_scheduler_id": config.identifier,
                "interval_seconds": config.interval_seconds,
            },
        )
        logger.info(
            "Scheduled %s (%s) every %ss on queue '%s' (job id %s).",
            config.identifier,
            config.command,
            config.interval_seconds,
            queue_name,
            job.id,
        )

    for identifier, job in existing_jobs.items():
        if identifier in configured_ids or identifier is None:
            continue
        logger.info("Removing orphaned asset scheduler job %s.", job.id)
        scheduler.cancel(job)


def _should_autoregister() -> bool:
    if not _is_enabled():
        return False
    # Allow disabling during image builds or certain commands
    if os.environ.get("DISABLE_RQ_SCHEDULER") == "1":
        return False
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    skip_cmds = {
        "collectstatic",
        "makemigrations",
        "migrate",
        "check",
        "compilemessages",
        "test",
        "shell",
        "loaddata",
        "dumpdata",
    }
    if cmd in skip_cmds:
        return False
    # Default to enabled unless explicitly turned off
    return os.environ.get("ASSETS_SCHEDULER_AUTOREGISTER", "1") == "1"


if _should_autoregister():
    ensure_periodic_jobs()
