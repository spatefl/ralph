from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from ralph.lib.lifecycle.forms import StatusTransitionForm

User = get_user_model()


class VehicleMaintenanceStatusForm(StatusTransitionForm):
    maintenance_ticket = forms.CharField(
        label=_("Maintenance ticket / reference"),
        required=False,
        max_length=128,
    )
    next_service_date = forms.DateField(
        label=_("Next service date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    next_service_odometer = forms.IntegerField(
        label=_("Next service odometer (km)"),
        required=False,
        min_value=0,
    )


class VehicleRetirementForm(StatusTransitionForm):
    retirement_reference = forms.CharField(
        label=_("Retirement reference"),
        required=False,
        max_length=128,
        help_text=_("Optional disposal or financial ticket reference."),
    )
    decommissioned_at = forms.DateField(
        label=_("Decommissioned on"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class VehicleAssignmentForm(forms.Form):
    assignee = forms.ModelChoiceField(
        label=_("Assign to user"),
        queryset=User.objects.none(),
        required=False,
    )
    location = forms.CharField(
        label=_("Assign location"),
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

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("assignee") and not cleaned.get("location"):
            raise forms.ValidationError(
                _("Provide at least a user or location for assignment.")
            )
        return cleaned


class VehicleUnassignmentForm(forms.Form):
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
