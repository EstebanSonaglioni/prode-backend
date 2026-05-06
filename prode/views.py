from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Tournament, Match, Prediction
from django.db.models import Q, Sum
from rest_framework.permissions import IsAuthenticated
from .serializers import TournamentSerializer, MatchSerializer, PredictionSerializer

class TournamentViewSet(viewsets.ModelViewSet):
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Tournament.objects.filter(
            Q(owner=user) | Q(participants=user)
        ).distinct()

    @action(detail=False, methods=['post'])
    def join_by_code(self, request):
        code = request.data.get('invitation_code')
        try:
            tournament = Tournament.objects.get(invitation_code=code)
            tournament.participants.add(request.user)
            return Response({"detail": f"Joined {tournament.name}"}, status=status.HTTP_200_OK)
        except Tournament.DoesNotExist:
            return Response({"detail": "Invalid tournament code"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'])
    def leaderboard(self, request, pk=None):
        """Return rankings for a tournament aggregated by user."""
        tournament = self.get_object()
        # Aggregate points per user for this tournament
        rankings = (
            Prediction.objects.filter(tournament=tournament)
            .values('user__id', 'user__username')
            .annotate(total_points=Sum('points_earned'))
            .order_by('-total_points')
        )
        return Response(list(rankings))

class MatchViewSet(viewsets.ModelViewSet):
    queryset = Match.objects.all()
    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tournament_id = self.request.query_params.get('tournament')
        if tournament_id:
            return Match.objects.filter(tournaments__id=tournament_id)
        return Match.objects.all()

    @action(detail=False, methods=['post'])
    def create_in_tournament(self, request):
        tournament_id = request.data.get('tournament_id')
        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            return Response({"detail": "Torneo no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if tournament.owner != request.user:
            return Response({"detail": "Solo el admin puede crear partidos"}, status=status.HTTP_403_FORBIDDEN)

        match_data = {
            'home_team': request.data.get('home_team'),
            'away_team': request.data.get('away_team'),
            'match_date': request.data.get('match_date'),
            'stage': request.data.get('stage', ''),
        }
        serializer = MatchSerializer(data=match_data)
        if serializer.is_valid():
            match = serializer.save()
            match.tournaments.add(tournament)
            response_serializer = MatchSerializer(match)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PredictionViewSet(viewsets.ModelViewSet):
    queryset = Prediction.objects.all()
    serializer_class = PredictionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Prediction.objects.filter(user=user)
        tournament_id = self.request.query_params.get('tournament')
        if tournament_id:
            queryset = queryset.filter(tournament_id=tournament_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Ensure the user can only create predictions for themselves
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)