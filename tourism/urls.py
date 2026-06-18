from django.urls import path
from . import views

app_name = "tourism"
urlpatterns = [
    path('', views.attractions_list, name='attractions'),
    path('<slug:slug>/', views.attraction_detail, name='attraction_detail'),
]
