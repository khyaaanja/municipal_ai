from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from core.sitemaps import StaticViewSitemap
from django.views.generic.base import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage


handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'

sitemaps = {'static': StaticViewSitemap}

urlpatterns = [
    # Favicon — redirect so browsers don't 404
    path('favicon.ico', RedirectView.as_view(url=staticfiles_storage.url('icons/icon-192.png'), permanent=True)),

    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('django-admin/', admin.site.urls),
    # social-auth endpoints (begin/complete/logout) must be reachable.
    path('auth/', include('social_django.urls')),

    path('complaint/',    include('complaints.urls')),
    path('dashboard/',    include('dashboard.urls')),
    path('mayor/',        include('mayor.urls')),
    path('chairperson/',  include('chairperson.urls')),
    path('', include('core.urls')),
    path('chat/', include('chatbot.urls')),
    # Homepage AI widget uses /api/chat/stream/ already, keep for compatibility.

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
    path('civic/', include('civic.urls')),
    path('services/', include('services.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
