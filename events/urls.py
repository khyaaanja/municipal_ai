from django.urls import path
from . import views

app_name = "events"
urlpatterns = [
    path('', views.events_list, name='events'),
    path('<slug:slug>/', views.event_detail, name='event_detail'),
    path('<slug:slug>/register/', views.event_register, name='event_register'),
    path('<slug:slug>/unregister/', views.event_unregister, name='event_unregister'),
]
