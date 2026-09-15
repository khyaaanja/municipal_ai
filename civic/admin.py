from django.contrib import admin
from .models import (Proposal, ProposalSupport, WardMeeting, MeetingRSVP,
                     MeetingQuestion, CivicPoll, PollOption, PollVote,
                     Petition, PetitionSignature)

admin.site.register(Proposal)
admin.site.register(WardMeeting)
admin.site.register(CivicPoll)
admin.site.register(Petition)
