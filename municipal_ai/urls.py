from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

handler404 = 'core.views.handler404'

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('auth/',         include('social_django.urls', namespace='social')),
    path('complaint/',    include('complaints.urls')),
    path('dashboard/',    include('dashboard.urls')),
    path('', include('core.urls')),
    path('chat/', include('chatbot.urls')),
    path('attractions/', include('tourism.urls')),
    path('events/', include('events.urls')),
    path('businesses/', include('businesses.urls')),
    path('marketplace/', include('marketplace.urls')),
    path('news/', include('news.urls')),
    path('', include('accounts.urls')),
    path('vendor/', include('vendor.urls')),
    path('admin/', include('adminpanel.urls')),
    path('api/', include('core.api_urls')),
    path('favorites/', include('favorites.urls')),
    path('itineraries/', include('itinerary.urls')),
    path('reviews/', include('reviews.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
