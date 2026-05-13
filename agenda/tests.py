from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from .forms import BookingCreateForm, PublicBookingForm, StaffBookingForm
from .models import Appointment


def _make_start_time(target_date, hour, minute=0):
	tz = timezone.get_current_timezone()
	return timezone.make_aware(datetime.combine(target_date, time(hour, minute)), tz)


@pytest.fixture
def collaborator(db):
	User = get_user_model()
	user = User.objects.create_user(username="collab", password="pass")
	user.is_staff = True
	user.save(update_fields=["is_staff"])
	return user


@pytest.fixture
def client_user(db):
	User = get_user_model()
	return User.objects.create_user(username="cliente", password="pass")


@pytest.mark.django_db
def test_appointment_requires_client_name_phone_when_no_client(collaborator):
	start_time = _make_start_time(timezone.localdate() + timedelta(days=2), 9, 0)
	appointment = Appointment(collaborator=collaborator, start_time=start_time)
	with pytest.raises(ValidationError) as exc:
		appointment.full_clean()
	assert "client_name" in exc.value.message_dict
	assert "client_phone" not in exc.value.message_dict


@pytest.mark.django_db
def test_appointment_requires_phone_when_name_provided(collaborator):
	start_time = _make_start_time(timezone.localdate() + timedelta(days=2), 9, 0)
	appointment = Appointment(
		collaborator=collaborator,
		start_time=start_time,
		client_name="Ana",
	)
	with pytest.raises(ValidationError) as exc:
		appointment.full_clean()
	assert "client_phone" in exc.value.message_dict


@pytest.mark.django_db
def test_appointment_rejects_off_slot_minutes(collaborator):
	start_time = _make_start_time(timezone.localdate() + timedelta(days=2), 9, 10)
	appointment = Appointment(
		collaborator=collaborator,
		start_time=start_time,
		client_name="Ana",
		client_phone="11999999999",
	)
	with pytest.raises(ValidationError) as exc:
		appointment.full_clean()
	assert "start_time" in exc.value.message_dict


@pytest.mark.django_db
def test_appointment_rejects_lunch_time(collaborator):
	start_time = _make_start_time(timezone.localdate() + timedelta(days=2), 12, 0)
	appointment = Appointment(
		collaborator=collaborator,
		start_time=start_time,
		client_name="Ana",
		client_phone="11999999999",
	)
	with pytest.raises(ValidationError) as exc:
		appointment.full_clean()
	assert "start_time" in exc.value.message_dict


@pytest.mark.django_db
def test_appointment_end_time_uses_slot_minutes(collaborator):
	start_time = _make_start_time(timezone.localdate() + timedelta(days=2), 9, 0)
	appointment = Appointment(
		collaborator=collaborator,
		start_time=start_time,
		client_name="Ana",
		client_phone="11999999999",
	)
	assert appointment.end_time == start_time + timedelta(minutes=30)


@pytest.mark.django_db
def test_appointment_client_display_prefers_user_full_name(collaborator, client_user):
	client_user.first_name = "Ana"
	client_user.last_name = "Silva"
	client_user.save(update_fields=["first_name", "last_name"])
	start_time = _make_start_time(timezone.localdate() + timedelta(days=2), 9, 0)
	appointment = Appointment(
		collaborator=collaborator,
		client=client_user,
		start_time=start_time,
	)
	assert appointment.client_display == "Ana Silva"


@pytest.mark.django_db
def test_appointment_can_cancel_respects_min_hours(collaborator):
	now = timezone.now()
	start_time = now + timedelta(hours=30)
	appointment = Appointment(
		collaborator=collaborator,
		start_time=start_time,
		client_name="Ana",
		client_phone="11999999999",
	)
	assert appointment.can_cancel(now=now) is True

	late_time = now + timedelta(hours=6)
	appointment.start_time = late_time
	assert appointment.can_cancel(now=now) is False


@pytest.mark.django_db
def test_portal_view_redirects_by_role(client, collaborator, client_user):
	client.force_login(collaborator)
	response = client.get(reverse("portal"))
	assert response.status_code == 302
	assert response.url == reverse("agenda-week")

	client.force_login(client_user)
	response = client.get(reverse("portal"))
	assert response.status_code == 302
	assert response.url == reverse("agenda-book")


@pytest.mark.django_db
def test_available_slots_view_excludes_booked_slots(client, collaborator):
	client.force_login(collaborator)
	future_date = timezone.localdate() + timedelta(days=3)
	start_time = _make_start_time(future_date, 9, 0)
	Appointment.objects.create(
		collaborator=collaborator,
		start_time=start_time,
		client_name="Ana",
		client_phone="11999999999",
	)
	response = client.get(
		reverse("agenda-slots"),
		{"date": future_date.isoformat(), "collaborator": collaborator.id},
	)
	assert response.status_code == 200
	assert "09:00" not in response.json().get("slots", [])


@pytest.mark.django_db
def test_public_available_slots_view_requires_params(client):
	response = client.get(reverse("public-slots"))
	assert response.status_code == 200
	assert response.json() == {"slots": []}


@pytest.mark.django_db
def test_booking_view_creates_appointment_for_client(client, collaborator, client_user):
	client.force_login(client_user)
	future_date = timezone.localdate() + timedelta(days=4)
	response = client.post(
		reverse("agenda-book"),
		{
			"date": future_date.isoformat(),
			"collaborator": collaborator.id,
			"time": "09:00",
			"notes": "Corte",
		},
	)
	assert response.status_code == 302
	assert Appointment.objects.filter(client=client_user).count() == 1


@pytest.mark.django_db
def test_cancel_appointment_view_too_late(client, collaborator, client_user):
	client.force_login(client_user)
	start_time = timezone.now() + timedelta(hours=6)
	appointment = Appointment.objects.create(
		collaborator=collaborator,
		client=client_user,
		start_time=start_time,
	)
	response = client.post(reverse("client-cancel", args=[appointment.id]))
	appointment.refresh_from_db()
	assert response.status_code == 302
	assert "status=too-late" in response.url
	assert appointment.status == Appointment.STATUS_SCHEDULED


@pytest.mark.django_db
def test_cancel_appointment_view_success(client, collaborator, client_user):
	client.force_login(client_user)
	start_time = timezone.now() + timedelta(hours=30)
	appointment = Appointment.objects.create(
		collaborator=collaborator,
		client=client_user,
		start_time=start_time,
	)
	response = client.post(reverse("client-cancel", args=[appointment.id]))
	appointment.refresh_from_db()
	assert response.status_code == 302
	assert "status=cancelled" in response.url
	assert appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
def test_staff_cancel_action_view_cancels(client, collaborator, client_user):
	client.force_login(collaborator)
	start_time = timezone.now() + timedelta(hours=30)
	appointment = Appointment.objects.create(
		collaborator=collaborator,
		client=client_user,
		start_time=start_time,
	)
	response = client.post(reverse("staff-cancel-action", args=[appointment.id]))
	appointment.refresh_from_db()
	assert response.status_code == 302
	assert "status=cancelled" in response.url
	assert appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
def test_staff_cancel_list_status_message(client, collaborator):
	client.force_login(collaborator)
	response = client.get(reverse("staff-cancel"), {"status": "cancelled"})
	assert response.status_code == 200
	assert response.context["status_message"] == "Agendamento cancelado com sucesso."


@pytest.mark.django_db
def test_staff_booking_form_validates_phone():
	form = StaffBookingForm(
		data={
			"client_name": "Ana",
			"client_phone": "123",
			"date": timezone.localdate().isoformat(),
			"collaborator": "",
			"time": "09:00",
		},
	)
	assert form.is_valid() is False
	assert "client_phone" in form.errors


@pytest.mark.django_db
def test_public_booking_form_validates_phone():
	form = PublicBookingForm(
		data={
			"client_name": "Ana",
			"client_phone": "123",
			"date": timezone.localdate().isoformat(),
			"collaborator": "",
			"time": "09:00",
		},
	)
	assert form.is_valid() is False
	assert "client_phone" in form.errors


@pytest.mark.django_db
def test_booking_create_form_rejects_invalid_time():
	form = BookingCreateForm(
		data={
			"date": timezone.localdate().isoformat(),
			"collaborator": "",
			"time": "invalid",
			"notes": "",
		},
	)
	assert form.is_valid() is False
	assert "time" in form.errors
