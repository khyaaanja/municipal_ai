from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    # Citizen
    path('',                                    views.service_list,          name='service_list'),
    path('apply/<str:service_type>/',           views.service_apply,         name='service_apply'),
    path('my/',                                 views.my_requests,           name='my_requests'),
    path('my/<str:ref>/',                       views.request_detail,        name='request_detail'),
    path('success/<str:ref>/',                  views.request_success,       name='request_success'),
    path('notices/',                            views.notice_list,           name='notice_list'),
    path('notices/<int:pk>/',                   views.notice_detail,         name='notice_detail'),

    # Chairperson
    path('manage/requests/',                    views.cp_request_list,       name='cp_request_list'),
    path('manage/requests/<str:ref>/',          views.cp_request_detail,     name='cp_request_detail'),

    # Mayor / staff
    path('mayor/requests/',                     views.mayor_request_list,    name='mayor_request_list'),
    path('mayor/notices/',                      views.mayor_notice_list,     name='mayor_notice_list'),
    path('mayor/notices/create/',               views.mayor_notice_create,   name='mayor_notice_create'),
    path('mayor/notices/<int:pk>/edit/',        views.mayor_notice_edit,     name='mayor_notice_edit'),
    path('mayor/notices/<int:pk>/delete/',      views.mayor_notice_delete,   name='mayor_notice_delete'),
]
