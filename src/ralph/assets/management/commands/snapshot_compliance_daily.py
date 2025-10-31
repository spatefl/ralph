# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ralph.assets.models import BaseObject
from ralph.assets.models.assets import (
    ComplianceRecord,
    ComplianceRecordStatus,
    ComplianceSnapshot,
    ComplianceSeverity,
)


def _risk_score_for(record: ComplianceRecord) -> int:
    # Risk scoring: base on status + template severity + missing docs
    status_score = 0
    if record.status == ComplianceRecordStatus.overdue.id:
        status_score = 4
    elif record.status == ComplianceRecordStatus.due_soon.id:
        status_score = 2
    # severity from template
    severity_score = 0
    template = getattr(record, "template", None)
    if template is not None and template.severity:
        # map low=1, medium=2, high=3, critical=4
        severity_score = int(template.severity)
    # required docs
    missing_doc_score = 0
    if template is not None and template.required_documents:
        has_doc = bool(record.document or record.document_url)
        if not has_doc:
            missing_doc_score = 1
    return status_score + severity_score + missing_doc_score


class Command(BaseCommand):
    help = "Create daily compliance snapshots per asset."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="target", default=None, help="Date ISO (YYYY-MM-DD), defaults to today")
        parser.add_argument("--limit", type=int, default=0, help="Max assets to snapshot (for testing)")

    @transaction.atomic
    def handle(self, *args, **options):
        target = options.get("target")
        if target:
            snapshot_date = date.fromisoformat(target)
        else:
            snapshot_date = timezone.now().date()

        qs = BaseObject.polymorphic_objects.all()
        if options.get("limit"):
            qs = qs[: options["limit"]]

        created, updated = 0, 0
        for base in qs:
            record = (
                ComplianceRecord.objects.filter(base_object=base)
                .order_by("-expires_on", "-pk")
                .first()
            )
            if record:
                status_label = record.get_status_display()
                expires_on = record.expires_on
                risk_score = _risk_score_for(record)
            else:
                status_label, expires_on, risk_score = "", None, 0

            obj, was_created = ComplianceSnapshot.objects.update_or_create(
                base_object=base,
                date=snapshot_date,
                defaults={
                    "status_label": status_label,
                    "expires_on": expires_on,
                    "risk_score": risk_score,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Compliance snapshots: created={created} updated={updated} for {snapshot_date}"))
