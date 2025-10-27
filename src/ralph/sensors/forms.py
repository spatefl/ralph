from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from ralph.lib.lifecycle.forms import StatusTransitionForm

User = get_user_model()


class SensorMaintenanceStatusForm(StatusTransitionForm):
    next_calibration_due = forms.DateField(
        label=_("Next calibration due"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    technician = forms.CharField(
        label=_("Technician"),
        required=False,
        max_length=128,
    )


class SensorFaultStatusForm(StatusTransitionForm):
    incident_reference = forms.CharField(
        label=_("Incident reference"),
        required=False,
        max_length=128,
    )


class SensorRetirementForm(StatusTransitionForm):
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


class SensorAssignmentForm(forms.Form):
    assignee = forms.ModelChoiceField(
        label=_("Assign to user"),
        queryset=User.objects.none(),
        required=False,
    )
    location = forms.CharField(
        label=_("Location"),
        required=False,
        max_length=128,
    )
    latitude = forms.DecimalField(
        label=_("Latitude"),
        required=False,
        max_digits=9,
        decimal_places=6,
    )
    longitude = forms.DecimalField(
        label=_("Longitude"),
        required=False,
        max_digits=9,
        decimal_places=6,
    )
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = User.objects.all()

    def clean(self):
        cleaned = super().clean()
        if not any(
            cleaned.get(field)
            for field in ("assignee", "location", "latitude", "longitude")
        ):
            raise forms.ValidationError(
                _("Provide at least a user, location, or coordinates to assign.")
            )
        return cleaned


class SensorUnassignmentForm(forms.Form):
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
