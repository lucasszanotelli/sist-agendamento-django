from django.contrib import admin
from django.utils import timezone

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
	list_display = (
		"start_time",
		"end_time_display",
		"collaborator",
		"client_display",
		"client_phone",
		"status",
	)
	list_filter = ("status", "collaborator")
	search_fields = (
		"client__username",
		"client__first_name",
		"client__last_name",
		"client_name",
		"client_phone",
		"collaborator__username",
		"collaborator__first_name",
		"collaborator__last_name",
	)

	@admin.display(description="cliente")
	def client_display(self, obj):
		return obj.client_display

	@admin.display(description="end")
	def end_time_display(self, obj):
		if not obj.end_time:
			return "-"
		return timezone.localtime(obj.end_time).strftime("%H:%M")
