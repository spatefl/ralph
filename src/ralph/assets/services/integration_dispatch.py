from __future__ import annotations

import json
import logging
import sys
import types
from typing import Dict

import requests
from django.conf import settings

try:  # maintain compatibility with rq-scheduler <=0.11
    import rq.utils as rq_utils
except Exception:  # pragma: no cover
    rq_utils = None
else:  # pragma: no branch - executed when rq_utils imports cleanly
    if not hasattr(rq_utils, "ColorizingStreamHandler"):
        class ColorizingStreamHandler(logging.StreamHandler):
            """Minimal stub for legacy scheduler imports."""

        rq_utils.ColorizingStreamHandler = ColorizingStreamHandler

    if "rq.compat" not in sys.modules:
        compat = types.ModuleType("rq.compat")
        compat.string_types = (str,)
        compat.text_type = str
        compat.binary_type = bytes

        def as_text(value):
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value

        compat.as_text = as_text
        sys.modules["rq.compat"] = compat

try:
    import django_rq
except ImportError:  # pragma: no cover
    django_rq = None

logger = logging.getLogger(__name__)


def queue_external_event(event: Dict[str, object]):
    if django_rq is None:
        deliver_events_sync(event)
        return

    from ralph.assets.models import IntegrationEndpoint

    for endpoint in IntegrationEndpoint.objects.filter(enabled=True):
        if not endpoint.is_event_supported(event.get("event_type")):
            continue
        django_rq.enqueue(
            deliver_event,
            endpoint.pk,
            event,
            job_timeout=endpoint.timeout_seconds + 5,
            queue=getattr(settings, "ASSETS_INTEGRATION_QUEUE", "default"),
        )


def deliver_events_sync(event: Dict[str, object]):
    from ralph.assets.models import IntegrationEndpoint

    for endpoint in IntegrationEndpoint.objects.filter(enabled=True):
        if endpoint.is_event_supported(event.get("event_type")):
            deliver_event(endpoint.pk, event)


def deliver_event(endpoint_id: int, event: Dict[str, object]):
    from ralph.assets.models import (
        IntegrationDeliveryLog,
        IntegrationDeliveryStatus,
        IntegrationEndpoint,
        IntegrationEndpointType,
    )

    try:
        endpoint = IntegrationEndpoint.objects.get(pk=endpoint_id)
    except IntegrationEndpoint.DoesNotExist:
        logger.warning("Integration endpoint %s vanished", endpoint_id)
        return

    if not endpoint.enabled:
        return

    status = IntegrationDeliveryStatus.success.id
    response_code = None
    response_body = ""
    metadata = {}

    try:
        if endpoint.endpoint_type in (
            IntegrationEndpointType.webhook.id,
            IntegrationEndpointType.n8n.id,
            IntegrationEndpointType.erp.id,
        ):
            response = _post_payload(endpoint, event)
            response_code = response.status_code
            response_body = response.text[:2048]
            metadata["url"] = endpoint.target_url
            if response.status_code >= 400:
                status = IntegrationDeliveryStatus.failure.id
        elif endpoint.endpoint_type == IntegrationEndpointType.celery.id:
            metadata["queue"] = endpoint.queue_name or "default"
            metadata["target"] = endpoint.target_url
            status = _enqueue_celery(endpoint, event)
        else:  # pragma: no cover
            metadata["warning"] = "unsupported endpoint type"
            status = IntegrationDeliveryStatus.failure.id
    except Exception as exc:  # pragma: no cover - defensive log
        status = IntegrationDeliveryStatus.failure.id
        metadata["error"] = str(exc)
        logger.exception("Failed to deliver asset event", extra={"endpoint": endpoint.name})

    IntegrationDeliveryLog.objects.create(
        endpoint=endpoint,
        event_type=str(event.get("event_type")),
        status=status,
        response_code=response_code,
        response_body=response_body,
        metadata=metadata,
    )


def _post_payload(endpoint: IntegrationEndpoint, event: Dict[str, object]):
    headers = {"Content-Type": "application/json"}
    headers.update(endpoint.headers or {})
    if endpoint.secret_token:
        headers["X-Asset-Signature"] = endpoint.secret_token
    timeout = endpoint.timeout_seconds or 10
    return requests.post(endpoint.target_url, headers=headers, data=json.dumps(event), timeout=timeout)


def _enqueue_celery(endpoint: IntegrationEndpoint, event: Dict[str, object]):
    from ralph.assets.models import IntegrationDeliveryStatus

    if not endpoint.target_url:
        return IntegrationDeliveryStatus.failure.id
    try:
        from celery import current_app

        queue = endpoint.queue_name or "default"
        current_app.send_task(endpoint.target_url, args=[event], queue=queue)
        return IntegrationDeliveryStatus.success.id
    except Exception as exc:  # pragma: no cover
        logger.exception("Celery dispatch failed", extra={"endpoint": endpoint.name})
        return IntegrationDeliveryStatus.failure.id
