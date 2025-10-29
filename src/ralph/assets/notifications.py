import logging
from enum import Enum
from typing import Any, Dict, Optional

from django.utils import timezone

from ralph.lib.hooks import get_hook

logger = logging.getLogger(__name__)


class AssetEventType(str, Enum):
    MAINTENANCE_STARTED = "maintenance.started"
    MAINTENANCE_COMPLETED = "maintenance.completed"
    MAINTENANCE_OVERDUE = "maintenance.overdue"
    STATUS_ACTIVATED = "status.activated"
    STATUS_RETIRED = "status.retired"
    INCIDENT_DAMAGE = "incident.damage"
    THRESHOLD_BREACH = "threshold.breach"
    COMPLIANCE_DUE = "compliance.due"
    REFUEL_LOGGED = "maintenance.refuel"
    APPROVAL_REQUIRED = "approval.required"


def default_dispatcher(asset: Any, event: Dict[str, Any]) -> None:
    logger.info(
        "Asset event %s for %s", event.get("event_type"), asset or event.get("asset")
    )


def notify_asset_event(
    asset,
    event_type: AssetEventType,
    *,
    payload: Optional[Dict[str, Any]] = None,
    severity: str = "info",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    payload = payload or {}
    metadata = metadata or {}
    event = {
        "asset": {
            "id": getattr(asset, "pk", None),
            "model": asset._meta.label if hasattr(asset, "_meta") else None,
            "hostname": getattr(asset, "hostname", None),
            "barcode": getattr(asset, "barcode", None),
            "display": str(asset),
        },
        "event_type": str(event_type),
        "severity": severity,
        "payload": payload,
        "metadata": metadata,
        "timestamp": timezone.now().isoformat(),
    }
    try:
        dispatcher = get_hook("assets.maintenance.notification")
    except Exception:
        logger.debug("Asset notification hook unavailable; using default dispatcher.")
        dispatcher = default_dispatcher

    try:
        dispatcher(asset=asset, event=event)
        return True
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to dispatch asset notification", extra=event)
        return False
