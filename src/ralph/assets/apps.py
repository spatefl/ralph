import os
import sys
from django.conf import settings

from ralph.apps import RalphAppConfig


class AssetsConfig(RalphAppConfig):
    name = "ralph.assets"
    default = True

    def get_load_modules_when_ready(self):
        modules = ["signals"]
        # Avoid importing the scheduler during build / management commands where
        # Redis is not available (collectstatic, migrations, checks, tests), or
        # when explicitly disabled via env.
        disable = os.environ.get("DISABLE_RQ_SCHEDULER") == "1"
        cmd = sys.argv[1] if len(sys.argv) > 1 else ""
        skip_cmds = {
            "collectstatic",
            "makemigrations",
            "migrate",
            "check",
            "compilemessages",
            "test",
            "shell",
            "loaddata",
            "dumpdata",
        }
        if not disable and cmd not in skip_cmds:
            modules.append("scheduling")
        if settings.ENABLE_HERMES_INTEGRATION:
            modules.append("subscribers")
        return modules
