from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Tournament, Match, Prediction
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated # Importante
from .serializers import TournamentSerializer, MatchSerializer, PredictionSerializer

class TournamentViewSet(viewsets.ModelViewSet):
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Filtramos: 
        # Que el usuario sea el dueño (owner)
        # O que el usuario esté en la lista de participantes (participants)
        return Tournament.objects.filter(
            Q(owner=user) | Q(participants=user)
        ).distinct() # .distinct() evita duplicados si el usuario es owner y participante a la vez

    @action(detail=False, methods=['post'])
    def join_by_code(self, request):
        print(self.request.user)
        code = request.data.get('invitation_code')
        try:
            tournament = Tournament.objects.get(invitation_code=code)
            # Evitar que el dueño se una a su propio torneo como participante
            # if tournament.owner == request.user:
            #     return Response({"detail": "Ya sos el dueño de este torneo"}, status=status.HTTP_400_BAD_REQUEST)
            
            tournament.participants.add(request.user)
            return Response({"detail": f"Te uniste a {tournament.name}"}, status=status.HTTP_200_OK)
        except Tournament.DoesNotExist:
            return Response({"detail": "Código de torneo inválido"}, status=status.HTTP_404_NOT_FOUND)

class MatchViewSet(viewsets.ModelViewSet):
    queryset = Match.objects.all()
    serializer_class = MatchSerializer

class PredictionViewSet(viewsets.ModelViewSet):
    queryset = Prediction.objects.all()
    serializer_class = PredictionSerializer
    
    # Filtro simple para que el usuario solo vea SUS predicciones
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return Prediction.objects.filter(user=user)
        return Prediction.objects.none()