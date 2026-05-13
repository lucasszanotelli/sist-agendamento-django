from datetime import date, datetime, timedelta, time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
	BookingCreateForm,
	BookingSearchForm,
	PublicBookingForm,
	StaffBookingForm,
	StaffCancelFilterForm,
)
from .models import Appointment


def _parse_time(value, default):
	if isinstance(value, time):
		return value
	if isinstance(value, str):
		try:
			return datetime.strptime(value, "%H:%M").time()
		except ValueError:
			return default
	return default


def _parse_date_param(value):
	if not value:
		return None
	try:
		return datetime.strptime(value, "%Y-%m-%d").date()
	except ValueError:
		return None


def _get_salon_rules():
	slot_minutes = getattr(settings, "SALON_SLOT_MINUTES", 30)
	open_time = _parse_time(getattr(settings, "SALON_OPEN_TIME", "08:00"), time(8, 0))
	close_time = _parse_time(getattr(settings, "SALON_CLOSE_TIME", "18:00"), time(18, 0))
	lunch_start = _parse_time(getattr(settings, "SALON_LUNCH_START", "12:00"), time(12, 0))
	lunch_end = _parse_time(getattr(settings, "SALON_LUNCH_END", "13:00"), time(13, 0))
	return slot_minutes, open_time, close_time, lunch_start, lunch_end


def _slot_choices(slots):
	return [(slot.strftime("%H:%M"), slot.strftime("%H:%M")) for slot in slots]


def _available_slots(target_date, collaborator_id):
	slot_minutes, open_time, close_time, lunch_start, lunch_end = _get_salon_rules()
	start_dt = datetime.combine(target_date, open_time)
	end_dt = datetime.combine(target_date, close_time)
	last_start = end_dt - timedelta(minutes=slot_minutes)

	slots = []
	current = start_dt
	while current <= last_start:
		current_time = current.time()
		if not (lunch_start <= current_time < lunch_end):
			slots.append(current_time)
		current += timedelta(minutes=slot_minutes)

	booked = Appointment.objects.filter(
		start_time__date=target_date,
		collaborator_id=collaborator_id,
		status=Appointment.STATUS_SCHEDULED,
	)
	booked_times = {timezone.localtime(item.start_time).time() for item in booked}
	slots = [slot for slot in slots if slot not in booked_times]

	now_local = timezone.localtime()
	if target_date <= now_local.date():
		tz = timezone.get_current_timezone()
		slots = [
			slot
			for slot in slots
			if timezone.make_aware(datetime.combine(target_date, slot), tz) > now_local
		]

	return slots


def _week_bounds(target_date):
	week_start = target_date - timedelta(days=target_date.weekday())
	week_end = week_start + timedelta(days=6)
	return week_start, week_end


def _is_collaborator(user):
	return user.is_authenticated and user.is_staff


def home_view(request):
	base_date = _parse_date_param(request.GET.get("date")) or timezone.localdate()
	month_start = base_date.replace(day=1)
	if month_start.month == 12:
		next_month = date(month_start.year + 1, 1, 1)
	else:
		next_month = date(month_start.year, month_start.month + 1, 1)
	prev_month = (month_start - timedelta(days=1)).replace(day=1)
	month_end = next_month - timedelta(days=1)
	week_start = month_start - timedelta(days=month_start.weekday())
	week_end = month_end - timedelta(days=month_end.weekday())

	User = get_user_model()
	collaborators = User.objects.filter(is_staff=True).order_by(
		"first_name", "last_name", "username"
	)

	weeks = []
	current = week_start
	while current <= week_end:
		week_days = []
		for offset in range(1, 6):
			day = current + timedelta(days=offset)
			if day.month != month_start.month:
				week_days.append(None)
				continue
			slot_count = 0
			for collaborator in collaborators:
				slot_count += len(_available_slots(day, collaborator.id))
			week_days.append({"date": day, "slot_count": slot_count})
		weeks.append(week_days)
		current += timedelta(days=7)

	booking_status = request.GET.get("booking")
	public_form = PublicBookingForm(collaborators_qs=collaborators)

	if request.method == "POST":
		selected_date = _parse_date_param(request.POST.get("date"))
		selected_collaborator = request.POST.get("collaborator")
		slot_choices = []
		if selected_date and selected_collaborator:
			available_slots = _available_slots(selected_date, selected_collaborator)
			slot_choices = _slot_choices(available_slots)

		public_form = PublicBookingForm(
			request.POST,
			collaborators_qs=collaborators,
			slot_choices=slot_choices,
		)

		if public_form.is_valid():
			selected_date = public_form.cleaned_data["date"]
			selected_collaborator = public_form.cleaned_data["collaborator"]
			slot_time = public_form.cleaned_data["time"]
			start_naive = datetime.combine(selected_date, slot_time)
			start_time = timezone.make_aware(start_naive, timezone.get_current_timezone())

			appointment = Appointment(
				client=None,
				client_name=public_form.cleaned_data["client_name"],
				client_phone=public_form.cleaned_data["client_phone"],
				collaborator=selected_collaborator,
				start_time=start_time,
				notes=public_form.cleaned_data["notes"],
			)

			try:
				appointment.full_clean()
				appointment.save()
			except ValidationError as exc:
				if hasattr(exc, "message_dict"):
					for field, messages in exc.message_dict.items():
						for message in messages:
							public_form.add_error(field, message)
				else:
					for message in exc.messages:
						public_form.add_error(None, message)
			except IntegrityError:
				public_form.add_error("time", "Horario indisponivel. Tente outro.")
			else:
				query = {"booking": "success", "date": selected_date.isoformat()}
				return redirect(f"{reverse('home')}?{urlencode(query)}")

	context = {
		"month_start": month_start,
		"month_end": month_end,
		"weeks": weeks,
		"prev_month": prev_month,
		"next_month": next_month,
		"today": timezone.localdate(),
		"booking_status": booking_status,
		"public_form": public_form,
	}
	return render(request, "agenda/home.html", context)


@login_required
def portal_view(request):
	if request.user.is_staff:
		return redirect("agenda-week")
	return redirect("agenda-book")


@login_required
@user_passes_test(_is_collaborator)
def week_view(request):
	base_date = _parse_date_param(request.GET.get("date")) or timezone.localdate()
	week_start, week_end = _week_bounds(base_date)
	days = [week_start + timedelta(days=i) for i in range(7)]

	User = get_user_model()
	all_collaborators = User.objects.filter(is_staff=True).order_by(
		"first_name", "last_name", "username"
	)
	selected_collaborator_id = request.GET.get("collaborator") or ""
	selected_collaborator = None
	collaborators = all_collaborators
	if selected_collaborator_id:
		try:
			selected_id = int(selected_collaborator_id)
		except ValueError:
			selected_collaborator_id = ""
		else:
			selected_collaborator = all_collaborators.filter(id=selected_id).first()
			if selected_collaborator:
				collaborators = all_collaborators.filter(id=selected_id)
			else:
				selected_collaborator_id = ""

	appointments = (
		Appointment.objects.filter(
			start_time__date__gte=week_start,
			start_time__date__lte=week_end,
			status=Appointment.STATUS_SCHEDULED,
		)
		.select_related("client", "collaborator")
		.order_by("start_time")
	)
	if selected_collaborator:
		appointments = appointments.filter(collaborator=selected_collaborator)

	schedule_map = {}
	for appointment in appointments:
		day = timezone.localtime(appointment.start_time).date()
		key = (appointment.collaborator_id, day)
		schedule_map.setdefault(key, []).append(appointment)

	rows = []
	for collaborator in collaborators:
		daily = []
		for day in days:
			daily.append(
				{
					"date": day,
					"appointments": schedule_map.get((collaborator.id, day), []),
				}
			)
		rows.append({"collaborator": collaborator, "days": daily})

	booking_status = request.GET.get("booking")
	open_booking_modal = request.GET.get("open") == "1"
	staff_form = StaffBookingForm(collaborators_qs=all_collaborators)

	if request.method == "POST":
		open_booking_modal = True
		selected_date = _parse_date_param(request.POST.get("date"))
		selected_collaborator = request.POST.get("collaborator")
		slot_choices = []
		if selected_date and selected_collaborator:
			available_slots = _available_slots(selected_date, selected_collaborator)
			slot_choices = _slot_choices(available_slots)

		staff_form = StaffBookingForm(
			request.POST,
			collaborators_qs=all_collaborators,
			slot_choices=slot_choices,
		)

		if staff_form.is_valid():
			selected_date = staff_form.cleaned_data["date"]
			selected_collaborator = staff_form.cleaned_data["collaborator"]
			slot_time = staff_form.cleaned_data["time"]
			start_naive = datetime.combine(selected_date, slot_time)
			start_time = timezone.make_aware(start_naive, timezone.get_current_timezone())

			appointment = Appointment(
				client=None,
				client_name=staff_form.cleaned_data["client_name"],
				client_phone=staff_form.cleaned_data["client_phone"],
				collaborator=selected_collaborator,
				start_time=start_time,
				notes=staff_form.cleaned_data["notes"],
			)

			try:
				appointment.full_clean()
				appointment.save()
			except ValidationError as exc:
				if hasattr(exc, "message_dict"):
					for field, messages in exc.message_dict.items():
						for message in messages:
							staff_form.add_error(field, message)
				else:
					for message in exc.messages:
						staff_form.add_error(None, message)
			except IntegrityError:
				staff_form.add_error("time", "Horario indisponivel. Tente outro.")
			else:
				query = {"booking": "success", "date": base_date.isoformat()}
				return redirect(f"{reverse('agenda-week')}?{urlencode(query)}")

	context = {
		"week_start": week_start,
		"week_end": week_end,
		"days": days,
		"rows": rows,
		"prev_week": week_start - timedelta(days=7),
		"next_week": week_start + timedelta(days=7),
		"staff_form": staff_form,
		"open_booking_modal": open_booking_modal,
		"booking_status": booking_status,
		"all_collaborators": all_collaborators,
		"selected_collaborator_id": selected_collaborator_id,
	}
	return render(request, "agenda/week.html", context)


@login_required
@user_passes_test(_is_collaborator)
def day_view(request, year, month, day):
	target_date = date(year, month, day)
	appointments = (
		Appointment.objects.filter(
			start_time__date=target_date,
			status=Appointment.STATUS_SCHEDULED,
		)
		.select_related("client", "collaborator")
		.order_by("start_time")
	)
	context = {
		"target_date": target_date,
		"appointments": appointments,
	}
	return render(request, "agenda/day.html", context)


@login_required
@user_passes_test(_is_collaborator)
def staff_cancel_list_view(request):
	User = get_user_model()
	collaborators = User.objects.filter(is_staff=True).order_by(
		"first_name", "last_name", "username"
	)

	form = StaffCancelFilterForm(request.GET or None, collaborators_qs=collaborators)
	appointments = (
		Appointment.objects.filter(status=Appointment.STATUS_SCHEDULED)
		.select_related("collaborator", "client")
		.order_by("start_time")
	)

	if form.is_valid():
		selected_date = form.cleaned_data.get("date")
		selected_collaborator = form.cleaned_data.get("collaborator")
		if selected_date:
			appointments = appointments.filter(start_time__date=selected_date)
		elif not selected_collaborator:
			appointments = appointments.filter(start_time__gte=timezone.now())
		if selected_collaborator:
			appointments = appointments.filter(collaborator=selected_collaborator)
	else:
		appointments = appointments.filter(start_time__gte=timezone.now())

	status = request.GET.get("status")
	status_message = None
	if status == "cancelled":
		status_message = "Agendamento cancelado com sucesso."
	elif status == "not-allowed":
		status_message = "Nao foi possivel cancelar este agendamento."

	context = {
		"appointments": appointments,
		"filter_form": form,
		"status_message": status_message,
	}
	return render(request, "agenda/staff_cancel.html", context)


@login_required
@user_passes_test(_is_collaborator)
def staff_cancel_action_view(request, pk):
	if request.method != "POST":
		return redirect("staff-cancel")

	appointment = get_object_or_404(Appointment, pk=pk)
	if appointment.status != Appointment.STATUS_SCHEDULED:
		return redirect(f"{reverse('staff-cancel')}?status=not-allowed")

	appointment.status = Appointment.STATUS_CANCELLED
	appointment.save(update_fields=["status", "updated_at"])
	return redirect(f"{reverse('staff-cancel')}?status=cancelled")


@login_required
@user_passes_test(_is_collaborator)
def available_slots_view(request):
	selected_date = _parse_date_param(request.GET.get("date"))
	collaborator_id = request.GET.get("collaborator")
	if not selected_date or not collaborator_id:
		return JsonResponse({"slots": []})

	slots = _available_slots(selected_date, collaborator_id)
	return JsonResponse({"slots": [slot.strftime("%H:%M") for slot in slots]})


def public_available_slots_view(request):
	selected_date = _parse_date_param(request.GET.get("date"))
	collaborator_id = request.GET.get("collaborator")
	if not selected_date or not collaborator_id:
		return JsonResponse({"slots": []})

	slots = _available_slots(selected_date, collaborator_id)
	return JsonResponse({"slots": [slot.strftime("%H:%M") for slot in slots]})


@login_required
def booking_view(request):
	if request.user.is_staff:
		return redirect("agenda-week")

	User = get_user_model()
	collaborators = User.objects.filter(is_staff=True).order_by(
		"first_name", "last_name", "username"
	)
	has_collaborators = collaborators.exists()

	created = request.GET.get("created") == "1"
	search_form = BookingSearchForm(request.GET or None, collaborators_qs=collaborators)
	available_slots = []
	booking_form = None
	selected_date = None
	selected_collaborator = None

	if request.method == "POST":
		created = False
		search_form = BookingSearchForm(request.POST, collaborators_qs=collaborators)
		if search_form.is_valid():
			selected_date = search_form.cleaned_data["date"]
			selected_collaborator = search_form.cleaned_data["collaborator"]
			available_slots = _available_slots(selected_date, selected_collaborator.id)

		booking_form = BookingCreateForm(
			request.POST,
			collaborators_qs=collaborators,
			slot_choices=_slot_choices(available_slots),
			hide_search=True,
		)

		if booking_form.is_valid():
			selected_date = booking_form.cleaned_data["date"]
			selected_collaborator = booking_form.cleaned_data["collaborator"]
			slot_time = booking_form.cleaned_data["time"]
			start_naive = datetime.combine(selected_date, slot_time)
			start_time = timezone.make_aware(start_naive, timezone.get_current_timezone())

			appointment = Appointment(
				client=request.user,
				collaborator=selected_collaborator,
				start_time=start_time,
				notes=booking_form.cleaned_data["notes"],
			)

			try:
				appointment.full_clean()
				appointment.save()
			except ValidationError as exc:
				if hasattr(exc, "message_dict"):
					for messages in exc.message_dict.values():
						for message in messages:
							booking_form.add_error(None, message)
				else:
					for message in exc.messages:
						booking_form.add_error(None, message)
			except IntegrityError:
				booking_form.add_error("time", "Horario indisponivel. Tente outro.")
			else:
				query = urlencode(
					{
						"date": selected_date.isoformat(),
						"collaborator": selected_collaborator.id,
						"created": "1",
					}
				)
				return redirect(f"{reverse('agenda-book')}?{query}")

	if search_form.is_valid() and booking_form is None:
		selected_date = search_form.cleaned_data["date"]
		selected_collaborator = search_form.cleaned_data["collaborator"]
		available_slots = _available_slots(selected_date, selected_collaborator.id)
		booking_form = BookingCreateForm(
			initial={"date": selected_date, "collaborator": selected_collaborator},
			collaborators_qs=collaborators,
			slot_choices=_slot_choices(available_slots),
			hide_search=True,
		)

	context = {
		"search_form": search_form,
		"booking_form": booking_form,
		"available_slots": available_slots,
		"created": created,
		"has_collaborators": has_collaborators,
		"selected_date": selected_date,
		"selected_collaborator": selected_collaborator,
	}
	return render(request, "agenda/booking.html", context)


@login_required
def client_appointments_view(request):
	if request.user.is_staff:
		return redirect("agenda-week")

	now = timezone.now()
	upcoming = (
		Appointment.objects.filter(
			client=request.user,
			status=Appointment.STATUS_SCHEDULED,
			start_time__gte=now,
		)
		.select_related("collaborator")
		.order_by("start_time")
	)

	history = (
		Appointment.objects.filter(client=request.user)
		.filter(Q(status=Appointment.STATUS_CANCELLED) | Q(start_time__lt=now))
		.select_related("collaborator")
		.order_by("-start_time")
	)

	status = request.GET.get("status")
	status_message = None
	if status == "cancelled":
		status_message = "Agendamento cancelado com sucesso."
	elif status == "too-late":
		status_message = "Cancelamento permitido somente com 24h de antecedencia."
	elif status == "not-allowed":
		status_message = "Nao foi possivel cancelar este agendamento."

	context = {
		"upcoming": upcoming,
		"history": history,
		"status_message": status_message,
		"now": now,
	}
	return render(request, "agenda/my_appointments.html", context)


@login_required
def cancel_appointment_view(request, pk):
	if request.user.is_staff:
		return redirect("agenda-week")

	if request.method != "POST":
		return redirect("client-appointments")

	appointment = get_object_or_404(Appointment, pk=pk, client=request.user)
	if appointment.status != Appointment.STATUS_SCHEDULED:
		return redirect(f"{reverse('client-appointments')}?status=not-allowed")
	if not appointment.can_cancel():
		return redirect(f"{reverse('client-appointments')}?status=too-late")

	appointment.status = Appointment.STATUS_CANCELLED
	appointment.save(update_fields=["status", "updated_at"])
	return redirect(f"{reverse('client-appointments')}?status=cancelled")
