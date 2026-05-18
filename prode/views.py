from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated, AllowAny
from .models import (
    Tournament, Match, Prediction, PredefinedTournamentTemplate,
    TemplateMatch, Team, TournamentRankingSnapshot,
)
from django.db.models import Q, Sum, Count, Case, When, IntegerField
from django.db import transaction
from django.utils import timezone
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
    TournamentRankingSnapshotSerializer,
)


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser


def recalculate_points(match):
    """
    Recalculate points for all predictions on a finished match.
    Returns the number of predictions whose points_earned actually changed.
    Safe to call multiple times (idempotent for the same scores).
    """
    home_real = match.home_score_real
    away_real = match.away_score_real

    if home_real is None or away_real is None:
        return 0

    updated_count = 0
    predictions = Prediction.objects.filter(match=match)
    for prediction in predictions:
        home_guess = prediction.home_score_guess
        away_guess = prediction.away_score_guess

        new_points = 0
        if home_guess == home_real and away_guess == away_real:
            new_points = 3
        elif (home_guess > away_guess and home_real > away_real) or \
             (home_guess < away_guess and home_real < away_real) or \
             (home_guess == away_guess and home_real == away_real):
            new_points = 1

        if prediction.points_earned != new_points:
            prediction.points_earned = new_points
            prediction.save(update_fields=['points_earned'])
            updated_count += 1

    return updated_count


def resolve_team_ids_from_names(matches_data):
    """
    Given a list of match dicts that may contain home_team_name / away_team_name,
    build a mapping of lowercase name -> Team id.
    If any name is missing from the DB, return (None, missing_names).
    Otherwise return (name_to_id_map, []).
    Supports both id and name fields. When a name is provided, it takes precedence.
    """
    names = []
    for item in matches_data:
        if isinstance(item, dict):
            for key in ('home_team_name', 'away_team_name'):
                name = item.get(key, '').strip()
                if name:
                    names.append(name.lower())

    if not names:
        return {}, []

    q = Q()
    for name in set(names):
        q |= Q(name__iexact=name)

    teams = Team.objects.filter(q)
    name_to_id = {}
    for team in teams:
        name_to_id[team.name.lower()] = team.id
        for trans in team.translations.all():
            name_to_id[trans.name.lower()] = team.id

    missing = [n for n in set(names) if n not in name_to_id]
    return name_to_id, missing


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
            if tournament.is_finished:
                return Response(
                    {"detail": "This tournament has already finished and is no longer accepting participants"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            tournament.participants.add(request.user)
            return Response({"detail": f"Joined {tournament.name}", "tournament_id": tournament.id}, status=status.HTTP_200_OK)
        except Tournament.DoesNotExist:
            return Response({"detail": "Invalid tournament code"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='by_code', permission_classes=[AllowAny])
    def by_code(self, request):
        """
        Return public tournament info by invitation code.
        No auth required so prospective participants can preview before joining.
        """
        code = request.query_params.get('code', '').strip().upper()
        if not code:
            return Response(
                {"detail": "code query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            tournament = Tournament.objects.select_related('owner', 'banner').get(invitation_code=code)
        except Tournament.DoesNotExist:
            return Response({"detail": "Invalid tournament code"}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "id": tournament.id,
            "name": tournament.name,
            "description": tournament.description,
            "invitation_code": tournament.invitation_code,
            "owner_name": tournament.owner.username,
            "participant_count": tournament.participants.count(),
            "is_finished": tournament.is_finished,
            "banner_url": tournament.banner.image_url if tournament.banner else None,
        })

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
    def finish(self, request, pk=None):
        """
        Mark the tournament as finished and snapshot the final rankings.
        Only the tournament owner can finish a tournament.
        """
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can finish this tournament"},
                status=status.HTTP_403_FORBIDDEN
            )

        if tournament.is_finished:
            return Response(
                {"detail": "This tournament is already finished"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Build final leaderboard with detailed stats
        predictions = Prediction.objects.filter(tournament=tournament)
        rankings = (
            predictions.values('user')
            .annotate(
                total_points=Sum('points_earned'),
                exact=Count(Case(When(points_earned=3, then=1), output_field=IntegerField())),
                partial=Count(Case(When(points_earned=1, then=1), output_field=IntegerField())),
                total=Count('id'),
            )
            .order_by('-total_points')
        )

        with transaction.atomic():
            created_snapshots = []
            for rank_idx, entry in enumerate(rankings, start=1):
                snapshot = TournamentRankingSnapshot.objects.create(
                    tournament=tournament,
                    user_id=entry['user'],
                    rank=rank_idx,
                    points=entry['total_points'] or 0,
                    exact_predictions=entry['exact'],
                    partial_predictions=entry['partial'],
                    total_predictions=entry['total'],
                )
                created_snapshots.append(snapshot)

            tournament.is_finished = True
            tournament.finished_at = timezone.now()
            tournament.save(update_fields=['is_finished', 'finished_at'])

        serializer = TournamentRankingSnapshotSerializer(created_snapshots, many=True)
        return Response(
            {
                "detail": f"Tournament finished. {len(created_snapshots)} participants ranked.",
                "rankings": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def toggle_visibility(self, request, pk=None):
        """
        Toggle whether a finished tournament is visible on the dashboard.
        Only the tournament owner can toggle visibility.
        """
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can change visibility"},
                status=status.HTTP_403_FORBIDDEN
            )

        tournament.is_visible_when_finished = not tournament.is_visible_when_finished
        tournament.save(update_fields=['is_visible_when_finished'])

        serializer = self.get_serializer(tournament)
        return Response(
            {
                "detail": "Visibility updated",
                "tournament": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get'])
    def ranking_history(self, request, pk=None):
        """
        Return the stored ranking snapshot for a finished tournament.
        """
        tournament = self.get_object()
        snapshots = tournament.ranking_snapshots.select_related('user').all()
        serializer = TournamentRankingSnapshotSerializer(snapshots, many=True)
        return Response(serializer.data)

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

    @action(detail=True, methods=['post'])
    def bulk_matches(self, request, pk=None):
        """
        Create multiple matches and link them to this tournament.
        Accepts home_team_id / away_team_id OR home_team_name / away_team_name.
        All-or-nothing atomic transaction.
        """
        tournament = self.get_object()

        if tournament.owner != request.user:
            return Response(
                {"detail": "Only the tournament admin can add matches"},
                status=status.HTTP_403_FORBIDDEN
            )

        matches_data = request.data.get('matches', [])
        if not matches_data:
            return Response(
                {"detail": "'matches' array is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(matches_data, list):
            return Response(
                {"detail": "'matches' must be a list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Resolve team names to IDs before creating
        name_to_id, missing = resolve_team_ids_from_names(matches_data)
        if missing:
            return Response(
                {"detail": f"Unknown team names: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            created_matches = []
            for idx, match_item in enumerate(matches_data):
                match_payload = {
                    'home_team_id': name_to_id.get(match_item.get('home_team_name', '').strip().lower()) or match_item.get('home_team_id'),
                    'away_team_id': name_to_id.get(match_item.get('away_team_name', '').strip().lower()) or match_item.get('away_team_id'),
                    'match_date': match_item.get('match_date'),
                    'stage': match_item.get('stage', ''),
                    'source': 'custom',
                }
                serializer = MatchSerializer(data=match_payload)
                if not serializer.is_valid():
                    return Response(
                        {"detail": f"Match at index {idx} is invalid", "errors": serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                match = serializer.save()
                match.tournaments.add(tournament)
                created_matches.append(match)

            response_serializer = MatchSerializer(created_matches, many=True)

        return Response(
            {"created": len(created_matches), "matches": response_serializer.data},
            status=status.HTTP_201_CREATED
        )


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

        home_score = request.data.get('home_score_real')
        away_score = request.data.get('away_score_real')

        if home_score is None or away_score is None:
            return Response(
                {"detail": "home_score_real and away_score_real are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        home_score = int(home_score)
        away_score = int(away_score)

        # Idempotent: already finished with same scores -> no-op
        if match.status == 'finished':
            if match.home_score_real == home_score and match.away_score_real == away_score:
                updated = recalculate_points(match)
                return Response({
                    "match": MatchSerializer(match).data,
                    "predictions_updated": updated,
                }, status=status.HTTP_200_OK)
            # Scores changed -> update and recalculate
            match.home_score_real = home_score
            match.away_score_real = away_score
            match.save(update_fields=['home_score_real', 'away_score_real'])
            updated = recalculate_points(match)
            return Response({
                "match": MatchSerializer(match).data,
                "predictions_updated": updated,
            }, status=status.HTTP_200_OK)

        if match.status != 'live':
            return Response(
                {"detail": f"Match must be live to finish, currently {match.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        match.home_score_real = home_score
        match.away_score_real = away_score
        match.status = 'finished'
        match.save()

        updated = recalculate_points(match)

        return Response({
            "match": MatchSerializer(match).data,
            "predictions_updated": updated,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def recalculate(self, request, pk=None):
        """
        Force recalculation of points for a finished match.
        Useful if the scoring logic was fixed and old matches need re-scoring.
        """
        match = self.get_object()

        if match.status != 'finished':
            return Response(
                {"detail": f"Match must be finished to recalculate, currently {match.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if match.source == 'pool':
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superadmins can recalculate pool matches"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            if not match.tournaments.filter(owner=request.user).exists():
                return Response(
                    {"detail": "Only the tournament admin can recalculate custom matches"},
                    status=status.HTTP_403_FORBIDDEN
                )

        updated = recalculate_points(match)

        return Response({
            "match": MatchSerializer(match).data,
            "predictions_updated": updated,
        }, status=status.HTTP_200_OK)


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

    @action(detail=True, methods=['post'])
    def bulk_matches(self, request, pk=None):
        """
        Create multiple TemplateMatch records for this template.
        Accepts home_team_id / away_team_id OR home_team_name / away_team_name.
        All-or-nothing atomic transaction.
        """
        template = self.get_object()
        matches_data = request.data.get('matches', [])

        if not matches_data:
            return Response(
                {"detail": "'matches' array is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(matches_data, list):
            return Response(
                {"detail": "'matches' must be a list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Resolve team names to IDs before creating
        name_to_id, missing = resolve_team_ids_from_names(matches_data)
        if missing:
            return Response(
                {"detail": f"Unknown team names: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            created = []
            for idx, item in enumerate(matches_data):
                payload = {
                    'template': template.id,
                    'home_team_id': name_to_id.get(item.get('home_team_name', '').strip().lower()) or item.get('home_team_id'),
                    'away_team_id': name_to_id.get(item.get('away_team_name', '').strip().lower()) or item.get('away_team_id'),
                    'match_date': item.get('match_date'),
                    'stage': item.get('stage', ''),
                }
                serializer = TemplateMatchSerializer(data=payload)
                if not serializer.is_valid():
                    return Response(
                        {"detail": f"Match at index {idx} is invalid", "errors": serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                tm = serializer.save()
                created.append(tm)

            response_serializer = TemplateMatchSerializer(created, many=True)

        return Response(
            {"created": len(created), "matches": response_serializer.data},
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

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Create multiple teams from a JSON array.
        Skips teams whose name already exists (case-insensitive).
        All-or-nothing atomic transaction.
        """
        teams_data = request.data.get('teams', [])
        if not teams_data:
            return Response(
                {"detail": "'teams' array is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(teams_data, list):
            return Response(
                {"detail": "'teams' must be a list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Pre-check for existing names to provide clear feedback
        names_lower = [t.get('name', '').strip().lower() for t in teams_data if t.get('name')]
        if names_lower:
            q = Q()
            for name in names_lower:
                q |= Q(name__iexact=name)
            existing = set(Team.objects.filter(q).values_list('name', flat=True))
            if existing:
                return Response(
                    {"detail": f"Teams already exist: {', '.join(existing)}"},
                    status=status.HTTP_409_CONFLICT
                )

        with transaction.atomic():
            created = []
            serializer = TeamSerializer(data=teams_data, many=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            created = serializer.data

        return Response(
            {"created": len(created), "teams": created},
            status=status.HTTP_201_CREATED
        )
