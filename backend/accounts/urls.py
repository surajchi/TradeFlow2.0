from django.urls import path
from .views import (
    RegisterView, LoginView, LogoutView, UserProfileView,
    UserProfileDetailView, ChangePasswordView, RefreshTokenView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('refresh/', RefreshTokenView.as_view(), name='refresh'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/detail/', UserProfileDetailView.as_view(), name='profile-detail'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]
