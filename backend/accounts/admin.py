from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_premium', 'created_at']
    list_filter = ['is_premium', 'is_staff', 'is_active', 'theme_preference']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering = ['-created_at']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Trading Info', {
            'fields': ('phone', 'default_currency', 'timezone', 'is_premium', 'theme_preference')
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'experience_level', 'trading_style', 'created_at']
    list_filter = ['experience_level', 'trading_style']
    search_fields = ['user__email', 'user__username']
