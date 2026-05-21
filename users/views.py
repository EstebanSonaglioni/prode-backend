from pathlib import Path

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth import get_user_model

from .serializers import RegisterSerializer
from rest_framework import generics, status
from rest_framework.permissions import AllowAny

from media.models import UploadedImage
from media.serializers import UploadedImageSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))

User = get_user_model()


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

            avatar_url = self.request.build_absolute_uri(user.avatar.url) if user.avatar else None
            response.data['user'] = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_superuser': user.is_superuser,
                'avatar_url': avatar_url,
            }

            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=secure_conf,
                samesite='Lax',
                max_age=900,
            )

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
    if not provided in the request body.
    """

    def post(self, request, *args, **kwargs):
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

        new_refresh = serializer.validated_data.get('refresh')
        if new_refresh:
            ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
            secure_conf = ENVIRONMENT == "production"
            max_age = 7 * 24 * 60 * 60

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
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "user": serializer.data["username"],
                "message": "Account created successfully. You can now log in."
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    user = request.user
    avatar_url = request.build_absolute_uri(user.avatar.url) if user.avatar else None
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "avatar_url": avatar_url,
        "date_joined": user.date_joined,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def upload_avatar(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

    image_file = request.FILES.get('image')
    if not image_file:
        return Response({"detail": "No image file provided"}, status=status.HTTP_400_BAD_REQUEST)

    allowed_extensions = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
    ext = image_file.name.split('.')[-1].lower()
    if ext not in allowed_extensions:
        return Response(
            {"detail": f"Invalid image format. Allowed: {', '.join(allowed_extensions)}."},
            status=status.HTTP_400_BAD_REQUEST
        )

    max_size = 5 * 1024 * 1024
    if image_file.size > max_size:
        return Response(
            {"detail": "Image too large. Max size is 5MB."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user

    # Delete old avatar file (Django handles storage deletion safely)
    if user.avatar:
        user.avatar.delete(save=False)
        user.save(update_fields=['avatar'])

    user.avatar = image_file
    user.save(update_fields=['avatar'])

    avatar_url = request.build_absolute_uri(user.avatar.url) if user.avatar else None
    return Response({
        "avatar_url": avatar_url,
        "detail": "Avatar updated successfully",
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def change_password(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')

    if not current_password or not new_password:
        return Response(
            {"detail": "Both current_password and new_password are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user
    if not user.check_password(current_password):
        return Response(
            {"detail": "Current password is incorrect"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save(update_fields=['password'])

    return Response({"detail": "Password changed successfully"})


@api_view(['GET'])
@permission_classes([AllowAny])
def my_rankings(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

    from prode.models import Tournament, Prediction, TournamentRankingSnapshot
    from django.db.models import Sum, Count, Case, When, IntegerField

    user = request.user

    # Finished tournaments (from snapshots)
    snapshots = (
        TournamentRankingSnapshot.objects
        .filter(user=user)
        .select_related('tournament')
        .order_by('-created_at')
    )

    finished = []
    for snap in snapshots:
        finished.append({
            "tournament_id": snap.tournament.id,
            "tournament_name": snap.tournament.name,
            "rank": snap.rank,
            "points": snap.points,
            "exact_predictions": snap.exact_predictions,
            "partial_predictions": snap.partial_predictions,
            "total_predictions": snap.total_predictions,
            "finished_at": snap.tournament.finished_at,
        })

    # Ongoing tournaments (live leaderboard position)
    ongoing_tournaments = (
        Tournament.objects
        .filter(participants=user, is_finished=False)
        .distinct()
    )

    ongoing = []
    for tournament in ongoing_tournaments:
        rankings = (
            Prediction.objects.filter(tournament=tournament)
            .values('user__id', 'user__username')
            .annotate(total_points=Sum('points_earned'))
            .order_by('-total_points')
        )

        user_rank = None
        user_points = 0
        for idx, entry in enumerate(rankings, start=1):
            if entry['user__id'] == user.id:
                user_rank = idx
                user_points = entry['total_points'] or 0
                break

        total_participants = rankings.count()
        total_predictions = Prediction.objects.filter(tournament=tournament, user=user).count()
        exact = Prediction.objects.filter(tournament=tournament, user=user, points_earned=3).count()
        partial = Prediction.objects.filter(tournament=tournament, user=user, points_earned=1).count()

        ongoing.append({
            "tournament_id": tournament.id,
            "tournament_name": tournament.name,
            "rank": user_rank,
            "points": user_points,
            "total_participants": total_participants,
            "exact_predictions": exact,
            "partial_predictions": partial,
            "total_predictions": total_predictions,
        })

    # Summary stats
    all_predictions = Prediction.objects.filter(user=user)
    total_predictions_made = all_predictions.count()
    total_exact = all_predictions.filter(points_earned=3).count()
    total_partial = all_predictions.filter(points_earned=1).count()
    total_points = all_predictions.aggregate(total=Sum('points_earned'))['total'] or 0

    best_finish = None
    if snapshots.exists():
        best = min(snapshots, key=lambda s: s.rank)
        best_finish = {
            "rank": best.rank,
            "tournament_name": best.tournament.name,
        }

    return Response({
        "finished": finished,
        "ongoing": ongoing,
        "summary": {
            "total_tournaments_finished": len(finished),
            "total_tournaments_ongoing": len(ongoing),
            "total_predictions": total_predictions_made,
            "total_points": total_points,
            "exact_predictions": total_exact,
            "partial_predictions": total_partial,
            "best_finish": best_finish,
        },
    })
