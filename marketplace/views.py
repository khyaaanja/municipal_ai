import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.db import transaction
from django.db.models import F
import json
from .models import Product, Cart, CartItem, Order, OrderItem

logger = logging.getLogger(__name__)

_FEE = lambda: getattr(django_settings, 'DELIVERY_FEE_NPR', 100)


def _send_order_confirmation(order, items):
    if not order.user.email:
        return
    lines = [f"  • {i.product.name if i.product else 'Item'} × {i.quantity}  —  NPR {i.price * i.quantity:,.0f}" for i in items]
    body = (
        f"Hi {order.user.get_full_name() or order.user.email},\n\n"
        f"Your order has been placed! We'll contact you to arrange delivery.\n\n"
        f"Order #{order.pk}\n"
        f"{'—' * 40}\n"
        + "\n".join(lines) +
        f"\n{'—' * 40}\n"
        f"Delivery Fee : NPR {_FEE()}\n"
        f"Total        : NPR {order.total_amount:,.0f}\n"
        f"Payment      : Cash on Delivery\n\n"
        f"Delivery address:\n{order.delivery_address}\n\n"
        f"Questions? Call +977-1-6610000 or reply to this email.\n\n"
        f"Bhaktapur Heritage Store\n"
        f"Bhaktapur Municipality Platform"
    )
    send_mail(
        subject=f'Order #{order.pk} Confirmed — Bhaktapur Marketplace',
        message=body,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        fail_silently=True,
    )


def marketplace_list(request):
    from .models import ProductCategory
    from django.core.cache import cache as _cache
    category  = request.GET.get('category', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    sort      = request.GET.get('sort', 'newest')

    _cache_key = None
    if not request.user.is_authenticated and not min_price and not max_price and sort == 'newest':
        _cache_key = f'marketplace_list:{category or "all"}'
        _cached = _cache.get(_cache_key)
        if _cached:
            return _cached

    products = Product.objects.filter(is_active=True).select_related('category', 'vendor')

    if category:
        products = products.filter(category__slug=category)
    try:
        if min_price:
            products = products.filter(price__gte=float(min_price))
        if max_price:
            products = products.filter(price__lte=float(max_price))
    except (ValueError, TypeError):
        pass
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    else:
        products = products.order_by('-created_at')

    categories = ProductCategory.objects.all()

    response = render(request, 'marketplace/list.html', {
        'products': products,
        'categories': categories,
        'active_category': category,
        'min_price': min_price,
        'max_price': max_price,
    })
    if _cache_key:
        _cache.set(_cache_key, response, 300)  # 5 minutes
    return response


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    from reviews.models import Review
    reviews = Review.objects.filter(
        content_type='product', object_id=pk, is_approved=True
    )
    related = Product.objects.filter(
        category=product.category, is_active=True
    ).exclude(pk=pk)[:4]

    return render(request, 'marketplace/detail.html', {
        'product': product,
        'reviews': reviews,
        'related': related,
    })


@login_required
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = cart.items.select_related('product').all()
    subtotal = sum(i.product.price * i.quantity for i in items)
    fee = _FEE()
    delivery = fee if items else 0
    total = subtotal + delivery

    for item in items:
        item.subtotal = item.product.price * item.quantity

    return render(request, 'marketplace/cart.html', {
        'cart_items': items,
        'subtotal': subtotal,
        'total': total,
    })


def add_to_cart(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Login required'})
    try:
        data = json.loads(request.body)
        product = get_object_or_404(Product, pk=data['product_id'], is_active=True)
        cart, _ = Cart.objects.get_or_create(user=request.user)
        qty = int(data.get('quantity', 1))
        item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        if created:
            # New item — enforce stock ceiling on creation too
            item.quantity = min(qty, product.stock) if product.stock > 0 else 0
            if item.quantity == 0:
                item.delete()
                return JsonResponse({'success': False, 'message': 'Item is out of stock'})
            item.save()
        else:
            item.quantity = min(item.quantity + qty, product.stock)
            item.save()
        cart_count = sum(i.quantity for i in cart.items.all())
        request.session['cart_count'] = cart_count
        return JsonResponse({'success': True, 'cart_count': cart_count})
    except Exception:
        logger.exception("add_to_cart failed for user %s", request.user.pk)
        return JsonResponse({'success': False, 'error': 'Could not add item. Please try again.'})


def update_cart(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False})
    try:
        data = json.loads(request.body)
        item = get_object_or_404(CartItem, pk=data['item_id'], cart__user=request.user)
        item.quantity = max(1, min(int(data['quantity']), item.product.stock))
        item.save()
        subtotal = item.product.price * item.quantity
        cart = item.cart
        items = list(cart.items.select_related('product').all())
        cart_sub = sum(i.product.price * i.quantity for i in items)
        return JsonResponse({
            'success': True,
            'item_subtotal': float(subtotal),
            'cart_subtotal': float(cart_sub),
            'cart_total': float(cart_sub + _FEE()),
        })
    except Exception:
        logger.exception("update_cart failed for user %s", request.user.pk)
        return JsonResponse({'success': False, 'error': 'Could not update cart. Please try again.'})


def remove_from_cart(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False})
    try:
        data = json.loads(request.body)
        item = get_object_or_404(CartItem, pk=data['item_id'], cart__user=request.user)
        cart = item.cart
        item.delete()
        # Single query after deletion
        remaining = list(cart.items.select_related('product').all())
        cart_count = sum(i.quantity for i in remaining)
        cart_sub = sum(i.product.price * i.quantity for i in remaining)
        request.session['cart_count'] = cart_count
        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
            'cart_subtotal': float(cart_sub),
            'cart_total': float(cart_sub + (_FEE() if cart_count else 0)),
        })
    except Exception:
        logger.exception("remove_from_cart failed for user %s", request.user.pk)
        return JsonResponse({'success': False, 'error': 'Could not remove item. Please try again.'})


@login_required
def checkout_view(request):
    cart = get_object_or_404(Cart, user=request.user)
    items = list(cart.items.select_related('product').all())
    if not items:
        return redirect('marketplace:list')

    for item in items:
        item.subtotal = item.product.price * item.quantity

    if request.method == 'POST':
        with transaction.atomic():
            # Re-fetch with select_for_update to lock rows during stock check + decrement
            fresh_items = list(
                cart.items.select_related('product')
                .select_for_update()
                .all()
            )
            out_of_stock = [i for i in fresh_items if i.product.stock < i.quantity]
            if out_of_stock:
                names = ', '.join(i.product.name for i in out_of_stock)
                # Use fresh_items subtotals for accurate error display
                for fi in fresh_items:
                    fi.subtotal = fi.product.price * fi.quantity
                err_subtotal = sum(fi.subtotal for fi in fresh_items)
                fee = _FEE()
                return render(request, 'marketplace/checkout.html', {
                    'cart_items': fresh_items,
                    'subtotal': err_subtotal,
                    'delivery_fee': fee,
                    'total': err_subtotal + fee,
                    'error': f'Insufficient stock for: {names}',
                })

            subtotal = sum(i.product.price * i.quantity for i in fresh_items)
            p = request.POST
            delivery_address = (
                f"{p.get('first_name', '')} {p.get('last_name', '')}\n"
                f"Phone: {p.get('phone', '')}\n"
                f"{p.get('address', '')}, {p.get('city', '')}, {p.get('district', '')}\n"
                f"Notes: {p.get('notes', '')}".strip()
            )
            payment_method = request.POST.get('payment_method', 'cod')
            if payment_method not in ('cod', 'khalti'):
                # eSewa/bank not yet implemented — reject rather than silently downgrade
                for fi in fresh_items:
                    fi.subtotal = fi.product.price * fi.quantity
                err_sub = sum(fi.subtotal for fi in fresh_items)
                fee = _FEE()
                return render(request, 'marketplace/checkout.html', {
                    'cart_items': fresh_items,
                    'subtotal': err_sub,
                    'delivery_fee': fee,
                    'total': err_sub + fee,
                    'error': f'"{payment_method}" is not yet available. Please use Cash on Delivery or Khalti.',
                })
            fee = _FEE()
            order = Order.objects.create(
                user=request.user,
                total_amount=subtotal + fee,
                status='pending',
                delivery_address=delivery_address,
                notes=p.get('notes', ''),
                payment_method=payment_method,
            )
            for item in fresh_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price=item.product.price,
                )
                Product.objects.filter(pk=item.product.pk).update(stock=F('stock') - item.quantity)
            cart.items.all().delete()
            _send_order_confirmation(order, fresh_items)
        request.session['cart_count'] = 0
        # Khalti: redirect to payment initiation (full-page, not AJAX)
        if payment_method == 'khalti':
            return redirect(f'/marketplace/khalti/initiate/{order.pk}/')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'order_id': order.pk})
        return redirect('core:orders')

    subtotal = sum(i.subtotal for i in items)
    fee = _FEE()
    return render(request, 'marketplace/checkout.html', {
        'cart_items': items,
        'subtotal': subtotal,
        'delivery_fee': fee,
        'total': subtotal + fee,
    })


# ── KHALTI PAYMENT INTEGRATION ──────────────────────────────────────────────

@login_required
def khalti_initiate(request, order_id):
    """Initiate a Khalti payment for a given order."""
    import requests as req_lib
    from django.conf import settings as dj_settings
    from django.contrib import messages

    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.payment_status == 'paid':
        messages.error(request, 'This order has already been paid.')
        return redirect('marketplace:checkout')

    secret_key = getattr(dj_settings, 'KHALTI_SECRET_KEY', '')
    if not secret_key:
        messages.error(request, 'Payment gateway not configured. Please use Cash on Delivery.')
        return redirect('marketplace:checkout')

    site_url = getattr(dj_settings, 'SITE_URL', 'http://localhost:8000')
    payload = {
        'return_url': f'{site_url}/marketplace/khalti/verify/',
        'website_url': site_url,
        'amount': int(order.total_amount * 100),  # Khalti uses paisa (1 NPR = 100 paisa)
        'purchase_order_id': str(order.pk),
        'purchase_order_name': f'Bhaktapur Order #{order.pk}',
        'customer_info': {
            'name': order.user.get_full_name() or order.user.username,
            'email': order.user.email,
        },
    }
    try:
        resp = req_lib.post(
            f"{dj_settings.KHALTI_API_URL}epayment/initiate/",
            json=payload,
            headers={'Authorization': f'Key {secret_key}'},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        pidx = data.get('pidx', '')
        payment_url = data.get('payment_url', '')
        if not payment_url:
            raise ValueError('No payment_url in Khalti response')
        # Save pidx for verification
        Order.objects.filter(pk=order.pk).update(
            khalti_pidx=pidx,
            payment_status='pending',
            payment_method='khalti',
        )
        return redirect(payment_url)
    except Exception as e:
        messages.error(request, 'Could not connect to Khalti. Please try Cash on Delivery.')
        return redirect(f'/marketplace/order/{order_id}/')


@login_required
def khalti_verify(request):
    """Called by Khalti after payment. Verify and mark order as paid."""
    import requests as req_lib
    from django.conf import settings as dj_settings
    from django.contrib import messages

    pidx = request.GET.get('pidx', '')
    status_param = request.GET.get('status', '')

    if status_param != 'Completed' or not pidx:
        messages.error(request, 'Payment was cancelled or failed. Please try again.')
        return redirect('/marketplace/')

    # Resolve order from our own database using the pidx we stored at initiation.
    # Never trust purchase_order_id from the callback — it could be tampered.
    try:
        order = Order.objects.get(khalti_pidx=pidx, user=request.user)
    except Order.DoesNotExist:
        logger.error("khalti_verify: no order found for pidx=%s user=%s", pidx, request.user.pk)
        messages.error(request, 'Payment reference not found. Contact support if amount was deducted.')
        return redirect('/marketplace/')

    if order.payment_status == 'paid':
        return redirect(f'/marketplace/order/{order.pk}/?paid=1')

    secret_key = getattr(dj_settings, 'KHALTI_SECRET_KEY', '')
    try:
        resp = req_lib.post(
            f"{dj_settings.KHALTI_API_URL}epayment/lookup/",
            json={'pidx': pidx},
            headers={'Authorization': f'Key {secret_key}'},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('status') != 'Completed':
            logger.warning("khalti_verify: Khalti status not Completed for pidx=%s — got %s", pidx, data.get('status'))
            messages.error(request, 'Payment verification failed. Contact support.')
            return redirect('/marketplace/')
        transaction_id = data.get('transaction_id', '')
        Order.objects.filter(pk=order.pk).update(
            payment_status='paid',
            khalti_transaction_id=transaction_id,
            status='processing',
        )
        logger.info("khalti_verify: order %s paid via Khalti txn %s", order.pk, transaction_id)
        messages.success(request, f'Payment successful! Transaction ID: {transaction_id}')
        return redirect(f'/marketplace/order/{order.pk}/?paid=1')
    except Exception:
        logger.exception("khalti_verify: verification error for pidx=%s order=%s", pidx, order.pk)
        messages.error(request, 'Payment verification error. If amount was deducted, contact support.')
        return redirect('/marketplace/')
