from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from ralph.assets.models.assets import Asset
from ralph.assets.notifications import AssetEventType, notify_asset_event


class Command(BaseCommand):
    help = "Check asset budgets and emit notifications for overruns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report overruns without sending notifications.",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=0,
            help="Variance threshold (in currency units) before alerting.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        threshold = Decimal(str(options["threshold"]))
        today = timezone.now().date()

        overruns = 0
        for asset in Asset.objects.all():
            status = asset.budget_status(reference=today)
            capex_variance = Decimal(str(status["capex_variance"]))
            opex_variance = Decimal(str(status["opex_variance"]))
            over_budget = []
            if asset.annual_capex_budget and capex_variance < -threshold:
                over_budget.append("capex")
            if asset.annual_opex_budget and opex_variance < -threshold:
                over_budget.append("opex")
            if not over_budget:
                continue
            overruns += 1
            if dry_run:
                self.stdout.write(f"[DRY-RUN] Budget overrun for {asset}: {over_budget}")
                continue
            notify_asset_event(
                asset,
                AssetEventType.BUDGET_OVERRUN,
                payload={
                    "budget": status,
                    "over_budget": over_budget,
                },
                severity="warning",
                metadata={"source": "check_asset_budgets"},
            )
        verb = "would notify" if dry_run else "notified"
        self.stdout.write(self.style.SUCCESS(f"{verb.title()} {overruns} asset(s) over budget."))
