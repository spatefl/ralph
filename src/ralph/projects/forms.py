from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class ProjectAssignmentForm(forms.Form):
    entry = forms.IntegerField(widget=forms.HiddenInput())
    assignee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        required=False,
        empty_label=_("Unassigned"),
        label=_("Assign to"),
    )
    handover_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": _("Add handover note (optional)"),
            }
        ),
        label=_("Handover notes"),
    )
