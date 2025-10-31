# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.assets.models import (
    AssetIncident,
    AssetIncidentSeverity,
    AssetIncidentStatus,
    OperatorCertification,
    SafetyChecklistEntry,
    SafetyChecklistTemplate,
    SafetyChecklistStatus,
    SafetyChecklistTrigger,
)
from ralph.assets.notifications import AssetEventType, notify_asset_event


def _base_object(asset):
    return getattr(asset, "baseobject_ptr", None) or asset


def enforce_checklist(asset, trigger: int, checklist_entry_id: Optional[int] = None):
    templates = SafetyChecklistTemplate.applicable_for(asset, trigger)
    if not templates:
        return None

    base_object = _base_object(asset)
    entry = None
    if checklist_entry_id:
        try:
            entry = SafetyChecklistEntry.objects.get(
                pk=checklist_entry_id,
                base_object=base_object,
                template__in=templates,
            )
        except SafetyChecklistEntry.DoesNotExist as exc:
            raise ValidationError(_("Selected checklist entry is invalid.")) from exc
    else:
        entry = (
            SafetyChecklistEntry.objects.filter(
                base_object=base_object,
                template__in=templates,
                status=SafetyChecklistStatus.passed.id,
            )
            .order_by("-completed_at")
            .first()
        )

    if entry is None or not entry.is_valid:
        trigger_choice = SafetyChecklistTrigger.from_id(trigger)
        trigger_name = trigger_choice.name if trigger_choice else str(trigger)
        trigger_desc = trigger_choice.desc if trigger_choice else str(trigger)
        notify_asset_event(
            asset,
            AssetEventType.SAFETY_CHECKLIST_REQUIRED,
            payload={
                "trigger": trigger_name,
                "asset_id": asset.pk,
            },
        )
        raise ValidationError(
            _("A valid %(trigger)s checklist is required before continuing."),
            params={"trigger": trigger_desc},
        )
    return entry


def ensure_operator_certification(user, asset):
    if user is None:
        return
    if OperatorCertification.valid_for(user, asset):
        return
    raise ValidationError(
        _("Operator %(user)s does not hold an active certification for %(asset)s."),
        params={"user": user, "asset": asset},
    )


def log_incident(asset, title, description="", *, severity=None, reported_by=None):
    base_object = _base_object(asset)
    severity = severity or AssetIncidentSeverity.medium.id
    incident = AssetIncident.objects.create(
        base_object=base_object,
        title=title,
        description=description,
        severity=severity,
        reported_by=reported_by,
        status=AssetIncidentStatus.open.id,
    )
    notify_asset_event(
        asset,
        AssetEventType.INCIDENT_REPORTED,
        payload={
            "incident_id": incident.pk,
            "title": title,
            "severity": severity,
        },
    )
    return incident
