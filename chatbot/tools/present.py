"""Render tool results as chat replies.

Rendering is deterministic and never routes tool output back through the
model. Retrieved text cannot be read as an instruction if no model reads
it, so this is also where §28 is strongest.
"""

EMPTY = {
    'find_on_map': "I couldn't find that place on the map.",
    'get_my_complaints': "You haven't filed any complaints yet. If you filed one "
                         "without an account, give me its **BK-XXXXXX** reference "
                         "and I can look it up.",
    'get_my_service_requests': "You don't have any service applications yet.",
    'get_my_proposals': "You haven't submitted any proposals yet.",
    'get_my_notifications': "You have no notifications right now.",
    'list_events': "I don't have any upcoming events listed at the moment.",
    'list_public_notices': "There are no active public notices right now.",
    'find_businesses': "I couldn't find any businesses matching that.",
    'find_attractions': "I couldn't find any attractions matching that.",
}

FOLLOWUPS = {
    'search_municipal_knowledge': ['Tell me more', 'Who do I contact?'],
    'find_on_map': ['Show nearby restaurants', 'What else is close by?'],
    'mark_notifications_read': ['Show my complaints', 'Show my applications'],
    'draft_service_request': ['Yes, submit it', 'Change the details'],
    'confirm_service_request': ['Track my applications', 'Apply for another service'],
    'draft_proposal': ['Yes, submit it', 'Reword the proposal'],
    'confirm_proposal': ['Show my proposals', 'How are proposals reviewed?'],
    'draft_complaint': ['Yes, file it', 'Change the description'],
    'confirm_complaint': ['Track this complaint', 'File another issue'],
    'get_complaint_status': ['How do I escalate this?', 'File another complaint'],
    'get_my_complaints': ['How do I file a new complaint?', 'Track a complaint by reference'],
    'get_my_service_requests': ['What documents do I need?', 'Apply for a service'],
    'get_my_proposals': ['How are proposals reviewed?', 'Submit a proposal'],
    'get_my_notifications': ['Show my complaints', 'Show my applications'],
    'list_events': ['What festivals are coming?', 'Show me attractions'],
    'list_public_notices': ['Show tenders only', 'Show job vacancies'],
    'find_businesses': ['Show restaurants', 'Show hotels'],
    'find_attractions': ['What are the opening hours?', 'Show nearby restaurants'],
}


def present(name, result):
    """Return (reply_text, followups). reply_text is None to fall through."""
    if not result.ok:
        return result.error, []

    data = result.data
    if isinstance(data, list) and not data:
        return EMPTY.get(name, "I couldn't find anything for that."), FOLLOWUPS.get(name, [])

    renderer = _RENDERERS.get(name)
    if renderer is None:
        return None, []
    return renderer(data), FOLLOWUPS.get(name, [])


def _complaint_status(d):
    lines = [
        f"**Complaint {d['complaint_id']}**",
        '',
        f"**Status:** {d['status']}",
        f"**Category:** {d['category']}",
        f"**Title:** {d['title']}",
    ]
    if d.get('ward_number'):
        lines.append(f"**Ward:** {d['ward_number']}")
    if d.get('submitter_phone') or d.get('submitter_email'):
        lines.append('')
        lines.append('_Contact details on file:_ '
                     f"{d.get('submitter_phone') or ''} {d.get('submitter_email') or ''}".strip())
    lines += ['', f"[Track full details](/complaint/status/{d['complaint_id']}/)"]
    return '\n'.join(lines)


def _my_complaints(rows):
    out = [f"You have **{len(rows)}** complaint(s):", '']
    for c in rows:
        out.append(f"- **{c['complaint_id']}** — {c['title']} · _{c['status']}_")
    out += ['', '[View all your complaints](/complaint/my/)']
    return '\n'.join(out)


def _my_service_requests(rows):
    out = [f"You have **{len(rows)}** application(s):", '']
    for s in rows:
        fee = ''
        if s.get('fee_amount'):
            fee = f" · fee Rs {s['fee_amount']}" + ('' if s['fee_paid'] else ' (unpaid)')
        out.append(f"- **{s['reference_number']}** — {s['service_type']} · _{s['status']}_{fee}")
    out += ['', '[View all your applications](/services/my/)']
    return '\n'.join(out)


def _my_proposals(rows):
    out = [f"You have **{len(rows)}** proposal(s):", '']
    for p in rows:
        out.append(f"- **{p['title']}** — {p['category']} · _{p['status']}_ "
                   f"· {p['support_count']} support")
    return '\n'.join(out)


def _my_notifications(rows):
    out = [f"You have **{len(rows)}** notification(s):", '']
    for n in rows:
        mark = '' if n['is_read'] else '**new** · '
        out.append(f"- {mark}{n['message']}")
    return '\n'.join(out)


def _events(rows):
    out = ['**Upcoming events**', '']
    for e in rows:
        when = e['starts'][:10]
        fee = 'Free' if e['is_free'] else (f"Rs {e['entry_fee']}" if e['entry_fee'] else '')
        venue = f" · {e['venue']}" if e['venue'] else ''
        out.append(f"- **{e['name']}** — {when}{venue}{' · ' + fee if fee else ''}")
    return '\n'.join(out)


def _notices(rows):
    out = ['**Public notices**', '']
    for n in rows:
        ref = f" ({n['reference_no']})" if n.get('reference_no') else ''
        deadline = f" · deadline {n['deadline']}" if n['deadline'] else ''
        title = (f"[{n['title']}]({n['source_url']})" if n.get('source_url')
                 else f"**{n['title']}**")
        out.append(f"- {title}{ref} — {n['type']}{deadline}")
    out += ['', '[All notices](/services/notices/)']
    return '\n'.join(out)


def _businesses(rows):
    out = ['**Local businesses**', '']
    for b in rows:
        rating = f" · {b['rating']:.1f}★" if b.get('rating') else ''
        addr = f" — {b['address']}" if b['address'] else ''
        out.append(f"- **{b['name']}** ({b['category']}){addr}{rating}")
    return '\n'.join(out)


def _attractions(rows):
    out = ['**Places to visit**', '']
    for a in rows:
        fee = 'Free entry' if a['is_free'] else (f"Rs {a['entry_fee']}" if a['entry_fee'] else '')
        hours = f" · {a['opening_hours']}" if a['opening_hours'] else ''
        cat = f" ({a['category']})" if a['category'] else ''
        out.append(f"- **{a['name']}**{cat}{hours}{' · ' + fee if fee else ''}")
    return '\n'.join(out)



# A citizen who described the problem in Nepali was shown the draft, and the
# confirmation, entirely in English. The description is the citizen's own
# words, so it decides the language of the reply.
STATUS_NE = {
    'Pending': 'प्रक्रियामा',
    'In Progress': 'काम भइरहेको',
    'Resolved': 'समाधान भएको',
    'Rejected': 'अस्वीकृत',
    'Closed': 'बन्द',
}


def _draft_complaint(d):
    from chatbot.tools.flow import CATEGORY_NE
    from chatbot.tools.retrieval import _is_devanagari

    p = d['draft']
    ne = _is_devanagari(p.get('description', ''))
    if ne:
        label = CATEGORY_NE.get(p['category'].upper(), p['category'].title())
        lines = [
            'यो उजुरी दर्ता गर्न लागेको छु। पठाउनु अघि एकपटक हेर्नुहोस्:',
            '',
            f"**विषय:** {label}",
            f"**शीर्षक:** {p['title']}",
            f"**स्थान:** {p['location']}",
        ]
        if p.get('ward_number'):
            lines.append(f"**वडा:** {p['ward_number']}")
        lines += [
            f"**उजुरीकर्ता:** {p['submitter_name']}",
            '',
            f"**विवरण:** {p['description']}",
            '',
            '**अहिलेसम्म केही पनि दर्ता भएको छैन।** पठाउन **हो** '
            'लेख्नुहोस्, वा के फेर्ने हो भन्नुहोस्।',
        ]
        return '\n'.join(lines)
    lines = [
        "Here's the complaint I'll file. Please check it before I send it:",
        '',
        f"**Category:** {p['category'].title()}",
        f"**Title:** {p['title']}",
        f"**Location:** {p['location']}",
    ]
    if p.get('ward_number'):
        lines.append(f"**Ward:** {p['ward_number']}")
    lines += [
        f"**Reported by:** {p['submitter_name']}",
        '',
        f"**Description:** {p['description']}",
        '',
        '**Nothing has been filed yet.** Reply **yes** to submit this, '
        'or tell me what to change.',
    ]
    return '\n'.join(lines)


def _confirm_complaint(d):
    if d.get('ne'):
        status = STATUS_NE.get(d['status'], d['status'])
        lines = [
            f"दर्ता भयो। तपाईंको सन्दर्भ नम्बर **{d['complaint_id']}** हो।",
            '',
            f"**अवस्था:** {status}",
            '',
            f"[यहाँबाट हेर्नुहोस्](/complaint/status/{d['complaint_id']}/)",
        ]
        if d.get('photos_attached'):
            lines.insert(3, f"**संलग्न फोटो:** {d['photos_attached']}")
        if d.get('claim_token'):
            lines += [
                '',
                '_यो लिङ्क सुरक्षित राख्नुहोस् — खाता नबनाई यही उजुरीमा '
                'फर्कने बाटो यही हो।_',
            ]
        return '\n'.join(lines)
    lines = [
        f"Filed. Your reference is **{d['complaint_id']}**.",
        '',
        f"**Status:** {d['status']}",
        '',
        f"[Track it here](/complaint/status/{d['complaint_id']}/)",
    ]
    if d.get('photos_attached'):
        lines.insert(3, f"**Photos attached:** {d['photos_attached']}")
    if d.get('claim_token'):
        lines += [
            '',
            '_Save this link — it is how you reach this complaint again '
            'without an account._',
        ]
    return '\n'.join(lines)



def _draft_service_request(d):
    p = d['draft']
    return '\n'.join([
        "Here's the application I'll submit. Please check it first:",
        '',
        f"**Service:** {p['service_type'].replace('_', ' ').title()}",
        f"**Ward:** {p['ward_number']}",
        f"**Applicant:** {p['applicant_name']}",
        f"**Phone:** {p['applicant_phone']}",
        f"**Address:** {p['applicant_address']}",
        '',
        f"**Details:** {p['details']}",
        '',
        '**Nothing has been submitted yet.** Reply **yes** to send it, '
        'or tell me what to change.',
    ])


def _confirm_service_request(d):
    lines = [
        f"Submitted. Your reference is **{d['reference_number']}**.",
        '',
        f"**Service:** {d['service_type']}",
        f"**Status:** {d['status']}",
    ]
    if d.get('fee_amount'):
        lines.append(f"**Fee:** Rs {d['fee_amount']}")
    lines += ['', '[View your applications](/services/my/)']
    return '\n'.join(lines)


def _draft_proposal(d):
    p = d['draft']
    lines = [
        "Here's your proposal as I've written it up:",
        '',
        f"**Title:** {p['title']}",
        f"**Category:** {p['category'].title()}",
        f"**Ward:** {p['ward_number']}",
        '',
        f"**Description:** {p['description']}",
    ]
    if p.get('expected_benefit'):
        lines += ['', f"**Expected benefit:** {p['expected_benefit']}"]
    lines += [
        '',
        '**Nothing has been submitted yet.** Reply **yes** to send it to your '
        'ward, or tell me what to change.',
    ]
    return '\n'.join(lines)


def _confirm_proposal(d):
    return '\n'.join([
        f"Submitted to Ward {d['ward_number']}.",
        '',
        f"**{d['title']}**",
        f"**Category:** {d['category']}",
        f"**Status:** {d['status']}",
    ])



def _on_map(rows):
    out = ['**Locations**', '']
    for r in rows:
        out.append(f"- **{r['name']}** ({r['kind']}) — {r['address'] or 'Bhaktapur'} "
                   f"· [map](https://www.openstreetmap.org/?mlat={r['latitude']}&mlon={r['longitude']}#map=18/{r['latitude']}/{r['longitude']})")
    return '\n'.join(out)


def _marked_read(d):
    n = d['marked_read']
    if not n:
        return 'You had no unread notifications.'
    return f"Marked **{n}** notification(s) as read."



def _knowledge(d):
    out = []
    # Asked in English, answered from a Nepali document: say so up front. The
    # text itself is left untranslated on purpose — these are fees and legal
    # requirements, and a machine translation that drifts is worse than script
    # the reader can copy to someone who reads it.
    if d.get('answer_in_devanagari') and not d.get('asked_in_devanagari'):
        out += ['_This answer is quoted from the municipality\'s official '
                'Nepali-language records, unchanged._', '']
    for p in d['passages'][:3]:
        out.append(f"**{p['title']}**")
        out.append(p['text'])
        out.append('')
    if d.get('confidence') == 'medium':
        out.append('_This is the closest match in the municipal records — '
                   'check with the ward office if you need certainty._')
    return '\n'.join(out).strip()


_RENDERERS = {
    'search_municipal_knowledge': _knowledge,
    'find_on_map': _on_map,
    'mark_notifications_read': _marked_read,
    'draft_service_request': _draft_service_request,
    'confirm_service_request': _confirm_service_request,
    'draft_proposal': _draft_proposal,
    'confirm_proposal': _confirm_proposal,
    'draft_complaint': _draft_complaint,
    'confirm_complaint': _confirm_complaint,
    'get_complaint_status': _complaint_status,
    'get_my_complaints': _my_complaints,
    'get_my_service_requests': _my_service_requests,
    'get_my_proposals': _my_proposals,
    'get_my_notifications': _my_notifications,
    'list_events': _events,
    'list_public_notices': _notices,
    'find_businesses': _businesses,
    'find_attractions': _attractions,
}
