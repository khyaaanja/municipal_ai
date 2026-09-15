from django.urls import path
from . import views

app_name = 'civic'

urlpatterns = [
    # Citizen — Proposals
    path('proposals/',                         views.proposal_list,      name='proposal_list'),
    path('proposals/submit/',                  views.proposal_submit,    name='proposal_submit'),
    path('proposals/<int:pk>/',                views.proposal_detail,    name='proposal_detail'),
    path('proposals/<int:pk>/support/',        views.proposal_support,   name='proposal_support'),

    # Citizen — Meetings
    path('meetings/',                          views.meeting_list,       name='meeting_list'),
    path('meetings/<int:pk>/',                 views.meeting_detail,     name='meeting_detail'),
    path('meetings/<int:pk>/rsvp/',            views.meeting_rsvp,       name='meeting_rsvp'),
    path('meetings/<int:pk>/question/',        views.meeting_question,   name='meeting_question'),

    # Citizen — Polls
    path('polls/',                             views.poll_list,          name='poll_list'),
    path('polls/<int:pk>/',                    views.poll_detail,        name='poll_detail'),
    path('polls/<int:pk>/vote/',               views.poll_vote,          name='poll_vote'),

    # Citizen — Petitions
    path('petitions/',                         views.petition_list,      name='petition_list'),
    path('petitions/start/',                   views.petition_submit,    name='petition_submit'),
    path('petitions/<int:pk>/',                views.petition_detail,    name='petition_detail'),
    path('petitions/<int:pk>/sign/',           views.petition_sign,      name='petition_sign'),

    # Chairperson management
    path('manage/proposals/',                  views.cp_proposal_list,   name='cp_proposal_list'),
    path('manage/proposals/<int:pk>/',         views.cp_proposal_detail, name='cp_proposal_detail'),
    path('manage/meetings/',                   views.cp_meeting_list,    name='cp_meeting_list'),
    path('manage/meetings/create/',            views.cp_meeting_create,  name='cp_meeting_create'),
    path('manage/meetings/<int:pk>/',          views.cp_meeting_detail,  name='cp_meeting_detail'),

    # Mayor management
    path('mayor/polls/',                       views.mayor_poll_list,    name='mayor_poll_list'),
    path('mayor/polls/create/',                views.mayor_poll_create,  name='mayor_poll_create'),
    path('mayor/polls/<int:pk>/close/',        views.mayor_poll_close,   name='mayor_poll_close'),
]
