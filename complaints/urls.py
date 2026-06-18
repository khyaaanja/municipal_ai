from django.urls import path
from . import views

app_name = 'complaints'

urlpatterns = [
    path('',                           views.submit_complaint,  name='complaint_submit'),
    path('success/',                   views.complaint_success, name='complaint_success'),
    path('track/',                     views.track_complaint,   name='complaint_track'),
    path('status/<str:complaint_id>/', views.complaint_status,  name='complaint_status'),
    path('my/',                        views.my_complaints,     name='my_complaints'),
]
