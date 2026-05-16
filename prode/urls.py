from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TournamentViewSet,
    MatchViewSet,
    PredictionViewSet,
    PredefinedTournamentTemplateViewSet,
    TemplateMatchViewSet,
    TeamViewSet,
)

router = DefaultRouter()
router.register(r'tournaments', TournamentViewSet)
router.register(r'matches', MatchViewSet)
router.register(r'predictions', PredictionViewSet)
router.register(r'predefined-templates', PredefinedTournamentTemplateViewSet, basename='predefinedtemplate')
router.register(r'template-matches', TemplateMatchViewSet, basename='templatematch')
router.register(r'teams', TeamViewSet, basename='team')

urlpatterns = [
    path('', include(router.urls)),
]
