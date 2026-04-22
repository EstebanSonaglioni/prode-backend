
from datetime import timedelta

INSTALLED_APPS = [
    # ... aplicaciones de django
    'rest_framework',
    'corsheaders',
    'predictions', # Tu app
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # Debe ir arriba de todo
    'django.middleware.common.CommonMiddleware',
    # ... otros middlewares
]

# Por ahora, permitimos que React (en localhost:5173) se conecte
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]


# ...

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

# Configuración de SimpleJWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
