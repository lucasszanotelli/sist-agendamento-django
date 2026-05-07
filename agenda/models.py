from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def _parse_time(value, default):
	if isinstance(value, time):
		return value
	if isinstance(value, str):
		try:
			return datetime.strptime(value, "%H:%M").time()
		except ValueError:
			return default
	return default


class Appointment(models.Model):
	STATUS_SCHEDULED = "scheduled"
	STATUS_CANCELLED = "cancelled"
	STATUS_CHOICES = [
		(STATUS_SCHEDULED, "Agendado"),
		(STATUS_CANCELLED, "Cancelado"),
	]

	client = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="client_appointments",
		null=True,
		blank=True,
	)
	client_name = models.CharField(max_length=120, blank=True)
	client_phone = models.CharField(max_length=20, blank=True)
	collaborator = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="collaborator_appointments",
	)
	start_time = models.DateTimeField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
	notes = models.TextField(blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["start_time"]
		constraints = [
			models.UniqueConstraint(
				fields=["collaborator", "start_time"],
				name="uniq_collab_slot",
			),
		]

	def clean(self):
		super().clean()
		if not self.start_time:
			return

		if not self.client_id and not self.client_name:
			raise ValidationError({"client_name": "Informe o nome do cliente."})
		if not self.client_id and not self.client_phone:
			raise ValidationError({"client_phone": "Informe o telefone do cliente."})

		slot_minutes = getattr(settings, "SALON_SLOT_MINUTES", 30)
		lunch_start = _parse_time(getattr(settings, "SALON_LUNCH_START", "12:00"), time(12, 0))
		lunch_end = _parse_time(getattr(settings, "SALON_LUNCH_END", "13:00"), time(13, 0))

		start_local = timezone.localtime(self.start_time)
		if (
			start_local.minute % slot_minutes != 0
			or start_local.second != 0
			or start_local.microsecond != 0
		):
			raise ValidationError(
				{"start_time": f"Horario precisa respeitar blocos de {slot_minutes} minutos."}
			)

		if lunch_start <= start_local.time() < lunch_end:
			raise ValidationError({"start_time": "Horario indisponivel (almoco)."})

	@property
	def end_time(self):
		slot_minutes = getattr(settings, "SALON_SLOT_MINUTES", 30)
		if not self.start_time:
			return None
		return self.start_time + timedelta(minutes=slot_minutes)

	@property
	def client_display(self):
		if self.client_id:
			name = self.client.get_full_name()
			return name if name else self.client.username
		if self.client_name:
			return self.client_name
		return "Cliente"

	def can_cancel(self, now=None):
		min_hours = getattr(settings, "SALON_CANCEL_MIN_HOURS", 24)
		if not self.start_time:
			return False
		now = now or timezone.now()
		return now <= self.start_time - timedelta(hours=min_hours)

	def __str__(self):
		if not self.start_time:
			return f"{self.collaborator} - sem horario"
		start_local = timezone.localtime(self.start_time)
		return f"{self.collaborator} - {start_local:%d/%m %H:%M}"
