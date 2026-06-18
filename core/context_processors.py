from django.conf import settings


def global_context(request):
    cart_count = 0
    if request.user.is_authenticated:
        cart_count = request.session.get('cart_count', None)
        if cart_count is None:
            try:
                from marketplace.models import CartItem
                cart_count = CartItem.objects.filter(
                    cart__user=request.user
                ).values_list('quantity', flat=True)
                cart_count = sum(cart_count)
            except Exception:
                cart_count = 0
            request.session['cart_count'] = cart_count

    return {
        'CITY_NAME': settings.CITY_NAME,
        'CITY_COUNTRY': settings.CITY_COUNTRY,
        'CITY_LAT': settings.CITY_LAT,
        'CITY_LNG': settings.CITY_LNG,
        'cart_count': cart_count,
    }
