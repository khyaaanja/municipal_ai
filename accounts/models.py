from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.Model):
    GUEST = 'guest'
    TOURIST = 'tourist'
    RESIDENT = 'resident'
    VENDOR = 'vendor'
    STAFF = 'staff'
    SUPER_ADMIN = 'super_admin'

    ROLE_CHOICES = [
        (GUEST, 'Guest'),
        (TOURIST, 'Tourist'),
        (RESIDENT, 'Resident'),
        (VENDOR, 'Vendor'),
        (STAFF, 'Municipal Staff'),
        (SUPER_ADMIN, 'Super Admin'),
    ]

    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_name_display()

    class Meta:
        db_table = 'roles'


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CITIZEN  = 'citizen'
    ROLE_STAFF    = 'staff'
    ROLE_OFFICIAL = 'official'
    ROLE_ADMIN    = 'admin'
    ROLE_CHOICES  = [
        ('citizen',  'Citizen'),
        ('staff',    'Municipality Staff'),
        ('official', 'Municipality Official'),
        ('admin',    'Platform Admin'),
    ]

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    legacy_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen', db_index=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_role_name(self):
        return self.legacy_role.name if self.legacy_role else Role.GUEST

    def is_vendor(self):
        return self.role == 'vendor'

    def is_municipal_staff(self):
        return self.role in ('staff', 'official', 'admin')

    class Meta:
        db_table = 'users'


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    language_preference = models.CharField(max_length=10, default='en')
    notification_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile: {self.user.email}"

    class Meta:
        db_table = 'profiles'
