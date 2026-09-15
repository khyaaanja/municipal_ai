from django.urls import path
from . import views

app_name = 'chairperson'

urlpatterns = [
    path('',                                        views.chairperson_dashboard,            name='dashboard'),
    path('report/',                                 views.chairperson_report,               name='report'),
    path('complaints/',                             views.chairperson_complaints,           name='complaints'),
    path('complaints/export/csv/',                  views.export_complaints_csv,            name='export_csv'),
    path('complaints/<str:complaint_id>/',          views.chairperson_complaint_detail,     name='complaint_detail'),
    path('announcements/',                          views.chairperson_announcements,        name='announcements'),
    path('announcements/<int:pk>/delete/',          views.chairperson_announcement_delete,  name='announcement_delete'),
    path('projects/',                               views.chairperson_projects,             name='projects'),
    path('budget/',                                 views.chairperson_budget,               name='budget'),
]
