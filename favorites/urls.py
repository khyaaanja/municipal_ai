from django.urls import path
from . import views

app_name = "favorites"

urlpatterns = [
    path('', views.favorites_list, name='favorites_list'),
    path('toggle/', views.toggle_favorite, name='toggle_favorite'),
]
