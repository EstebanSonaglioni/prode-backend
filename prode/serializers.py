from rest_framework import serializers
from .models import Tournament, Match, Prediction

class TournamentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = '__all__'

class MatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = '__all__'
        extra_kwargs = {
            'tournaments': {'required': False}
        }

class PredictionSerializer(serializers.ModelSerializer):
    # Esto es opcional, pero ayuda a ver el nombre del usuario en el JSON
    user_name = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Prediction
        fields = '__all__'