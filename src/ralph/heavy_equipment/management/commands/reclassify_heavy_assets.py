# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType

from ralph.heavy_equipment.models import HeavyEquipmentAsset
from ralph.trailers.models import TrailerAsset
from ralph.power.models import PowerAsset
from ralph.assets.models.base import BaseObject


POWER_TYPES = {"generator", "light_tower", "pump"}
TRAILER_TYPES = {"trailer", "tank"}


class Command(BaseCommand):
    help = (
        "Reclassify HeavyEquipmentAsset records into TrailerAsset/PowerAsset and update polymorphic content types.\n"
        "Run without --apply for a dry run summary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            dest="apply",
            help="Apply changes (default is dry-run).",
        )

    def handle(self, *args, **options):
        do_apply = options.get("apply", False)

        trailer_ct = ContentType.objects.get_for_model(TrailerAsset)
        power_ct = ContentType.objects.get_for_model(PowerAsset)

        he_qs = HeavyEquipmentAsset.objects.only("pk", "equipment_type")
        trailer_candidates = list(
            he_qs.filter(equipment_type__in=TRAILER_TYPES).values_list("pk", "equipment_type")
        )
        power_candidates = list(
            he_qs.filter(equipment_type__in=POWER_TYPES).values_list("pk", "equipment_type")
        )

        existing_trailers = set(
            TrailerAsset.objects.values_list("heavyequipmentasset_ptr_id", flat=True)
        )
        existing_power = set(
            PowerAsset.objects.values_list("heavyequipmentasset_ptr_id", flat=True)
        )

        to_make_trailers = [
            (pk, et)
            for pk, et in trailer_candidates
            if pk not in existing_trailers
        ]
        to_make_power = [
            (pk, et)
            for pk, et in power_candidates
            if pk not in existing_power
        ]

        self.stdout.write(
            f"Trailer candidates: {len(trailer_candidates)} (create {len(to_make_trailers)})"
        )
        self.stdout.write(
            f"Power candidates: {len(power_candidates)} (create {len(to_make_power)})"
        )

        if not do_apply:
            self.stdout.write("Dry run complete. Use --apply to perform changes.")
            return

        # Create missing TrailerAsset rows
        trailer_bulk = []
        for pk, etype in to_make_trailers:
            subtype = "water" if etype == "tank" else "specialty"
            trailer_bulk.append(
                TrailerAsset(heavyequipmentasset_ptr_id=pk, trailer_subtype=subtype)
            )
        if trailer_bulk:
            TrailerAsset.objects.bulk_create(trailer_bulk, ignore_conflicts=True)

        # Create missing PowerAsset rows
        power_bulk = []
        for pk, etype in to_make_power:
            power_type = etype if etype in POWER_TYPES else "generator"
            power_bulk.append(
                PowerAsset(heavyequipmentasset_ptr_id=pk, power_asset_type=power_type)
            )
        if power_bulk:
            PowerAsset.objects.bulk_create(power_bulk, ignore_conflicts=True)

        # Update BaseObject.content_type
        trailer_ids = [pk for pk, _ in trailer_candidates]
        power_ids = [pk for pk, _ in power_candidates]
        if trailer_ids:
            BaseObject.objects.filter(pk__in=trailer_ids).update(content_type_id=trailer_ct.id)
        if power_ids:
            BaseObject.objects.filter(pk__in=power_ids).update(content_type_id=power_ct.id)

        self.stdout.write(
            self.style.SUCCESS(
                f"Reclassification complete. Trailers set: {len(trailer_ids)}, Power set: {len(power_ids)}"
            )
        )

