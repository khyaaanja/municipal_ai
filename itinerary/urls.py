from django.urls import path
from . import views

app_name = 'itinerary'

urlpatterns = [
    path('', views.itinerary_list, name='list'),
    path('generate/', views.generate_itinerary, name='generate'),
    path('<int:pk>/', views.itinerary_detail, name='detail'),
    path('<int:pk>/delete/', views.delete_itinerary, name='delete'),
]
