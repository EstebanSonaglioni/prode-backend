from django.utils import timezone
from rest_framework import serializers
from .models import Tournament, Match, Prediction, PredefinedTournamentTemplate, TemplateMatch, Team, TeamTranslation
from media.serializers import BannerSerializer


class TeamTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamTranslation
        fields = ['language', 'name']


class TeamSerializer(serializers.ModelSerializer):
    flag = serializers.SerializerMethodField()
    translations = TeamTranslationSerializer(many=True, required=False)

    class Meta:
        model = Team
        fields = ['id', 'name', 'code', 'flag_url', 'is_national', 'flag', 'translations']

    def get_flag(self, obj):
        return obj.get_flag_url()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            lang = request.query_params.get('lang') or request.headers.get('Accept-Language', 'en').split(',')[0].split(';')[0].strip()
            data['name'] = instance.get_translated_name(language=lang)
        return data

    def create(self, validated_data):
        translations_data = validated_data.pop('translations', [])
        team = super().create(validated_data)
        for trans in translations_data:
            TeamTranslation.objects.create(team=team, **trans)
        return team

    def update(self, instance, validated_data):
        translations_data = validated_data.pop('translations', None)
        team = super().update(instance, validated_data)
        if translations_data is not None:
            team.translations.all().delete()
            for trans in translations_data:
                TeamTranslation.objects.create(team=team, **trans)
        return team


class UpcomingMatchSerializer(serializers.ModelSerializer):
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    has_prediction = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = ['id', 'home_team', 'away_team', 'match_date', 'stage', 'has_prediction']

    def get_has_prediction(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return True
        return Prediction.objects.filter(
            match=obj, user=request.user, tournament=obj.tournaments.first()
        ).exists()


class TournamentSerializer(serializers.ModelSerializer):
    banner = BannerSerializer(read_only=True)
    upcoming_matches = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = '__all__'

    def get_upcoming_matches(self, obj):
        now = timezone.now()
        matches = obj.matches.filter(
            status='scheduled',
            match_date__gte=now,
        ).order_by('match_date')[:3]
        return UpcomingMatchSerializer(
            matches, many=True, context=self.context
        ).data


class MatchSerializer(serializers.ModelSerializer):
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    home_team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), source='home_team', write_only=True
    )
    away_team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), source='away_team', write_only=True
    )

    class Meta:
        model = Match
        fields = [
            'id', 'home_team', 'away_team', 'home_team_id', 'away_team_id',
            'match_date', 'home_score_real', 'away_score_real', 'status', 'stage',
            'tournaments', 'source', 'template'
        ]
        extra_kwargs = {
            'tournaments': {'required': False}
        }


class PredictionSerializer(serializers.ModelSerializer):
    # Esto es opcional, pero ayuda a ver el nombre del usuario en el JSON
    user_name = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Prediction
        fields = '__all__'


class TemplateMatchSerializer(serializers.ModelSerializer):
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    home_team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), source='home_team', write_only=True
    )
    away_team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), source='away_team', write_only=True
    )

    class Meta:
        model = TemplateMatch
        fields = [
            'id', 'template', 'home_team', 'away_team',
            'home_team_id', 'away_team_id', 'match_date', 'stage'
        ]


class PredefinedTournamentTemplateSerializer(serializers.ModelSerializer):
    matches = TemplateMatchSerializer(many=True, read_only=True)
    match_count = serializers.SerializerMethodField()

    class Meta:
        model = PredefinedTournamentTemplate
        fields = '__all__'

    def get_match_count(self, obj):
        return obj.matches.count()
