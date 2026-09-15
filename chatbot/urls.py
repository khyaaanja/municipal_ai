from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    path('',               views.chat_page,           name='chat'),
    path('history/',       views.chat_history,         name='history'),
    path('<int:pk>/',      views.conversation_detail,  name='conversation'),
    path('delete/<int:pk>/', views.delete_conversation, name='delete_conversation'),
    path('feedback/',      views.message_feedback,     name='feedback'),
    path('set-language/',  views.set_language,         name='set_language'),
]
