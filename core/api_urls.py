from django.urls import path
from chatbot.views import chat_api, chat_stream, chat_async, chat_poll, voice_transcribe
from core.views import scan_api

urlpatterns = [
    path('chat/',                   chat_api,         name='api_chat'),
    path('chat/stream/',            chat_stream,      name='api_chat_stream'),
    path('chat/async/',             chat_async,       name='api_chat_async'),
    path('chat/poll/<str:job_id>/', chat_poll,        name='api_chat_poll'),
    path('scan/',                   scan_api,         name='api_scan'),
    path('voice/',                  voice_transcribe, name='api_voice'),
]
