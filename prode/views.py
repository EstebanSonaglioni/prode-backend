from rest_framework import viewsets
from .models import Tournament, Match, Prediction
from .serializers import TournamentSerializer, MatchSerializer, PredictionSerializer

class TournamentViewSet(viewsets.ModelViewSet):
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer

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