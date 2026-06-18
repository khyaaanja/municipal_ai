from django.urls import path
from chatbot.views import chat_api
urlpatterns = [
    path('chat/', chat_api, name='api_chat'),
]
