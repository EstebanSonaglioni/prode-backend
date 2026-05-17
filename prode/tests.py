from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from .models import Tournament, Match, Prediction, Team
from .views import recalculate_points


class IdempotentPointsTests(TestCase):
    """Comprehensive tests for idempotent match finish and point recalculation."""

    def setUp(self):
        self.client = APIClient()
        self.superuser = User.objects.create_superuser('super', 'super@test.com', 'pass123')
        self.admin = User.objects.create_user('admin', 'admin@test.com', 'pass123')
        self.participant = User.objects.create_user('participant', 'part@test.com', 'pass123')
        self.other_user = User.objects.create_user('other', 'other@test.com', 'pass123')

        self.team_a = Team.objects.create(name='Team A', code='TA', is_national=True)
        self.team_b = Team.objects.create(name='Team B', code='TB', is_national=True)
        self.team_c = Team.objects.create(name='Team C', code='TC', is_national=True)
        self.team_d = Team.objects.create(name='Team D', code='TD', is_national=True)

        self.tournament = Tournament.objects.create(name='Test Cup', owner=self.admin)
        self.tournament.participants.add(self.admin, self.participant)

    def _create_custom_match(self, status='scheduled'):
        """Helper to create a custom match in the tournament."""
        match = Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            match_date='2026-06-01T18:00:00Z',
            status=status,
            source='custom',
        )
        match.tournaments.add(self.tournament)
        return match

    def _create_pool_match(self, status='scheduled'):
        """Helper to create a pool match."""
        match = Match.objects.create(
            home_team=self.team_c,
            away_team=self.team_d,
            match_date='2026-06-02T18:00:00Z',
            status=status,
            source='pool',
        )
        match.tournaments.add(self.tournament)
        return match

    def _create_prediction(self, match, user, home, away):
        return Prediction.objects.create(
            user=user,
            tournament=self.tournament,
            match=match,
            home_score_guess=home,
            away_score_guess=away,
        )

    def _login(self, user):
        resp = self.client.post('/api/users/login/', {
            'username': user.username,
            'password': 'pass123'
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + resp.data['access'])

    # ==========================================================================
    # recalculate_points() function tests
    # ==========================================================================

    def test_recalculate_exact_score(self):
        """Exact guess earns 3 points."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        pred = self._create_prediction(match, self.participant, 2, 1)
        self.assertEqual(pred.points_earned, 0)

        updated = recalculate_points(match)
        self.assertEqual(updated, 1)

        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 3)

    def test_recalculate_winner_only(self):
        """Correct winner only earns 1 point."""
        match = self._create_custom_match('finished')
        match.home_score_real = 3
        match.away_score_real = 1
        match.save()

        pred = self._create_prediction(match, self.participant, 2, 0)
        updated = recalculate_points(match)

        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 1)
        self.assertEqual(updated, 1)

    def test_recalculate_draw_both_guess_draw(self):
        """Both draw earns 1 point."""
        match = self._create_custom_match('finished')
        match.home_score_real = 1
        match.away_score_real = 1
        match.save()

        pred = self._create_prediction(match, self.participant, 2, 2)
        updated = recalculate_points(match)

        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 1)
        self.assertEqual(updated, 1)

    def test_recalculate_completely_wrong(self):
        """Wrong winner earns 0 points."""
        match = self._create_custom_match('finished')
        match.home_score_real = 0
        match.away_score_real = 2
        match.save()

        # Start with a non-zero value to verify the update is detected
        pred = Prediction.objects.create(
            user=self.participant,
            tournament=self.tournament,
            match=match,
            home_score_guess=2,
            away_score_guess=0,
            points_earned=99,
        )
        updated = recalculate_points(match)

        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 0)
        self.assertEqual(updated, 1)

    def test_recalculate_idempotent_same_scores(self):
        """Calling recalculate twice with same scores should update 0 on second call."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._create_prediction(match, self.participant, 2, 1)

        first = recalculate_points(match)
        self.assertEqual(first, 1)

        second = recalculate_points(match)
        self.assertEqual(second, 0)  # Already correct, no update needed

    def test_recalculate_multiple_predictions(self):
        """Multiple predictions get correct points independently."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        # All start with a wrong value to ensure updates are detected
        Prediction.objects.create(
            user=self.admin, tournament=self.tournament, match=match,
            home_score_guess=2, away_score_guess=1, points_earned=0,
        )  # -> 3 pts
        Prediction.objects.create(
            user=self.participant, tournament=self.tournament, match=match,
            home_score_guess=2, away_score_guess=0, points_earned=0,
        )  # -> 1 pt
        Prediction.objects.create(
            user=self.other_user, tournament=self.tournament, match=match,
            home_score_guess=1, away_score_guess=1, points_earned=99,
        )  # -> 0 pts

        updated = recalculate_points(match)
        self.assertEqual(updated, 3)

        preds = Prediction.objects.filter(match=match).order_by('user__username')
        self.assertEqual(preds[0].points_earned, 3)   # admin guessed exact
        self.assertEqual(preds[1].points_earned, 0)   # other_user guessed draw
        self.assertEqual(preds[2].points_earned, 1)   # participant guessed winner

    def test_recalculate_none_scores_returns_zero(self):
        """If scores are None, return 0 and don't crash."""
        match = self._create_custom_match('finished')
        match.home_score_real = None
        match.away_score_real = None
        match.save()

        self._create_prediction(match, self.participant, 2, 1)
        updated = recalculate_points(match)
        self.assertEqual(updated, 0)

    def test_recalculate_scores_changed_updates_all(self):
        """If scores change after initial calculation, recalculate updates predictions."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        pred = self._create_prediction(match, self.participant, 2, 1)
        recalculate_points(match)
        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 3)

        # Now change the real scores
        match.home_score_real = 0
        match.away_score_real = 0
        match.save()

        updated = recalculate_points(match)
        self.assertEqual(updated, 1)
        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 0)  # Was 3, now wrong

    # ==========================================================================
    # finish() action tests
    # ==========================================================================

    def test_finish_live_match(self):
        """Normal finish of a live match."""
        match = self._create_custom_match('live')
        self._login(self.admin)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('predictions_updated', resp.data)
        self.assertIn('match', resp.data)

        match.refresh_from_db()
        self.assertEqual(match.status, 'finished')
        self.assertEqual(match.home_score_real, 2)

    def test_finish_idempotent_same_scores(self):
        """Finishing an already-finished match with same scores is a no-op."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._create_prediction(match, self.participant, 2, 1)
        recalculate_points(match)

        self._login(self.admin)
        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['predictions_updated'], 0)

        # Ensure no duplicate points added
        pred = Prediction.objects.get(match=match, user=self.participant)
        self.assertEqual(pred.points_earned, 3)

    def test_finish_idempotent_changed_scores(self):
        """Finishing an already-finished match with different scores recalculates."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._create_prediction(match, self.participant, 2, 1)
        recalculate_points(match)

        self._login(self.admin)
        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 0,
            'away_score_real': 0,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['predictions_updated'], 1)

        pred = Prediction.objects.get(match=match, user=self.participant)
        self.assertEqual(pred.points_earned, 0)

    def test_finish_scheduled_match_fails(self):
        """Cannot finish a match that hasn't started."""
        match = self._create_custom_match('scheduled')
        self._login(self.admin)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finish_missing_scores(self):
        """Scores are required."""
        match = self._create_custom_match('live')
        self._login(self.admin)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ==========================================================================
    # Permissions tests for finish()
    # ==========================================================================

    def test_finish_custom_match_non_admin_forbidden(self):
        """Only tournament admin can finish custom matches."""
        match = self._create_custom_match('live')
        self._login(self.participant)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_finish_pool_match_non_superuser_forbidden(self):
        """Only superuser can finish pool matches."""
        match = self._create_pool_match('live')
        self._login(self.admin)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_finish_pool_match_superuser_allowed(self):
        """Superuser can finish pool matches."""
        match = self._create_pool_match('live')
        self._login(self.superuser)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ==========================================================================
    # recalculate() action tests
    # ==========================================================================

    def test_recalculate_action_custom_match(self):
        """Admin can force recalculate on a finished custom match."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._create_prediction(match, self.participant, 2, 1)
        recalculate_points(match)

        self._login(self.admin)
        resp = self.client.post(f'/api/prode/matches/{match.id}/recalculate/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['predictions_updated'], 0)

    def test_recalculate_action_pool_match(self):
        """Superuser can force recalculate on a finished pool match."""
        match = self._create_pool_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._create_prediction(match, self.participant, 2, 1)
        recalculate_points(match)

        self._login(self.superuser)
        resp = self.client.post(f'/api/prode/matches/{match.id}/recalculate/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_recalculate_action_not_finished_fails(self):
        """Cannot recalculate a match that isn't finished."""
        match = self._create_custom_match('live')
        self._login(self.admin)

        resp = self.client.post(f'/api/prode/matches/{match.id}/recalculate/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recalculate_action_custom_non_admin_forbidden(self):
        """Non-admin cannot recalculate custom matches."""
        match = self._create_custom_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._login(self.participant)
        resp = self.client.post(f'/api/prode/matches/{match.id}/recalculate/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_recalculate_action_pool_non_superuser_forbidden(self):
        """Non-superuser cannot recalculate pool matches."""
        match = self._create_pool_match('finished')
        match.home_score_real = 2
        match.away_score_real = 1
        match.save()

        self._login(self.admin)
        resp = self.client.post(f'/api/prode/matches/{match.id}/recalculate/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================================================
    # Edge case: multiple sequential finishes don't corrupt points
    # ==========================================================================

    def test_triple_finish_same_scores_no_corruption(self):
        """Calling finish 3 times with same scores must not change points."""
        match = self._create_custom_match('live')
        self._create_prediction(match, self.participant, 2, 1)

        self._login(self.admin)
        for _ in range(3):
            resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
                'home_score_real': 2,
                'away_score_real': 1,
            }, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        pred = Prediction.objects.get(match=match, user=self.participant)
        self.assertEqual(pred.points_earned, 3)

    def test_finish_then_recalculate_no_corruption(self):
        """Finish then recalculate must keep same points."""
        match = self._create_custom_match('live')
        self._create_prediction(match, self.participant, 2, 1)

        self._login(self.admin)

        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['predictions_updated'], 1)

        resp = self.client.post(f'/api/prode/matches/{match.id}/recalculate/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['predictions_updated'], 0)

        pred = Prediction.objects.get(match=match, user=self.participant)
        self.assertEqual(pred.points_earned, 3)

    def test_score_correction_then_recalculate_updates_correctly(self):
        """Admin corrects score, finish with new score, points update correctly."""
        match = self._create_custom_match('live')
        self._create_prediction(match, self.participant, 1, 1)  # guessed draw

        self._login(self.admin)

        # First finish: real result was 2-1 (participant guessed wrong)
        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 2,
            'away_score_real': 1,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        pred = Prediction.objects.get(match=match, user=self.participant)
        self.assertEqual(pred.points_earned, 0)

        # Oops, score was actually 1-1 (participant guessed right!)
        resp = self.client.post(f'/api/prode/matches/{match.id}/finish/', {
            'home_score_real': 1,
            'away_score_real': 1,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['predictions_updated'], 1)

        pred.refresh_from_db()
        self.assertEqual(pred.points_earned, 3)
