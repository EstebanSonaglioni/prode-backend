from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.response import Response
from django.conf import settings
from .serializers import RegisterSerializer
from rest_framework import generics, status
from rest_framework.permissions import AllowAny

from django.contrib.auth.models import User


class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            access_token = response.data.get('access')
            # Seteamos la cookie HttpOnly
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=False, # Ponelo en True cuando subas a Render (HTTPS)
                samesite='Lax'
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