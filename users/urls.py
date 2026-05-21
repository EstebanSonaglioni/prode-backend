from django.urls import path
from .views import (
    RegisterView, CustomTokenObtainPairView, CustomTokenRefreshView,
    me, upload_avatar, change_password, my_rankings,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('me/', me, name='me'),
    path('me/avatar/', upload_avatar, name='upload_avatar'),
    path('me/change_password/', change_password, name='change_password'),
    path('me/rankings/', my_rankings, name='my_rankings'),
]
