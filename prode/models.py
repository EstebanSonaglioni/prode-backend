from django.db import models
from django.utils.crypto import get_random_string
from django.conf import settings

class Tournament(models.Model):
    """
    Represents a specific 'Prode' instance (e.g., 'Work World Cup 2026').
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    invitation_code = models.CharField(max_length=20, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_tournaments')
    is_private = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='joined_tournaments', blank=True)
    banner = models.ForeignKey(
        'media.UploadedImage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_banner',
    )
    is_finished = models.BooleanField(default=False, help_text="When true, no new participants can join and the final ranking is locked.")
    finished_at = models.DateTimeField(blank=True, null=True)
    is_visible_when_finished = models.BooleanField(default=True, help_text="If true, the tournament remains visible on the owner's dashboard after finishing.")

    def save(self, *args, **kwargs):
        if not self.invitation_code:
            # Generamos un código aleatorio de 10 caracteres (puedes ajustar el largo)
            self.invitation_code = get_random_string(length=10).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TournamentRankingSnapshot(models.Model):
    """
    Stores the final ranking of a tournament when it is finished.
    This provides a historical record that won't change even if match scores are later updated.
    """
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='ranking_snapshots')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tournament_rankings')
    rank = models.PositiveIntegerField()
    points = models.IntegerField()
    exact_predictions = models.PositiveIntegerField(default=0, help_text="Predictions with 3 points (exact score)")
    partial_predictions = models.PositiveIntegerField(default=0, help_text="Predictions with 1 point (correct outcome)")
    total_predictions = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['tournament', 'rank']
        unique_together = ('tournament', 'user')

    def __str__(self):
        return f"#{self.rank} {self.user.username} — {self.points} pts ({self.tournament.name})"


class Team(models.Model):
    """
    Represents a football team (national or club).
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, blank=True, help_text="ISO country code for national teams")
    flag_url = models.URLField(blank=True)
    is_national = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def get_flag_url(self):
        if self.flag_url:
            return self.flag_url
        if self.code:
            return f"https://flagcdn.com/w80/{self.code.lower()}.png"
        return None

    def get_translated_name(self, language='en'):
        """Return the team name in the requested language, fallback to default name."""
        if language == 'en' or not language:
            return self.name
        try:
            translation = self.translations.get(language=language)
            return translation.name
        except TeamTranslation.DoesNotExist:
            return self.name

    def __str__(self):
        return self.name


class TeamTranslation(models.Model):
    """
    Stores translated names for teams.
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='translations')
    language = models.CharField(max_length=5, help_text="Language code, e.g. 'es', 'pt', 'fr'")
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('team', 'language')
        verbose_name = 'Team Translation'
        verbose_name_plural = 'Team Translations'

    def __str__(self):
        return f"{self.team.name} ({self.language}): {self.name}"

class Match(models.Model):
    """
    Represents a real football match.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('finished', 'Finished'),
    ]

    SOURCE_CHOICES = [
        ('pool', 'Pool'),
        ('custom', 'Custom'),
    ]

    home_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='home_matches',
    )
    away_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='away_matches',
    )
    match_date = models.DateTimeField()
    home_score_real = models.IntegerField(blank=True, null=True)
    away_score_real = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    stage = models.CharField(max_length=50, blank=True, null=True)
    tournaments = models.ManyToManyField(Tournament, related_name='matches')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='custom')
    template = models.ForeignKey(
        'PredefinedTournamentTemplate',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pool_matches'
    )

    class Meta:
        verbose_name_plural = "Matches"

    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name}"

class Prediction(models.Model):
    """
    A user's prediction for a specific match within a tournament.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='predictions')
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

class PredefinedTournamentTemplate(models.Model):
    """
    A reusable template of matches that can be added to user tournaments.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class TemplateMatch(models.Model):
    """
    A match within a predefined tournament template.
    """
    template = models.ForeignKey(PredefinedTournamentTemplate, on_delete=models.CASCADE, related_name='matches')
    home_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='template_home_matches',
    )
    away_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='template_away_matches',
    )
    match_date = models.DateTimeField()
    stage = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ['match_date']

    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name}"
