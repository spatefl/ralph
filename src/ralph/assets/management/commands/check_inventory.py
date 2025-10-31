# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.db.models import F, Q

from ralph.assets.models import SparePartStock


class Command(BaseCommand):
    help = "Check spare part stock levels and emit restock notifications."

    def handle(self, *args, **options):
        queryset = SparePartStock.objects.filter(is_active=True, part__is_active=True)
        queryset = queryset.filter(
            Q(reorder_point__isnull=False, quantity_on_hand__lte=F("reorder_point"))
            | Q(
                reorder_point__isnull=True,
                quantity_on_hand__lte=F("part__restock_threshold"),
            )
        ).select_related("part")

        count = 0
        for stock in queryset:
            stock.trigger_restock_alert()
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {count} low-stock locations."))
