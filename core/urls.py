from django.urls import path
from . import views

app_name = "core"
urlpatterns = [
    path('', views.homepage, name='home'),
    path('search/', views.global_search, name='search'),
    path('map/', views.map_view, name='map'),
    path('orders/', views.orders_view, name='orders'),
]
