from django.urls import path
from . import views

app_name = 'marketplace'

urlpatterns = [
    path('', views.marketplace_list, name='list'),
    path('<int:pk>/', views.product_detail, name='detail'),
    path('cart/', views.cart_view, name='cart'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('api/cart/add/', views.add_to_cart, name='cart_add'),
    path('api/cart/update/', views.update_cart, name='cart_update'),
    path('api/cart/remove/', views.remove_from_cart, name='cart_remove'),
    path('khalti/initiate/<int:order_id>/', views.khalti_initiate, name='khalti_initiate'),
    path('khalti/verify/', views.khalti_verify, name='khalti_verify'),
]
