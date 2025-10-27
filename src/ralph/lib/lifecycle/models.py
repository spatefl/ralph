import logging
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class LifecycleStatusMixin:
    """
    Helper mixin providing guarded lifecycle status transitions with auditing hooks.
    Classes mixing this in must define:
      * STATUS_FIELD (name of the status attribute, defaults to ``status``)
      * STATUS_TRANSITIONS (dict mapping current status -> iterable of allowed targets)
      * create_status_log(user, old_status, new_status, note="", metadata=None)
    Optional hooks:
      * pre_status_change(...)
      * post_status_change(...)
    """

    STATUS_FIELD = "status"
    STATUS_TRANSITIONS = {}

    def get_current_status(self):
        return getattr(self, self.STATUS_FIELD)

    def get_allowed_transitions(self, status=None):
        status = self.get_current_status() if status is None else status
        return set(self.STATUS_TRANSITIONS.get(status, ()))

    def pre_status_change(self, old_status, new_status, user, note="", metadata=None):
        """
        Hook executed before persisting the status change.
        May mutate the instance and should return an iterable of fields that were updated.
        """
        return []

    def post_status_change(self, old_status, new_status, user, note="", metadata=None):
        """
        Hook executed after the status change and audit log creation.
        Default implementation emits a debug log entry.
        """
        logger.info(
            "%s status changed from %s to %s",
            self.__class__.__name__,
            old_status,
            new_status,
            extra={
                "asset_id": getattr(self, "pk", None),
                "old_status": old_status,
                "new_status": new_status,
                "user_id": getattr(user, "pk", None),
            },
        )

    def change_status(self, user, new_status, note="", metadata=None):
        """
        Persist a status change following the configured transition rules.
        Returns True when a change has been applied, False if the value was unchanged.
        Raises ValidationError when transition is not allowed.
        """
        metadata = metadata or {}
        current_status = self.get_current_status()
        if new_status == current_status:
            return False

        allowed_targets = self.get_allowed_transitions(current_status)
        if new_status not in allowed_targets:
            raise ValidationError(
                _(
                    "Transition from %(old)s to %(new)s is not allowed for %(model)s."
                ),
                params={
                    "old": current_status,
                    "new": new_status,
                    "model": self._meta.verbose_name,
                },
            )

        with transaction.atomic():
            old_status = current_status
            self.pre_status_change(old_status, new_status, user, note, metadata)
            setattr(self, self.STATUS_FIELD, new_status)
            self.save()
            serialized_metadata = self.serialize_metadata(metadata)
            self.create_status_log(
                user, old_status, new_status, note, serialized_metadata
            )
            self.post_status_change(old_status, new_status, user, note, metadata)
        return True

    def create_status_log(self, user, old_status, new_status, note="", metadata=None):
        raise NotImplementedError("create_status_log must be implemented")

    def serialize_metadata(self, metadata):
        cleaned = {}
        metadata = metadata or {}
        for key, value in metadata.items():
            if isinstance(value, Decimal):
                cleaned[key] = float(value)
            elif isinstance(value, (date, datetime)):
                cleaned[key] = value.isoformat()
            else:
                cleaned[key] = value
        return cleaned
