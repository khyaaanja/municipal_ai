from django.urls import path
from . import views

app_name = 'complaints'

urlpatterns = [
    path('',                                    views.submit_complaint,      name='complaint_submit'),
    path('success/',                            views.complaint_success,     name='complaint_success'),
    path('track/',                              views.track_complaint,       name='complaint_track'),
    path('status/<str:complaint_id>/',          views.complaint_status,      name='complaint_status'),
    path('my/',                                 views.my_complaints,         name='my_complaints'),
    path('vote/<str:complaint_id>/',            views.vote_complaint,        name='vote_complaint'),
    path('follow/<str:complaint_id>/',          views.follow_complaint,      name='follow_complaint'),
    path('rate/<str:complaint_id>/',            views.rate_complaint,        name='rate_complaint'),
    path('update/<str:complaint_id>/',          views.add_complaint_update,  name='add_update'),
    path('print/<str:complaint_id>/',           views.complaint_pdf,         name='complaint_pdf'),
    path('support/<str:complaint_id>/',         views.support_complaint,      name='support_complaint'),
    path('escalate/<str:complaint_id>/',        views.escalate_complaint,     name='escalate_complaint'),
    path('escalation/ack/<int:escalation_id>/', views.acknowledge_escalation, name='acknowledge_escalation'),
    path('ai-assist/',                          views.ai_assist_complaint,    name='ai_assist'),
    path('similar/',                            views.similar_complaints,     name='similar_complaints'),
    path('claim/<uuid:token>/',                 views.claim_complaint,        name='claim_complaint'),
    path('service-rating/<str:complaint_id>/', views.rate_service,           name='rate_service'),
]
