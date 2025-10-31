import json

from django.core.management.base import BaseCommand, CommandError

from ralph.assets.models.assets import Asset
from ralph.assets.services.telemetry import build_payload, ingest_telemetry


class Command(BaseCommand):
    help = "Ingest telemetry payloads from stdin or a file (JSON lines)."

    def add_arguments(self, parser):
        parser.add_argument("asset_id", type=int)
        parser.add_argument(
            "--file",
            type=str,
            help="Path to file containing JSONL telemetry events. Defaults to stdin.",
        )

    def handle(self, *args, **options):
        asset_id = options["asset_id"]
        try:
            asset = Asset.objects.get(pk=asset_id)
        except Asset.DoesNotExist:
            raise CommandError("Asset not found.")

        stream = open(options["file"], "r") if options["file"] else self.stdin
        ingested = 0
        for line in stream:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            payload = build_payload(data)
            ingest_telemetry(asset, payload)
            ingested += 1
        if options["file"]:
            stream.close()
        self.stdout.write(self.style.SUCCESS(f"Ingested {ingested} telemetry event(s)."))
