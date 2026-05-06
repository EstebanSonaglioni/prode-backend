from django.db import models
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User # Usamos el modelo de usuario por defecto de Django

class Tournament(models.Model):
    """
    Represents a specific 'Prode' instance (e.g., 'Work World Cup 2026').
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    invitation_code = models.CharField(max_length=20, unique=True, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tournaments')
    is_private = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    participants = models.ManyToManyField(User, related_name='joined_tournaments', blank=True)

    def save(self, *args, **kwargs):
        if not self.invitation_code:
            # Generamos un código aleatorio de 10 caracteres (puedes ajustar el largo)
            self.invitation_code = get_random_string(length=10).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Match(models.Model):
    """
    Represents a real football match.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('finished', 'Finished'),
    ]

    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    match_date = models.DateTimeField()
    home_score_real = models.IntegerField(blank=True, null=True)
    away_score_real = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    stage = models.CharField(max_length=50, blank=True, null=True)
    tournaments = models.ManyToManyField(Tournament, related_name='matches')

    class Meta:
        verbose_name_plural = "Matches"

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"

class Prediction(models.Model):
    """
    A user's prediction for a specific match within a tournament.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='predictions')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='predictions')
    home_score_guess = models.IntegerField()
    away_score_guess = models.IntegerField()
    points_earned = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevents a user from predicting the same match twice in the same tournament
        unique_together = ('user', 'tournament', 'match')

    def __str__(self):
        return f"{self.user.username} - {self.match}"

class Team(models.Model):
    name = models.CharField(max_length=100)
    flag_url = models.URLField(blank=True)

    def __str__(self):
        return self.name