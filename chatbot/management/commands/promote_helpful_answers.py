"""Promote answers citizens marked helpful into the fallback store.

The assistant's free Groq tier allows 8,000 tokens a minute, which a handful
of simultaneous citizens exhausts. When it runs out the tool layer still
answers from municipal records, but open-ended questions — itineraries,
explanations — have nothing behind them.

This fills that gap from the one signal that reflects real usefulness: the
👍 button. An answer a citizen found helpful is worth keeping; the model's
own confidence is not evidence of anything.

Promoted answers are stored as FAQEntry with a marker, and are always served
as previously-generated text, never as municipal record. A generated answer
that enters the same store as the charter is how the knowledge base ended up
two-thirds written by the assistant citing itself.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

LEARNED_MARKER = '[learned]'
MIN_ANSWER_CHARS = 80
MAX_ANSWER_CHARS = 4000

# Never promote an answer that was itself a refusal or an error.
REFUSAL_MARKERS = (
    "don't have confident information", 'जानकारी उपलब्ध छैन', "couldn't",
    'could not', 'try again', '⚠️', 'rate limit', 'signed in',
)


# Devanagari carries more meaning per character than Latin: कर is two
# characters and means tax, while a two-letter Latin word is almost always
# filler. So the minimum word length differs by script.
LATIN_WORD = re.compile(r'[0-9A-Za-z]{3,}')
DEVANAGARI_WORD = re.compile(r'[\u0900-\u097F]{2,}')


def keywords_of(question):
    text = (question or '').lower()
    words = LATIN_WORD.findall(text) + DEVANAGARI_WORD.findall(text)
    return sorted(set(words))[:12]


def is_promotable(question, answer):
    if not question or not answer:
        return False, 'empty'
    if len(answer) < MIN_ANSWER_CHARS:
        return False, 'too short'
    if len(answer) > MAX_ANSWER_CHARS:
        return False, 'too long'
    lowered = answer.lower()
    if any(m.lower() in lowered for m in REFUSAL_MARKERS):
        return False, 'refusal or error'
    return True, ''


class Command(BaseCommand):
    help = 'Turn thumbs-up answers into fallback FAQ entries.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--min-votes', type=int, default=1,
                            help='Helpful votes required before promoting.')

    def handle(self, *args, **options):
        from django.db.models import Count

        from chatbot.models import FAQEntry, Message, ResponseFeedback

        helpful = (ResponseFeedback.objects
                   .filter(rating=ResponseFeedback.HELPFUL)
                   .values('message')
                   .annotate(votes=Count('id'))
                   .filter(votes__gte=options['min_votes']))

        if not helpful:
            self.stdout.write(self.style.WARNING(
                'No answers have been marked helpful yet — nothing to promote. '
                'The 👍 button in the chat feeds this.'))
            return

        promoted = skipped = 0
        with transaction.atomic():
            for row in helpful:
                answer_msg = Message.objects.filter(pk=row['message']).first()
                if answer_msg is None:
                    continue
                # The question is the citizen's message immediately before it.
                question_msg = (Message.objects
                                .filter(conversation=answer_msg.conversation,
                                        role=Message.ROLE_USER,
                                        created_at__lt=answer_msg.created_at)
                                .order_by('-created_at').first())
                if question_msg is None:
                    skipped += 1
                    continue

                question = question_msg.content.strip()
                answer = answer_msg.content.strip()
                ok, why = is_promotable(question, answer)
                if not ok:
                    skipped += 1
                    if options['dry_run']:
                        self.stdout.write(f'  skip ({why}): {question[:56]}')
                    continue

                if options['dry_run']:
                    self.stdout.write(f'  promote: {question[:64]}')
                    promoted += 1
                    continue

                _, created = FAQEntry.objects.update_or_create(
                    question=question[:500],
                    defaults={
                        'answer': f'{LEARNED_MARKER} {answer}',
                        'keywords': keywords_of(question),
                        'category': 'general',
                        'is_active': True,
                    },
                )
                promoted += created

        verb = 'would promote' if options['dry_run'] else 'promoted'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {promoted}, skipped {skipped}'))
