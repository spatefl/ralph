from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from ralph.accounts.models import Team
from ralph.lib.lifecycle.forms import StatusTransitionForm

User = get_user_model()


class DroneMaintenanceStatusForm(StatusTransitionForm):
    reference = forms.CharField(
        label=_("Maintenance reference"),
        required=False,
        max_length=128,
    )
    next_maintenance_date = forms.DateField(
        label=_("Next maintenance date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    next_maintenance_flight_hours = forms.DecimalField(
        label=_("Next maintenance flight hours"),
        required=False,
        min_value=Decimal("0"),
        max_digits=7,
        decimal_places=1,
    )
    firmware_version = forms.CharField(
        label=_("Firmware version"),
        required=False,
        max_length=64,
    )
    last_firmware_update = forms.DateField(
        label=_("Last firmware update"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class DroneCertificationForm(StatusTransitionForm):
    certification_reference = forms.CharField(
        label=_("Certification reference"),
        required=False,
        max_length=128,
    )


class DroneRetirementForm(StatusTransitionForm):
    retirement_reference = forms.CharField(
        label=_("Retirement reference"),
        required=False,
        max_length=128,
    )
    retired_at = forms.DateField(
        label=_("Retired on"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class DroneAssignmentForm(forms.Form):
    assignee = forms.ModelChoiceField(
        label=_("Assign to operator"),
        queryset=User.objects.none(),
        required=False,
    )
    team = forms.ModelChoiceField(
        label=_("Assign to team"),
        queryset=Team.objects.none(),
        required=False,
    )
    location = forms.CharField(
        label=_("Deployment location"),
        required=False,
        max_length=128,
    )
    mission = forms.CharField(
        label=_("Mission"),
        required=False,
        max_length=128,
    )
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = User.objects.all()
        self.fields["team"].queryset = Team.objects.all()

    def clean(self):
        cleaned = super().clean()
        if not any(
            cleaned.get(field)
            for field in ("assignee", "team", "location", "mission")
        ):
            raise forms.ValidationError(
                _("Provide at least a user, team, location or mission to assign.")
            )
        return cleaned


class DroneUnassignmentForm(forms.Form):
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
