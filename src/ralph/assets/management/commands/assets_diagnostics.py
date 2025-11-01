# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.core.mail import get_connection
from django.core.files.storage import default_storage
from django.conf import settings
import django_rq


class Command(BaseCommand):
    help = "Run basic diagnostics for SMTP, media storage, and RQ/Redis connectivity."

    def handle(self, *args, **options):
        ok = True

        # SMTP
        try:
            conn = get_connection()
            conn.open()
            conn.close()
            self.stdout.write(self.style.SUCCESS("SMTP: OK (connection opened/closed)"))
        except Exception as exc:
            ok = False
            self.stderr.write(self.style.ERROR(f"SMTP: ERROR – {exc}"))

        # Media storage (writability check where possible)
        try:
            test_path = "diagnostics/test.txt"
            with default_storage.open(test_path, "w") as fh:
                fh.write("ok")
            default_storage.delete(test_path)
            self.stdout.write(self.style.SUCCESS("Media storage: OK (write/delete)"))
        except Exception as exc:
            ok = False
            self.stderr.write(self.style.ERROR(f"Media storage: ERROR – {exc}"))

        # RQ/Redis
        try:
            queue = django_rq.get_queue("default")
            # Execute a trivial no-op to ensure round-trip
            job = queue.enqueue(lambda: True)
            self.stdout.write(self.style.SUCCESS(f"RQ/Redis: OK (enqueued job {job.id})"))
        except Exception as exc:
            ok = False
            self.stderr.write(self.style.ERROR(f"RQ/Redis: ERROR – {exc}"))

        if ok:
            self.stdout.write(self.style.SUCCESS("Diagnostics: ALL OK"))
        else:
            self.stderr.write(self.style.ERROR("Diagnostics: FAILURES detected"))

