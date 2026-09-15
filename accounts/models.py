import uuid
import hashlib
import re
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


def _fernet():
    """Return a Fernet cipher if TOTP_ENCRYPTION_KEY is configured."""
    key = getattr(settings, 'TOTP_ENCRYPTION_KEY', '')
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_otp_secret(plaintext: str) -> str:
    f = _fernet()
    if not f or not plaintext:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_otp_secret(ciphertext: str) -> str:
    f = _fernet()
    if not f or not ciphertext:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        import logging
        logging.getLogger(__name__).error(
            'decrypt_otp_secret failed — TOTP_ENCRYPTION_KEY may have changed. '
            '2FA will be broken for this user until the secret is reset.'
        )
        return ''


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
        if not extra_fields.get('username'):
            local_part = re.sub(
                r'[^a-zA-Z0-9._-]+',
                '-',
                email.split('@', 1)[0],
            ).strip('-._') or 'user'
            suffix = hashlib.sha256(email.encode('utf-8')).hexdigest()[:8]
            extra_fields['username'] = f'{local_part}-{suffix}'[:100]
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

    # NOTE:
    # Do NOT define `social_user` as a @property with no setter.
    # social-auth/social-core may attempt to assign to `user.social_user`.
    # If we override it as a read-only property, OAuth completion fails with:
    #   "property 'social_user' of 'User' object has no setter".
    #
    # social-django stores related social accounts via the reverse relation
    # `user.social_auth`.


    ROLE_CITIZEN     = 'citizen'

    ROLE_STAFF       = 'staff'
    ROLE_OFFICIAL    = 'official'
    ROLE_ADMIN       = 'admin'
    ROLE_MAYOR       = 'mayor'
    ROLE_CHAIRPERSON = 'chairperson'
    ROLE_CHOICES  = [
        ('citizen',     'Citizen'),
        ('staff',       'Municipality Staff'),
        ('official',    'Municipality Official'),
        ('admin',       'Platform Admin'),
        ('mayor',       'Mayor'),
        ('chairperson', 'Ward Chairperson'),
    ]

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    legacy_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen', db_index=True)
    provider = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    ward_number = models.IntegerField(null=True, blank=True, help_text='Ward number (1-17) for chairpersons')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    otp_secret  = models.CharField(max_length=256, blank=True, default='')
    otp_enabled = models.BooleanField(default=False)
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

    # OAuth identity fields
    # Google uses the stable `sub` value (unique per provider/account).
    google_id = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)

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


class Notification(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message    = models.CharField(max_length=300)
    url        = models.CharField(max_length=200, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at'], name='idx_notif_user_read_created'),
        ]

    def __str__(self):
        return f"Notification for {self.user.email}: {self.message[:50]}"
