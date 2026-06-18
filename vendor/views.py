from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum


@login_required
def vendor_dashboard(request):
    try:
        vendor = request.user.vendor_profile
    except Exception:
        return redirect('/')

    from marketplace.models import Product, Order
    products = Product.objects.filter(vendor=vendor)
    recent_orders = Order.objects.filter(
        items__product__vendor=vendor
    ).distinct().order_by('-created_at')[:5]
    total_revenue = Order.objects.filter(
        items__product__vendor=vendor, status='completed'
    ).distinct().aggregate(total=Sum('total_amount'))['total'] or 0
    pending_orders = Order.objects.filter(
        items__product__vendor=vendor, status='pending'
    ).distinct().count()

    return render(request, 'vendor/dashboard.html', {
        'vendor': vendor,
        'products': products,
        'recent_orders': recent_orders,
        'total_revenue': total_revenue,
        'pending_orders': pending_orders,
        'product_count': products.count(),
        'total_orders': recent_orders.count(),
    })
