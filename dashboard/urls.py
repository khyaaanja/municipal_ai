from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('',                        views.dashboard_home,          name='home'),
    path('complaints/',             views.complaint_list_staff,    name='complaints'),
    path('complaints/<str:complaint_id>/', views.complaint_detail_staff, name='complaint_detail'),
    path('export/',                 views.export_complaints,        name='export'),
]
