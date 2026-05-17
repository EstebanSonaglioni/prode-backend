from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from .models import Tournament, Match, Prediction, PredefinedTournamentTemplate, TemplateMatch, Team
from django.db.models import Q, Sum
from django.contrib.contenttypes.models import ContentType
from media.models import UploadedImage
from media.serializers import BannerSerializer
from .serializers import (
    TournamentSerializer,
    MatchSerializer,
    PredictionSerializer,
    PredefinedTournamentTemplateSerializer,
    TemplateMatchSerializer,
    TeamSerializer,
)


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser


def recalculate_points(match):
    """Recalculate points for all predictions on a finished match."""
    home_real = match.home_score_real
    away_real = match.away_score_real

    if home_real is None or away_real is None:
        return

    predictions = Prediction.objects.filter(match=match)
    for prediction in predictions:
        home_guess = prediction.home_score_guess
        away_guess = prediction.away_score_guess

        if home_guess == home_real and away_guess == away_real:
            prediction.points_earned = 3
        elif (home_guess > away_guess and home_real > away_real) or \
             (home_guess < away_guess and home_real < away_real) or \
             (home_guess == away_guess and home_real == away_real):
            prediction.points_earned = 1
        else:
            prediction.points_earned = 0

        prediction.save()


class TournamentViewSet(viewsets.ModelViewSet):
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        template_id = request.data.get('template_id')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        tournament = serializer.instance

        if template_id:
            try:
                template = PredefinedTournamentTemplate.objects.get(id=template_id)
                pool_matches = Match.objects.filter(
                    source='pool', template=template
                ).exclude(
                    id__in=tournament.matches.values_list('id', flat=True)
                )
                for match in pool_matches:
                    tournament.matches.add(match)
            except PredefinedTournamentTemplate.DoesNotExist:
                pass

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        user = self.request.user
        return Tournament.objects.filter(
            Q(owner=user) | Q(participants=user)
        ).distinct()

    def destroy(self, request, *args, **kwargs):
        tournament = self.get_object()
        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can delete this tournament"},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

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
        rankings = (
            Prediction.objects.filter(tournament=tournament)
            .values('user__id', 'user__username')
            .annotate(total_points=Sum('points_earned'))
            .order_by('-total_points')
        )
        return Response(list(rankings))

    @action(detail=True, methods=['post'])
    def add_predefined(self, request, pk=None):
        """Link existing pool matches from a predefined template to this tournament."""
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can add predefined matches"},
                status=status.HTTP_403_FORBIDDEN
            )

        template_id = request.data.get('template_id')
        if not template_id:
            return Response(
                {"detail": "template_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            template = PredefinedTournamentTemplate.objects.get(id=template_id)
        except PredefinedTournamentTemplate.DoesNotExist:
            return Response(
                {"detail": "Predefined template not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        pool_matches = Match.objects.filter(
            source='pool', template=template
        ).exclude(
            id__in=tournament.matches.values_list('id', flat=True)
        )

        added_count = pool_matches.count()
        for match in pool_matches:
            tournament.matches.add(match)

        serializer = MatchSerializer(pool_matches, many=True)
        msg = (
            f"Added {added_count} matches from '{template.name}'"
            if added_count > 0
            else f"No matches available from '{template.name}'. The template may not be published yet."
        )
        return Response(
            {"detail": msg, "matches": serializer.data},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def add_pool_matches(self, request, pk=None):
        """Link all available pool matches not already in this tournament."""
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can add pool matches"},
                status=status.HTTP_403_FORBIDDEN
            )

        pool_matches = Match.objects.filter(source='pool').exclude(
            id__in=tournament.matches.values_list('id', flat=True)
        )

        added_count = pool_matches.count()
        for match in pool_matches:
            tournament.matches.add(match)

        serializer = MatchSerializer(pool_matches, many=True)
        return Response(
            {
                "detail": f"Added {added_count} pool matches",
                "matches": serializer.data
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get'])
    def available_pool_matches(self, request, pk=None):
        """List pool matches not yet added to this tournament."""
        tournament = self.get_object()
        pool_matches = Match.objects.filter(source='pool').exclude(
            id__in=tournament.matches.values_list('id', flat=True)
        )
        serializer = MatchSerializer(pool_matches, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def upload_banner(self, request, pk=None):
        """Upload a banner image for this tournament."""
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can upload a banner"},
                status=status.HTTP_403_FORBIDDEN
            )

        image_file = request.FILES.get('image')
        if not image_file:
            return Response(
                {"detail": "No image file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate extension
        allowed_extensions = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
        ext = image_file.name.split('.')[-1].lower()
        if ext not in allowed_extensions:
            return Response(
                {"detail": f"Invalid image format. Allowed: {', '.join(allowed_extensions)}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate size (5MB)
        max_size = 5 * 1024 * 1024
        if image_file.size > max_size:
            return Response(
                {"detail": "Image too large. Max size is 5MB."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Remove old banner if exists
        if tournament.banner:
            old_banner = tournament.banner
            tournament.banner = None
            tournament.save(update_fields=['banner'])
            old_banner.delete()

        # Create new UploadedImage linked to tournament
        ct = ContentType.objects.get_for_model(tournament)
        uploaded = UploadedImage.objects.create(
            image=image_file,
            category='banner',
            uploaded_by=request.user,
            content_type=ct,
            object_id=tournament.id,
        )

        tournament.banner = uploaded
        tournament.save(update_fields=['banner'])

        serializer = self.get_serializer(tournament)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def remove_banner(self, request, pk=None):
        """Remove the banner image from this tournament."""
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can remove the banner"},
                status=status.HTTP_403_FORBIDDEN
            )

        if tournament.banner:
            old_banner = tournament.banner
            tournament.banner = None
            tournament.save(update_fields=['banner'])
            old_banner.delete()

        serializer = self.get_serializer(tournament)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MatchViewSet(viewsets.ModelViewSet):
    queryset = Match.objects.all()
    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Match.objects.all()
        tournament_id = self.request.query_params.get('tournament')
        source = self.request.query_params.get('source')
        template_id = self.request.query_params.get('template')

        if tournament_id:
            queryset = queryset.filter(tournaments__id=tournament_id)
        if source:
            queryset = queryset.filter(source=source)
        if template_id:
            queryset = queryset.filter(template__id=template_id)

        return queryset

    @action(detail=False, methods=['post'])
    def create_in_tournament(self, request):
        tournament_id = request.data.get('tournament_id')
        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            return Response({"detail": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND)

        if tournament.owner != request.user:
            return Response({"detail": "Only the tournament admin can create matches"}, status=status.HTTP_403_FORBIDDEN)

        match_data = {
            'home_team_id': request.data.get('home_team_id'),
            'away_team_id': request.data.get('away_team_id'),
            'match_date': request.data.get('match_date'),
            'stage': request.data.get('stage', ''),
            'source': 'custom',
        }
        serializer = MatchSerializer(data=match_data)
        if serializer.is_valid():
            match = serializer.save()
            match.tournaments.add(tournament)
            response_serializer = MatchSerializer(match)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        match = self.get_object()

        if match.source == 'pool':
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superadmins can start pool matches"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            if not match.tournaments.filter(owner=request.user).exists():
                return Response(
                    {"detail": "Only the tournament admin can start custom matches"},
                    status=status.HTTP_403_FORBIDDEN
                )

        if match.status != 'scheduled':
            return Response(
                {"detail": f"Match is already {match.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        match.status = 'live'
        match.save()
        return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        match = self.get_object()

        if match.source == 'pool':
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superadmins can finish pool matches"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            if not match.tournaments.filter(owner=request.user).exists():
                return Response(
                    {"detail": "Only the tournament admin can finish custom matches"},
                    status=status.HTTP_403_FORBIDDEN
                )

        if match.status != 'live':
            return Response(
                {"detail": f"Match must be live to finish, currently {match.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        home_score = request.data.get('home_score_real')
        away_score = request.data.get('away_score_real')

        if home_score is None or away_score is None:
            return Response(
                {"detail": "home_score_real and away_score_real are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        match.home_score_real = int(home_score)
        match.away_score_real = int(away_score)
        match.status = 'finished'
        match.save()

        recalculate_points(match)

        return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)


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
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class PredefinedTournamentTemplateViewSet(viewsets.ModelViewSet):
    queryset = PredefinedTournamentTemplate.objects.prefetch_related('matches').all()
    serializer_class = PredefinedTournamentTemplateSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsSuperUser()]

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Create pool Match records from this template's matches."""
        template = self.get_object()
        created = []

        for template_match in template.matches.all():
            match, was_created = Match.objects.get_or_create(
                home_team=template_match.home_team,
                away_team=template_match.away_team,
                match_date=template_match.match_date,
                defaults={
                    'stage': template_match.stage,
                    'status': 'scheduled',
                    'source': 'pool',
                    'template': template,
                }
            )
            if was_created:
                created.append(match)
            elif match.template != template:
                match.template = template
                match.save()

        return Response(
            {
                "detail": f"Published {len(created)} new pool matches from '{template.name}'",
                "matches": MatchSerializer(created, many=True).data
            },
            status=status.HTTP_201_CREATED
        )


class TemplateMatchViewSet(viewsets.ModelViewSet):
    queryset = TemplateMatch.objects.all()
    serializer_class = TemplateMatchSerializer
    permission_classes = [IsSuperUser]

    def get_queryset(self):
        queryset = TemplateMatch.objects.all()
        template_id = self.request.query_params.get('template')
        if template_id:
            queryset = queryset.filter(template_id=template_id)
        return queryset


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all().order_by('name')
    serializer_class = TeamSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsSuperUser()]
