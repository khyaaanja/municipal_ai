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
        ref = f" ({n['reference_no']})" if n['reference_no'] else ''
        deadline = f" · deadline {n['deadline']}" if n['deadline'] else ''
        out.append(f"- **{n['title']}**{ref} — {n['type']}{deadline}")
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



def _draft_complaint(d):
    p = d['draft']
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


_RENDERERS = {
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
