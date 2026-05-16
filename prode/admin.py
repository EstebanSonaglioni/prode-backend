from django.contrib import admin
from .models import Tournament, Match, Prediction, Team, PredefinedTournamentTemplate, TemplateMatch

admin.site.register(Tournament)
admin.site.register(Match)
admin.site.register(Prediction)
admin.site.register(Team)
admin.site.register(PredefinedTournamentTemplate)
admin.site.register(TemplateMatch)
