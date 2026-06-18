from django.urls import path
from . import views

app_name = "adminpanel"

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # Attractions
    path('cms/attractions/',                   views.cms_attractions,        name='cms_attractions'),
    path('cms/attractions/add/',               views.cms_attraction_form,    name='cms_attraction_add'),
    path('cms/attractions/<int:pk>/edit/',     views.cms_attraction_form,    name='cms_attraction_edit'),
    path('cms/attractions/<int:pk>/delete/',   views.cms_attraction_delete,  name='cms_attraction_delete'),

    # Events
    path('cms/events/',                        views.cms_events,             name='cms_events'),
    path('cms/events/add/',                    views.cms_event_form,         name='cms_event_add'),
    path('cms/events/<int:pk>/edit/',          views.cms_event_form,         name='cms_event_edit'),
    path('cms/events/<int:pk>/delete/',        views.cms_event_delete,       name='cms_event_delete'),

    # Businesses
    path('cms/businesses/',                    views.cms_businesses,         name='cms_businesses'),
    path('cms/businesses/add/',                views.cms_business_form,      name='cms_business_add'),
    path('cms/businesses/<int:pk>/edit/',      views.cms_business_form,      name='cms_business_edit'),
    path('cms/businesses/<int:pk>/delete/',    views.cms_business_delete,    name='cms_business_delete'),

    # News
    path('cms/news/',                          views.cms_news,               name='cms_news'),
    path('cms/news/add/',                      views.cms_news_form,          name='cms_news_add'),
    path('cms/news/<int:pk>/edit/',            views.cms_news_form,          name='cms_news_edit'),
    path('cms/news/<int:pk>/delete/',          views.cms_news_delete,        name='cms_news_delete'),

    # Knowledge Base
    path('cms/knowledge/',                       views.cms_knowledge,               name='cms_knowledge'),
    path('cms/knowledge/add/',                   views.cms_knowledge_form,          name='cms_knowledge_add'),
    path('cms/knowledge/<int:pk>/edit/',         views.cms_knowledge_form,          name='cms_knowledge_edit'),
    path('cms/knowledge/<int:pk>/delete/',       views.cms_knowledge_delete,        name='cms_knowledge_delete'),

    # Marketplace — Products
    path('cms/products/',                        views.cms_products,                name='cms_products'),
    path('cms/products/add/',                    views.cms_product_form,            name='cms_product_add'),
    path('cms/products/<int:pk>/edit/',          views.cms_product_form,            name='cms_product_edit'),
    path('cms/products/<int:pk>/delete/',        views.cms_product_delete,          name='cms_product_delete'),

    # Marketplace — Product Categories
    path('cms/product-categories/',             views.cms_product_categories,      name='cms_product_categories'),
    path('cms/product-categories/add/',         views.cms_product_category_form,   name='cms_product_category_add'),
    path('cms/product-categories/<int:pk>/edit/',   views.cms_product_category_form, name='cms_product_category_edit'),
    path('cms/product-categories/<int:pk>/delete/', views.cms_product_category_delete, name='cms_product_category_delete'),

    # Marketplace — Vendors
    path('cms/vendors/',                         views.cms_vendors,                 name='cms_vendors'),
    path('cms/vendors/<int:pk>/toggle/',         views.cms_vendor_toggle,           name='cms_vendor_toggle'),

    # Marketplace — Orders
    path('cms/orders/',                          views.cms_orders,                  name='cms_orders'),
    path('cms/orders/<int:pk>/status/',          views.cms_order_status,            name='cms_order_status'),

    # Map CMS
    path('cms/map/',                             views.cms_map,                     name='cms_map'),
    path('cms/map/update-location/',             views.cms_map_update_location,     name='cms_map_update_location'),
    path('cms/map/clear-location/',              views.cms_map_clear_location,      name='cms_map_clear_location'),
]
