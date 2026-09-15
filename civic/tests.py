from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from .models import (Proposal, ProposalSupport, WardMeeting, MeetingRSVP,
                     MeetingQuestion, CivicPoll, PollOption, PollVote,
                     Petition, PetitionSignature)
from django.utils import timezone
import json

User = get_user_model()


def make_citizen(tag, ward=3):
    return User.objects.create_user(f'{tag}@test.com', password='testpass123',
                                    username=tag, ward_number=ward, role='citizen')


def make_chairperson(tag, ward=3):
    return User.objects.create_user(f'{tag}@test.com', password='testpass123',
                                    username=tag, ward_number=ward, role='chairperson')


class ProposalTests(TestCase):
    def setUp(self):
        self.citizen = make_citizen('prop_citizen')
        self.chair = make_chairperson('prop_chair')
        self.client = Client()

    def test_submit_requires_login(self):
        r = self.client.post('/civic/proposals/submit/', {'title': 'Test', 'description': 'Desc', 'category': 'OTHER'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])

    def test_valid_post_creates_proposal(self):
        self.client.login(email='prop_citizen@test.com', password='testpass123')
        self.client.post('/civic/proposals/submit/', {
            'category': 'INFRASTRUCTURE',
            'title': 'Fix the Road',
            'description': 'The road is damaged.',
            'expected_benefit': 'Better commute',
        })
        self.assertEqual(Proposal.objects.count(), 1)
        p = Proposal.objects.first()
        self.assertEqual(p.title, 'Fix the Road')
        self.assertEqual(p.ward_number, 3)

    def test_support_toggle_increments_count(self):
        self.client.login(email='prop_citizen@test.com', password='testpass123')
        p = Proposal.objects.create(ward_number=3, submitted_by=self.citizen,
                                    category='OTHER', title='T', description='D')
        r = self.client.post(f'/civic/proposals/{p.pk}/support/')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data['supported'])
        self.assertEqual(data['count'], 1)

    def test_chairperson_cannot_see_other_ward(self):
        other_citizen = make_citizen('other_cit', ward=5)
        p = Proposal.objects.create(ward_number=5, submitted_by=other_citizen,
                                    category='OTHER', title='Other Ward', description='D')
        self.client.login(email='prop_chair@test.com', password='testpass123')
        r = self.client.get(f'/civic/manage/proposals/{p.pk}/')
        self.assertEqual(r.status_code, 403)


class MeetingTests(TestCase):
    def setUp(self):
        self.citizen = make_citizen('meet_citizen')
        self.chair = make_chairperson('meet_chair')
        self.meeting = WardMeeting.objects.create(
            ward_number=3, title='Test Meeting',
            venue='Ward Office', meeting_date=timezone.now() + timezone.timedelta(days=7),
        )
        self.client = Client()

    def test_rsvp_requires_login(self):
        r = self.client.post(f'/civic/meetings/{self.meeting.pk}/rsvp/')
        self.assertIn(r.status_code, [302, 403])

    def test_rsvp_creates_record(self):
        self.client.login(email='meet_citizen@test.com', password='testpass123')
        r = self.client.post(f'/civic/meetings/{self.meeting.pk}/rsvp/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MeetingRSVP.objects.count(), 1)

    def test_max_rsvp_enforced(self):
        self.meeting.max_rsvp = 1
        self.meeting.save()
        other_citizen = make_citizen('other_meet', ward=3)
        self.client.login(email='meet_citizen@test.com', password='testpass123')
        self.client.post(f'/civic/meetings/{self.meeting.pk}/rsvp/')
        self.client.login(email='other_meet@test.com', password='testpass123')
        r = self.client.post(f'/civic/meetings/{self.meeting.pk}/rsvp/')
        self.assertEqual(r.status_code, 400)

    def test_one_question_per_citizen(self):
        self.client.login(email='meet_citizen@test.com', password='testpass123')
        self.client.post(f'/civic/meetings/{self.meeting.pk}/question/', {'question': 'First question?'})
        r = self.client.post(f'/civic/meetings/{self.meeting.pk}/question/', {'question': 'Second question?'})
        self.assertEqual(r.status_code, 400)


class PollTests(TestCase):
    def setUp(self):
        self.citizen = make_citizen('poll_citizen')
        self.poll = CivicPoll.objects.create(question='Best park?', status='ACTIVE')
        self.opt_a = PollOption.objects.create(poll=self.poll, text='Park A', order=0)
        self.opt_b = PollOption.objects.create(poll=self.poll, text='Park B', order=1)
        self.client = Client()

    def test_one_vote_per_citizen(self):
        self.client.login(email='poll_citizen@test.com', password='testpass123')
        self.client.post(f'/civic/polls/{self.poll.pk}/vote/', {'option_id': self.opt_a.pk})
        r = self.client.post(f'/civic/polls/{self.poll.pk}/vote/', {'option_id': self.opt_b.pk})
        self.assertEqual(r.status_code, 400)

    def test_vote_increments_option_count(self):
        self.client.login(email='poll_citizen@test.com', password='testpass123')
        self.client.post(f'/civic/polls/{self.poll.pk}/vote/', {'option_id': self.opt_a.pk})
        self.opt_a.refresh_from_db()
        self.assertEqual(self.opt_a.vote_count, 1)

    def test_closed_poll_rejects_vote(self):
        self.poll.status = 'CLOSED'
        self.poll.save()
        self.client.login(email='poll_citizen@test.com', password='testpass123')
        r = self.client.post(f'/civic/polls/{self.poll.pk}/vote/', {'option_id': self.opt_a.pk})
        self.assertEqual(r.status_code, 404)


class PetitionTests(TestCase):
    def setUp(self):
        self.citizen = make_citizen('pet_citizen')
        self.petition = Petition.objects.create(
            ward_number=3, created_by=self.citizen,
            title='Fix Park', body='Fix the park.', target='Ward Chair',
        )
        self.client = Client()

    def test_sign_open_petition(self):
        other = make_citizen('pet_signer', ward=3)
        self.client.login(email='pet_signer@test.com', password='testpass123')
        r = self.client.post(f'/civic/petitions/{self.petition.pk}/sign/')
        self.assertEqual(r.status_code, 200)
        self.petition.refresh_from_db()
        self.assertEqual(self.petition.signature_count, 1)

    def test_cannot_sign_closed_petition(self):
        self.petition.status = 'CLOSED'
        self.petition.save()
        self.client.login(email='pet_citizen@test.com', password='testpass123')
        r = self.client.post(f'/civic/petitions/{self.petition.pk}/sign/')
        self.assertEqual(r.status_code, 400)

    def test_create_requires_login(self):
        r = self.client.post('/civic/petitions/start/', {
            'title': 'T', 'body': 'B', 'target': 'Mayor', 'goal_signatures': 100,
        })
        self.assertIn('/login/', r['Location'])
