import os
import pkg_resources

from ralph.lib.hooks.main import get_hook, hook_name_to_env_name


def _register_default_hooks():
    defaults = {
        "back_office.transition_action.email_context": "ralph.back_office.helpers:get_email_context_for_transition",
        "assets.maintenance.notification": "ralph.assets.notifications:default_dispatcher",
    }

    location = os.path.dirname(__file__)
    dist = pkg_resources.Distribution(
        location=location,
        project_name="ralph-local-hooks",
    )
    dist._ep_map = {}
    added = False

    for group, target in defaults.items():
        # When Ralph isn't installed as a package (e.g. editable install failure),
        # the entry point group may be empty which breaks startup checks. Provide
        # the default implementation dynamically so migrations/tests can run.
        if any(True for _ in pkg_resources.iter_entry_points(group)):
            continue

        entry_point = pkg_resources.EntryPoint.parse(
            f"default = {target}",
            dist=dist,
        )
        dist._ep_map.setdefault(group, {})["default"] = entry_point
        added = True

    if added:
        pkg_resources.working_set.add(dist, entry=location)


_register_default_hooks()

__all__ = ["get_hook", "hook_name_to_env_name"]
