from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model


class BookingSearchForm(forms.Form):
	date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
	collaborator = forms.ModelChoiceField(
		queryset=get_user_model().objects.none(),
		empty_label="Selecione",
	)

	def __init__(self, *args, collaborators_qs=None, **kwargs):
		super().__init__(*args, **kwargs)
		if collaborators_qs is None:
			collaborators_qs = get_user_model().objects.filter(is_staff=True)
		self.fields["collaborator"].queryset = collaborators_qs


class BookingCreateForm(BookingSearchForm):
	time = forms.ChoiceField(choices=[])
	notes = forms.CharField(
		required=False,
		widget=forms.Textarea(attrs={"rows": 3}),
	)

	def __init__(self, *args, slot_choices=None, hide_search=False, collaborators_qs=None, **kwargs):
		super().__init__(*args, collaborators_qs=collaborators_qs, **kwargs)
		self.fields["time"].choices = slot_choices or []
		if hide_search:
			self.fields["date"].widget = forms.HiddenInput()
			self.fields["collaborator"].widget = forms.HiddenInput()

	def clean_time(self):
		value = self.cleaned_data.get("time")
		try:
			return datetime.strptime(value, "%H:%M").time()
		except (TypeError, ValueError):
			raise forms.ValidationError("Horario invalido.")


class StaffBookingForm(forms.Form):
	client_name = forms.CharField(max_length=120, label="Nome do cliente")
	client_phone = forms.CharField(max_length=20, label="Telefone")
	date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
	collaborator = forms.ModelChoiceField(
		queryset=get_user_model().objects.none(),
		empty_label="Selecione",
	)
	time = forms.ChoiceField(choices=[])
	notes = forms.CharField(
		required=False,
		widget=forms.Textarea(attrs={"rows": 3}),
	)

	def __init__(self, *args, collaborators_qs=None, slot_choices=None, **kwargs):
		super().__init__(*args, **kwargs)
		if collaborators_qs is None:
			collaborators_qs = get_user_model().objects.filter(is_staff=True)
		self.fields["collaborator"].queryset = collaborators_qs
		self.fields["time"].choices = slot_choices or []

	def clean_time(self):
		value = self.cleaned_data.get("time")
		try:
			return datetime.strptime(value, "%H:%M").time()
		except (TypeError, ValueError):
			raise forms.ValidationError("Horario invalido.")

	def clean_client_phone(self):
		value = self.cleaned_data.get("client_phone", "")
		digits = "".join(ch for ch in value if ch.isdigit())
		if len(digits) < 8:
			raise forms.ValidationError("Telefone invalido.")
		return digits


class PublicBookingForm(forms.Form):
	client_name = forms.CharField(max_length=120, label="Nome do cliente")
	client_phone = forms.CharField(max_length=20, label="Telefone")
	date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
	collaborator = forms.ModelChoiceField(
		queryset=get_user_model().objects.none(),
		empty_label="Selecione",
	)
	time = forms.ChoiceField(choices=[])
	notes = forms.CharField(
		required=False,
		widget=forms.Textarea(attrs={"rows": 3}),
	)

	def __init__(self, *args, collaborators_qs=None, slot_choices=None, **kwargs):
		super().__init__(*args, **kwargs)
		if collaborators_qs is None:
			collaborators_qs = get_user_model().objects.filter(is_staff=True)
		self.fields["collaborator"].queryset = collaborators_qs
		self.fields["time"].choices = slot_choices or []

	def clean_time(self):
		value = self.cleaned_data.get("time")
		try:
			return datetime.strptime(value, "%H:%M").time()
		except (TypeError, ValueError):
			raise forms.ValidationError("Horario invalido.")

	def clean_client_phone(self):
		value = self.cleaned_data.get("client_phone", "")
		digits = "".join(ch for ch in value if ch.isdigit())
		if len(digits) < 8:
			raise forms.ValidationError("Telefone invalido.")
		return digits


class StaffCancelFilterForm(forms.Form):
	date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
	collaborator = forms.ModelChoiceField(
		required=False,
		queryset=get_user_model().objects.none(),
		empty_label="Todos",
	)

	def __init__(self, *args, collaborators_qs=None, **kwargs):
		super().__init__(*args, **kwargs)
		if collaborators_qs is None:
			collaborators_qs = get_user_model().objects.filter(is_staff=True)
		self.fields["collaborator"].queryset = collaborators_qs
