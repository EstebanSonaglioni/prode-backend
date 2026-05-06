from pathlib import Path

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.response import Response
from django.conf import settings

from .serializers import RegisterSerializer
from rest_framework import generics, status
from rest_framework.permissions import AllowAny

from django.contrib.auth.models import User
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))


class CustomTokenObtainPairView(TokenObtainPairView):

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
        secure_conf = ENVIRONMENT == "production"

        if response.status_code == 200:
            username = request.data.get('username')
            user = User.objects.get(username=username)

            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')
            remember_me = request.data.get('remember_me', False)

            # Agregamos los datos del usuario al cuerpo de la respuesta
            response.data['user'] = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            }

            # Access token como cookie httpOnly
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=secure_conf,
                samesite='Lax',
                max_age=900,  # 15 minutos
            )

            # Refresh token como cookie httpOnly
            # Si remember_me es True, dura 30 días. Si no, dura 1 día.
            refresh_max_age = 30 * 24 * 60 * 60 if remember_me else 24 * 60 * 60
            response.set_cookie(
                key='refresh_token',
                value=refresh_token,
                httponly=True,
                secure=secure_conf,
                samesite='Lax',
                max_age=refresh_max_age,
            )

        return response


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom refresh view that reads the refresh token from an httpOnly cookie
    if not provided in the request body. It also rotates the refresh token
    and sets the new one back in the cookie.
    """

    def post(self, request, *args, **kwargs):
        # Si no viene refresh en el body, tomarlo de la cookie
        if 'refresh' not in request.data:
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                request.data['refresh'] = refresh_token

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        # Rotar cookie de refresh token
        new_refresh = serializer.validated_data.get('refresh')
        if new_refresh:
            ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
            secure_conf = ENVIRONMENT == "production"
            # Mantener el max_age que ya tenía la cookie (lo leemos si existe)
            existing_max_age = request.COOKIES.get('refresh_token')
            # Default a 7 días si no sabemos
            max_age = 7 * 24 * 60 * 60
            if existing_max_age:
                # No podemos saber el max_age original de la cookie desde JS,
                # pero sí desde el backend. Usamos un valor fijo razonable.
                pass

            response.set_cookie(
                key='refresh_token',
                value=new_refresh,
                httponly=True,
                secure=secure_conf,
                samesite='Lax',
                max_age=max_age,
            )

        return response


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,) # Cualquiera puede registrarse
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "user": serializer.data["username"],
                "message": "Usuario creado exitosamente. Ahora puedes acceder."
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
