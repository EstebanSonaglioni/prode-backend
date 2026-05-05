from pathlib import Path

from rest_framework_simplejwt.views import TokenObtainPairView
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
        secure_conf = ENVIRONMENT=="production"
        if response.status_code == 200:
            username = request.data.get('username')
            user = User.objects.get(username=username)
            
            access_token = response.data.get('access')

            # Agregamos los datos del usuario al cuerpo de la respuesta (data)
            # Esto es lo que Zustand recibirá en el frontend
            response.data['user'] = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            }
            response.set_cookie(
                    key='access_token',
                    value=access_token,
                    httponly=True,
                    secure=secure_conf,
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