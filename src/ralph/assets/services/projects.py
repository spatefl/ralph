from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from ralph.assets.models import BaseObject, DeploymentEntry, DeploymentStatus, Location, Project

User = get_user_model()


def _close_other_active_entries(entry: DeploymentEntry) -> None:
    DeploymentEntry.objects.filter(
        base_object=entry.base_object,
        ended_at__isnull=True,
    ).exclude(pk=entry.pk).update(ended_at=timezone.now())


def _sync_assignment(
    entry: DeploymentEntry,
    assignee: Optional[User],
    handover_notes: Optional[str] = None,
) -> None:
    now = timezone.now()
    active_qs = entry.assignments.select_for_update().filter(ended_at__isnull=True)
    if not assignee:
        if active_qs.exists():
            update_fields = {"ended_at": now}
            if handover_notes:
                update_fields["handover_notes"] = handover_notes
            active_qs.update(**update_fields)
        return
    existing = active_qs.filter(user=assignee).first()
    if existing:
        return
    if active_qs.exists():
        update_fields = {"ended_at": now}
        if handover_notes:
            update_fields["handover_notes"] = handover_notes
        active_qs.update(**update_fields)
    entry.assignments.create(user=assignee, started_at=now)


@transaction.atomic
def assign_asset_to_project(
    *,
    project: Project,
    asset: BaseObject,
    assignee: Optional[User] = None,
    status: Optional[int] = None,
    location: Optional[str] = None,
    location_ref: Optional[Location] = None,
    shift_label: Optional[str] = None,
    notes: Optional[str] = None,
    started_at=None,
    handover_notes: Optional[str] = None,
) -> DeploymentEntry:
    status = status or DeploymentStatus.deployed.id
    assignee = assignee or (project.default_assignee() if project else None)
    target_team = project.default_team if project else None
    location_ref = location_ref or (project.location if project else None)
    if location_ref and location is None:
        location = location_ref.name
    if location is None:
        location = project.location_name if project else ""
    started_at = started_at or timezone.now()

    entry = (
        DeploymentEntry.objects.select_for_update()
        .filter(
            base_object=asset,
            project=project,
            ended_at__isnull=True,
        )
        .order_by("-started_at", "-pk")
        .first()
    )

    if entry is None:
        entry = DeploymentEntry.objects.create(
            base_object=asset,
            project=project,
            status=status,
            shift_label=shift_label or "",
            location=location or "",
            location_ref=location_ref,
            assigned_to_user=assignee,
            assigned_to_team=target_team,
            started_at=started_at,
            notes=notes or "",
        )
    else:
        updates = set()
        if entry.status != status:
            entry.status = status
            updates.add("status")
        if shift_label is not None and entry.shift_label != shift_label:
            entry.shift_label = shift_label
            updates.add("shift_label")
        if location is not None and entry.location != location:
            entry.location = location
            updates.add("location")
        new_location_id = location_ref.id if location_ref else None
        if entry.location_ref_id != new_location_id:
            entry.location_ref = location_ref
            updates.add("location_ref")
        if entry.assigned_to_team != target_team:
            entry.assigned_to_team = target_team
            updates.add("assigned_to_team")
        if entry.project_id != (project.id if project else None):
            entry.project = project
            updates.add("project")
        if notes is not None and entry.notes != (notes or ""):
            entry.notes = notes or ""
            updates.add("notes")
        new_assignee_id = assignee.id if assignee else None
        if entry.assigned_to_user_id != new_assignee_id:
            entry.assigned_to_user = assignee
            updates.add("assigned_to_user")
        if updates:
            updates.add("modified")
            entry.save(update_fields=list(updates))

    _sync_assignment(entry, assignee, handover_notes=handover_notes)
    _close_other_active_entries(entry)
    return entry
