from django import forms
from django.utils.translation import gettext_lazy as _


class StatusTransitionForm(forms.Form):
    """
    Base form for lifecycle actions – stores optional note.
    """
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def cleaned_note_and_metadata(self):
        data = self.cleaned_data.copy()
        note = data.pop("note", "")
        return note, data
