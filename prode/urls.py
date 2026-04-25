from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TournamentViewSet, MatchViewSet, PredictionViewSet

router = DefaultRouter()
router.register(r'tournaments', TournamentViewSet)
router.register(r'matches', MatchViewSet)
router.register(r'predictions', PredictionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]