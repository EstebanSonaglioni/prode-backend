from django.db import migrations, models
import django.db.models.deletion


def migrate_teams(apps, schema_editor):
    """Create Team records from existing match team names and link them."""
    Team = apps.get_model('prode', 'Team')
    Match = apps.get_model('prode', 'Match')
    TemplateMatch = apps.get_model('prode', 'TemplateMatch')

    # Collect all unique team names from existing matches and template matches
    team_names = set()
    for match in Match.objects.all():
        if match.home_team:
            team_names.add(match.home_team)
        if match.away_team:
            team_names.add(match.away_team)
    for tm in TemplateMatch.objects.all():
        if tm.home_team:
            team_names.add(tm.home_team)
        if tm.away_team:
            team_names.add(tm.away_team)

    # Create Team objects for each unique name
    team_map = {}
    for name in team_names:
        if name:
            team, _ = Team.objects.get_or_create(name=name)
            team_map[name] = team

    # Link Match records
    for match in Match.objects.all():
        updated = False
        if match.home_team in team_map:
            match.home_team_fk = team_map[match.home_team]
            updated = True
        if match.away_team in team_map:
            match.away_team_fk = team_map[match.away_team]
            updated = True
        if updated:
            match.save(update_fields=['home_team_fk', 'away_team_fk'])

    # Link TemplateMatch records
    for tm in TemplateMatch.objects.all():
        updated = False
        if tm.home_team in team_map:
            tm.home_team_fk = team_map[tm.home_team]
            updated = True
        if tm.away_team in team_map:
            tm.away_team_fk = team_map[tm.away_team]
            updated = True
        if updated:
            tm.save(update_fields=['home_team_fk', 'away_team_fk'])


def reverse_migrate(apps, schema_editor):
    """Reverse is not safely supported for this data migration."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('prode', '0005_match_template'),
    ]

    operations = [
        # 1. Add new fields to Team
        migrations.AddField(
            model_name='team',
            name='code',
            field=models.CharField(max_length=10, blank=True),
        ),
        migrations.AddField(
            model_name='team',
            name='is_national',
            field=models.BooleanField(default=False),
        ),

        # 2. Add temporary FK fields to Match
        migrations.AddField(
            model_name='match',
            name='home_team_fk',
            field=models.ForeignKey(
                to='prode.Team',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='home_matches',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='match',
            name='away_team_fk',
            field=models.ForeignKey(
                to='prode.Team',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='away_matches',
                null=True,
            ),
        ),

        # 3. Add temporary FK fields to TemplateMatch
        migrations.AddField(
            model_name='templatematch',
            name='home_team_fk',
            field=models.ForeignKey(
                to='prode.Team',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='template_home_matches',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='templatematch',
            name='away_team_fk',
            field=models.ForeignKey(
                to='prode.Team',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='template_away_matches',
                null=True,
            ),
        ),

        # 4. Migrate data from CharFields to FKs
        migrations.RunPython(migrate_teams, reverse_migrate),

        # 5. Remove old CharFields
        migrations.RemoveField(
            model_name='match',
            name='home_team',
        ),
        migrations.RemoveField(
            model_name='match',
            name='away_team',
        ),
        migrations.RemoveField(
            model_name='templatematch',
            name='home_team',
        ),
        migrations.RemoveField(
            model_name='templatematch',
            name='away_team',
        ),

        # 6. Rename FK fields to the original names
        migrations.RenameField(
            model_name='match',
            old_name='home_team_fk',
            new_name='home_team',
        ),
        migrations.RenameField(
            model_name='match',
            old_name='away_team_fk',
            new_name='away_team',
        ),
        migrations.RenameField(
            model_name='templatematch',
            old_name='home_team_fk',
            new_name='home_team',
        ),
        migrations.RenameField(
            model_name='templatematch',
            old_name='away_team_fk',
            new_name='away_team',
        ),
    ]
