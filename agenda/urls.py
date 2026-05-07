from django.urls import path

from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("painel/", views.portal_view, name="portal"),
    path("agenda/", views.week_view, name="agenda-week"),
    path("agenda/dia/<int:year>/<int:month>/<int:day>/", views.day_view, name="agenda-day"),
    path("agenda/slots/", views.available_slots_view, name="agenda-slots"),
    path("slots/", views.public_available_slots_view, name="public-slots"),
    path("agenda/cancelamentos/", views.staff_cancel_list_view, name="staff-cancel"),
    path(
        "agenda/cancelamentos/<int:pk>/",
        views.staff_cancel_action_view,
        name="staff-cancel-action",
    ),
    path("agendar/", views.booking_view, name="agenda-book"),
    path("meus-agendamentos/", views.client_appointments_view, name="client-appointments"),
    path(
        "meus-agendamentos/cancelar/<int:pk>/",
        views.cancel_appointment_view,
        name="client-cancel",
    ),
]
