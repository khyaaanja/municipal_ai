from django.urls import path
from . import views

app_name = 'mayor'

urlpatterns = [
    path('',                                  views.mayor_dashboard,              name='dashboard'),
    path('report/',                           views.mayor_report,                 name='report'),
    path('briefing/',                         views.mayor_briefing,               name='briefing'),
    path('escalations/',                      views.mayor_escalations,            name='escalations'),
    path('announcements/',                    views.mayor_announcements,          name='announcements'),
    path('announcements/<int:pk>/delete/',    views.mayor_announcement_delete,    name='announcement_delete'),
    path('complaints/',                       views.mayor_complaints,             name='complaints'),
    path('complaints/export/csv/',            views.export_complaints_csv,        name='export_csv'),
    path('complaints/<str:complaint_id>/',    views.mayor_complaint_detail,       name='complaint_detail'),
    path('chairpersons/',                     views.mayor_chairpersons,           name='chairpersons'),
]
