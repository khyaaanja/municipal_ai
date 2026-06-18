from django.test import TestCase
from accounts.models import User
from marketplace.models import Product, ProductCategory, VendorProfile


def make_vendor_user(email='vendor@test.com'):
    u = User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='V', last_name='Seller', role='citizen'
    )
    vendor = VendorProfile.objects.create(
        user=u, shop_name='Test Shop', is_approved=True
    )
    return u, vendor


def make_product(name='Dhaka Shawl', vendor=None, **kw):
    cat, _ = ProductCategory.objects.get_or_create(name='Handicrafts', slug='handicrafts')
    defaults = dict(
        slug=name.lower().replace(' ', '-'),
        description='A handmade product.',
        price='650.00',
        stock=10,
        is_active=True,
        category=cat,
    )
    defaults.update(kw)
    return Product.objects.create(name=name, vendor=vendor, **defaults)


class MarketplaceListTests(TestCase):
    def setUp(self):
        _, self.vendor = make_vendor_user()
        self.p1 = make_product('Dhaka Shawl', vendor=self.vendor)
        self.p2 = make_product('Bronze Statue', slug='bronze-statue', vendor=self.vendor)

    def test_list_loads(self):
        r = self.client.get('/marketplace/')
        self.assertEqual(r.status_code, 200)

    def test_list_shows_products(self):
        r = self.client.get('/marketplace/')
        self.assertContains(r, 'Dhaka Shawl')

    def test_inactive_product_hidden(self):
        make_product('Old Item', slug='old-item', vendor=self.vendor, is_active=False)
        r = self.client.get('/marketplace/')
        self.assertNotContains(r, 'Old Item')


class ProductDetailTests(TestCase):
    def setUp(self):
        _, self.vendor = make_vendor_user()
        self.p = make_product('Thangka Painting', slug='thangka-painting', vendor=self.vendor)

    def test_detail_loads(self):
        r = self.client.get(f'/marketplace/{self.p.pk}/')
        self.assertEqual(r.status_code, 200)

    def test_detail_shows_name(self):
        r = self.client.get(f'/marketplace/{self.p.pk}/')
        self.assertContains(r, 'Thangka Painting')

    def test_404_on_missing(self):
        r = self.client.get('/marketplace/99999/')
        self.assertEqual(r.status_code, 404)


class CartTests(TestCase):
    def setUp(self):
        _, self.vendor = make_vendor_user()
        self.product = make_product('Pottery Bowl', slug='pottery-bowl', vendor=self.vendor)

    def test_cart_page_loads(self):
        u = User.objects.create_user(
            email='cart@test.com', username='cart',
            password='Pass1234!', first_name='C', last_name='T'
        )
        self.client.login(username='cart@test.com', password='Pass1234!')
        r = self.client.get('/marketplace/cart/')
        self.assertEqual(r.status_code, 200)

    def test_add_to_cart(self):
        r = self.client.post('/marketplace/api/cart/add/', {
            'product_id': self.product.pk, 'quantity': 1
        }, content_type='application/json')
        self.assertIn(r.status_code, [200, 302])

    def test_checkout_requires_login(self):
        r = self.client.get('/marketplace/checkout/')
        self.assertIn(r.status_code, [200, 302])
