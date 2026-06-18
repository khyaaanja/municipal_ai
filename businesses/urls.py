from django.urls import path
from . import views

app_name = "businesses"
urlpatterns = [
    path('', views.businesses_list, name='businesses'),
    path('<slug:slug>/', views.business_detail, name='business_detail'),
]
