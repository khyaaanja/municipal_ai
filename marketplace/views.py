from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.db import transaction
from django.db.models import F
import json
from .models import Product, Cart, CartItem, Order, OrderItem


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
        f"Delivery Fee : NPR 100\n"
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
    category = request.GET.get('category', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    sort = request.GET.get('sort', 'newest')

    products = Product.objects.filter(is_active=True)

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

    return render(request, 'marketplace/list.html', {
        'products': products,
        'categories': categories,
        'active_category': category,
        'min_price': min_price,
        'max_price': max_price,
    })


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
    delivery = 100 if items else 0
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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


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
        cart_sub = sum(i.product.price * i.quantity for i in cart.items.all())
        return JsonResponse({
            'success': True,
            'item_subtotal': float(subtotal),
            'cart_subtotal': float(cart_sub),
            'cart_total': float(cart_sub + 100),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def remove_from_cart(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False})
    try:
        data = json.loads(request.body)
        item = get_object_or_404(CartItem, pk=data['item_id'], cart__user=request.user)
        item.delete()
        cart = Cart.objects.get(user=request.user)
        cart_count = sum(i.quantity for i in cart.items.all())
        cart_sub = sum(i.product.price * i.quantity for i in cart.items.all())
        request.session['cart_count'] = cart_count
        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
            'cart_subtotal': float(cart_sub),
            'cart_total': float(cart_sub + (100 if cart_count else 0)),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


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
                return render(request, 'marketplace/checkout.html', {
                    'cart_items': fresh_items,
                    'subtotal': err_subtotal,
                    'delivery_fee': 100,
                    'total': err_subtotal + 100,
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
            order = Order.objects.create(
                user=request.user,
                total_amount=subtotal + 100,
                status='pending',
                delivery_address=delivery_address,
                notes=p.get('notes', ''),
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
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'order_id': order.pk})
        return redirect('core:orders')

    subtotal = sum(i.subtotal for i in items)
    return render(request, 'marketplace/checkout.html', {
        'cart_items': items,
        'subtotal': subtotal,
        'delivery_fee': 100,
        'total': subtotal + 100,
    })
