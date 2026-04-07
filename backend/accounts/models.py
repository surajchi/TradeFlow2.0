from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # Trading preferences
    default_currency = models.CharField(max_length=3, default='USD')
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Account status
    is_premium = models.BooleanField(default=False)
    premium_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Theme preference
    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System'),
    ]
    theme_preference = models.CharField(
        max_length=10, 
        choices=THEME_CHOICES, 
        default='system'
    )
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        db_table = 'accounts_user'
    
    def __str__(self):
        return self.email
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    
    # Trading experience
    EXPERIENCE_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('professional', 'Professional'),
    ]
    experience_level = models.CharField(
        max_length=20, 
        choices=EXPERIENCE_LEVELS, 
        default='beginner'
    )
    
    # Trading style
    TRADING_STYLES = [
        ('scalping', 'Scalping'),
        ('day_trading', 'Day Trading'),
        ('swing_trading', 'Swing Trading'),
        ('position_trading', 'Position Trading'),
        ('long_term', 'Long Term Investing'),
    ]
    trading_style = models.CharField(
        max_length=20, 
        choices=TRADING_STYLES, 
        default='day_trading'
    )
    
    # Risk management
    risk_per_trade = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=1.00,
        help_text='Risk percentage per trade'
    )
    max_daily_loss = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=3.00,
        help_text='Maximum daily loss percentage'
    )
    
    # Bio
    bio = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # Social links
    twitter = models.CharField(max_length=100, blank=True, null=True)
    linkedin = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'accounts_userprofile'
    
    def __str__(self):
        return f"{self.user.email}'s Profile"
