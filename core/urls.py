from django.contrib import admin

from django.urls import path, include
from users.views import CustomTokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('api/prode/', include('prode.urls')), # Las rutas ahora vivirán en /api/
]