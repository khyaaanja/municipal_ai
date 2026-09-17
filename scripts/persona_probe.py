"""Ask the assistant what a real user would ask, and record what comes back.

Probing `search()` alone measures the wrong thing. It counts a miss when the
router was always going to answer -- "my street light is broken" opens a
complaint and retrieves nothing -- and counts a hit when a query merely
shares a word, as "do I need a guide" did against "Newari Cuisine Guide".

This goes through the same path a citizen's message takes: the tool router
first, then knowledge, then the no-answer reply.
"""
import os
import pathlib
import sys

import django

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'municipal_ai.settings')
django.setup()

from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from chatbot.tools.flow import handle  # noqa: E402
from chatbot.services.answer_engine import NO_INFO_MESSAGE  # noqa: E402

TOOL, KNOWLEDGE, NOTHING = 'tool', 'knowledge', 'none'


def _request():
    req = RequestFactory().post('/api/chat/')
    req.session = SessionStore()
    req.user = type('Anon', (), {'is_authenticated': False, 'pk': None})()
    return req


def ask(question):
    """Return (outcome, intent, reply) for one question."""
    result = handle(_request(), question)
    if result is None:
        return NOTHING, 'fell_through_to_model', ''
    reply, _followups, intent = result
    if reply.strip() == NO_INFO_MESSAGE.strip():
        return NOTHING, intent, reply
    return (TOOL if intent and intent != 'knowledge' else KNOWLEDGE), intent, reply


def run(label, questions):
    print(f'--- {label} ---')
    counts = {TOOL: 0, KNOWLEDGE: 0, NOTHING: 0}
    gaps = []
    for question in questions:
        outcome, intent, reply = ask(question)
        counts[outcome] += 1
        if outcome == NOTHING:
            gaps.append(question)
        first = ' '.join(reply.split())[:52]
        print(f'  {outcome:9} {question[:38]:40} {intent[:18]:20} {first}')
    print(f'  => tool={counts[TOOL]} knowledge={counts[KNOWLEDGE]} '
          f'nothing={counts[NOTHING]}\n')
    return gaps


if __name__ == '__main__':
    from persona_questions import PERSONAS
    all_gaps = {}
    for name, questions in PERSONAS.items():
        all_gaps[name] = run(name, questions)
    print('=== unanswered ===')
    for name, gaps in all_gaps.items():
        if gaps:
            print(f'  {name}:')
            for gap in gaps:
                print(f'    {gap}')
