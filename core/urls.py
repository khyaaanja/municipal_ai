from django.urls import path, re_path
from . import views

app_name = 'core'

urlpatterns = [
    # Google social-auth failure page
    path('auth/error/google-oauth2/', views.google_oauth_error, name='google_oauth_error'),

    # Public homepage
    path('', views.homepage, name='home'),

    # Core public pages referenced by tests
    path('search/', views.global_search, name='search'),
    path('map/', views.map_view, name='map_view'),

    # Orders page (requires login)
    path('orders/', views.orders_view, name='orders'),

    # Citizen dashboard (personalised hub for logged-in citizens)
    path('my/', views.citizen_dashboard, name='citizen_dashboard'),

    # Civic transparency dashboard — resolution stats, leaderboard, SLA compliance
    path('transparency/', views.transparency_dashboard, name='transparency_dashboard'),

    # Ward projects — public view for all citizens
    path('ward-projects/', views.ward_projects_public, name='ward_projects_public'),

    # Toggle follow/unfollow on a ward project (POST only)
    path('ward-projects/<int:pk>/follow/', views.toggle_project_follow, name='project_follow'),

    # Public announcements — city-wide and per-ward
    path('announcements/', views.announcements_public, name='announcements_public'),

    # Post a comment on an announcement (POST only)
    path('announcements/<int:pk>/comment/', views.announcement_comment, name='announcement_comment'),

    # Per-ward citizen hub — complaint stats, projects, budget, announcements
    path('ward/<int:ward_number>/', views.ward_pulse, name='ward_pulse'),

    # Public chairperson profile for a ward
    path('ward/<int:ward_number>/chairperson/', views.ward_chairperson_profile, name='ward_chairperson_profile'),

    # SEO / PWA files
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('manifest.json', views.web_manifest, name='web_manifest'),
    path('sw.js', views.service_worker, name='service_worker'),
    path('offline/', views.offline, name='offline'),
]

# Favicon — redirect to static file so browsers don't 404
# Note: main favicon redirect is in municipal_ai/urls.py

# API endpoints
urlpatterns += [
    # Search autocomplete suggestions (used by nav bar)
    re_path(r'^api/search/suggest/$', views.search_suggest_api, name='api_search_suggest'),

    # Map pins JSON endpoint (attractions + businesses)
    path('api/map/pins/', views.map_pins_api, name='api_map_pins'),
]



