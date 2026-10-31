#!/usr/bin/env python3
"""Layer 4 of the QA run: knowledge-base gap check.

A gap is NOT a bug. The chat endpoint can return 200 with a real model call and
still leave a citizen with nothing usable, because the municipal knowledge base
has no material on what they asked. The fix for that is data, not code, so gaps
are counted and drafted separately from test failures.

What counts as a gap here:
  * an empty answer
  * an answer shorter than MIN_WORDS (the keyword-fallback signature)
  * an answer that only deflects ("contact the municipality") without giving
    any concrete detail — no number, no document name, no time, no place

What does NOT count:
  * a 429. That is a spent quota, not a gap. It is reported as "unchecked" and
    the run says so rather than quietly scoring it as clean.

Outputs:
  log/kb_gaps.txt        one stable gap id per line (machine-readable)
  log/kb_drafts/*.md     one draft per gap, for a human to fill in and review
Exit codes:
  0  the check ran (gaps may or may not have been found)
  3  infrastructure: the app was not reachable, so nothing was checked
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("MUNICIPAL_AI_BASE_URL", "http://localhost:8000").rstrip("/")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAPS_FILE = os.path.join(REPO, "log", "kb_gaps.txt")
DRAFTS_DIR = os.path.join(REPO, "log", "kb_drafts")

MIN_WORDS = 15

# Questions a citizen actually arrives with. Each id is stable so the outer loop
# can tell a new gap from one that was already known.
QUESTIONS = [
    ("birth-certificate",  "What documents do I need to get a birth certificate in Bhaktapur?"),
    ("business-register",  "How do I register a new business in Bhaktapur municipality?"),
    ("office-hours",       "What are the Bhaktapur municipality office hours?"),
    ("property-tax",       "How much is property tax in Bhaktapur and how do I pay it?"),
    ("garbage-complaint",  "How do I file a complaint about garbage not being collected?"),
    ("building-permit",    "What is the process to get a building permit in Bhaktapur?"),
    ("marriage-cert",      "How do I get a marriage certificate registered in Bhaktapur?"),
    ("durbar-entry-fee",   "What is the entry fee for Bhaktapur Durbar Square?"),
    ("track-complaint",    "How do I check the status of a complaint I already filed?"),
    ("social-security",    "How do I apply for the social security allowance for elderly citizens?"),
    ("bisket-jatra",       "When is Bisket Jatra and what happens during it?"),
    ("citizenship-np",     "नागरिकता प्रमाणपत्र बनाउन के के कागजात चाहिन्छ?"),
]

# Phrases that mean "the knowledge base had nothing for this".
DEFLECTIONS = [
    "i don't have", "i do not have", "i'm not sure", "i am not sure",
    "no information", "not available in", "cannot find", "can't find",
    "unable to find", "sorry, i", "मसँग जानकारी छैन",
]

# The app's own no-answer fallback, in both languages. When this fires the
# knowledge base had nothing, full stop — no amount of contact detail in the
# message changes that, so it is a gap regardless of what else it contains.
NO_ANSWER_FALLBACK = [
    "don't have confident information",
    "do not have confident information",
    "जानकारी उपलब्ध छैन",
]

# Phone numbers are contact boilerplate, not an answer to anything. They get
# stripped before the "is there anything concrete here?" test, or every
# deflection that ends with the municipality switchboard scores as concrete.
PHONE = re.compile(r"\+?\d[\d\-\s()]{6,}\d")

# Something concrete: a figure, a fee, a count, a date, a time.
# Deliberately NOT words like "office", "document" or "certificate" — a
# deflection ("please contact the municipality office") contains those, so
# including them let every deflection score as concrete and nothing was ever
# flagged. A real procedural answer carries a number: a fee, a ward, a count
# of documents, a deadline, opening hours.
CONCRETE = re.compile(r"\d|रुपैयाँ|रुपैया|npr|rs\.?\s", re.IGNORECASE)

# Words too common to prove an answer is on topic.
STOPWORDS = {
    "what", "when", "where", "which", "does", "documents", "document", "need",
    "about", "have", "from", "with", "this", "that", "they", "there", "their",
    "your", "you", "the", "and", "for", "are", "how", "get", "can", "will",
    "bhaktapur", "municipality", "municipal", "nepal", "please", "would",
}


def topic_words(text):
    """Content words worth matching on — long enough to be meaningful."""
    words = re.findall(r"[\w\u0900-\u097F]{4,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def dominant_script(text):
    """'devanagari', 'latin', or None when neither clearly dominates."""
    deva = len(re.findall(r"[\u0900-\u097F]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if deva > latin * 2:
        return "devanagari"
    if latin > deva * 2:
        return "latin"
    return None


def csrf_session():
    """A brand-new browser-like session with its own CSRF cookie.

    One session per question, deliberately. The assistant runs stateful flows —
    ask it to file a complaint and the next few turns belong to that flow. Reusing
    one session across this list made unrelated questions come back as "And what
    name should I file it under?", which scores as a knowledge gap while the
    knowledge base is in fact fine. That measures contamination, not coverage.
    """
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        opener.open(BASE_URL + "/chat/", timeout=20).read()
    except urllib.error.URLError as exc:
        sys.stderr.write(
            f"INFRASTRUCTURE: no server at {BASE_URL} ({exc}). "
            "Nothing was checked — this is not a clean knowledge base.\n"
        )
        sys.exit(3)
    token = next((c.value for c in jar if c.name == "csrftoken"), "")
    return opener, token


def ask(opener, token, question):
    """Return (answer, status). answer is None when the call did not produce one."""
    body = json.dumps({"message": question}).encode()
    req = urllib.request.Request(
        BASE_URL + "/api/chat/", data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-CSRFToken": token,
            "Referer": BASE_URL,
        },
    )
    try:
        with opener.open(req, timeout=120) as resp:
            return (json.loads(resp.read()).get("response") or "").strip(), resp.status
    except urllib.error.HTTPError as exc:
        return None, exc.code
    except urllib.error.URLError:
        return None, 0


def classify(answer, question=""):
    """Return a reason string when this answer is a gap, else None."""
    if not answer:
        return "empty answer"
    words = len(answer.split())
    if words < MIN_WORDS:
        return f"only {words} words — reads like the keyword fallback, not an answer"
    low = answer.lower()
    if any(f in low for f in NO_ANSWER_FALLBACK):
        return "the assistant's own no-answer fallback fired — nothing in the knowledge base"
    if any(d in low for d in DEFLECTIONS) and not CONCRETE.search(PHONE.sub("", answer)):
        return "deflects to the municipality without giving any concrete detail"
    # Non-responsive answer. Retrieval has been seen to match an unrelated
    # document and present it as authoritative ("Based on our municipal
    # records...") for a question it does not answer at all. A long, confident,
    # off-topic answer is worse for a citizen than an honest "I don't know".
    # Bilingual caveat: this app answers English questions out of Nepali
    # municipal records on purpose. A correct Devanagari answer to a Latin
    # question shares no words with it, so word overlap cannot judge those —
    # skip the check rather than report the feature as a defect.
    cross_script = (
        dominant_script(question) is not None
        and dominant_script(answer) is not None
        and dominant_script(question) != dominant_script(answer)
    )
    if question and not cross_script:
        asked = topic_words(question)
        if asked and not (asked & topic_words(answer)):
            return (
                "does not address the question — the answer shares no subject "
                "word with what was asked, so retrieval matched something else"
            )
    return None


def write_draft(gap_id, question, answer, reason):
    """Write a draft for this gap, but never over a draft that already exists.

    A draft is where a human writes the verified municipal answer. This script
    runs on a loop; overwriting would throw that work away every few minutes.
    An existing file is left exactly as it is and reported as-is.
    """
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    path = os.path.join(DRAFTS_DIR, f"{gap_id}.md")
    if os.path.exists(path):
        return path
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f"# Knowledge gap: {gap_id}\n\n"
            f"**Citizen asked:** {question}\n\n"
            f"**Why this is a gap:** {reason}\n\n"
            f"**What the assistant said:**\n\n> {answer or '(nothing)'}\n\n"
            "---\n\n"
            "## Draft answer — NEEDS HUMAN VERIFICATION\n\n"
            "Do not publish this until someone at the municipality confirms it.\n"
            "An invented fee, deadline, or document list is worse than no answer.\n\n"
            "- [ ] Source checked against an official municipal document\n"
            "- [ ] Verified by: ______________  Date: __________\n\n"
            "(write the verified answer here)\n"
        )
    return path


def main():
    gaps, unchecked = [], []

    for gap_id, question in QUESTIONS:
        opener, token = csrf_session()  # fresh session — see csrf_session()
        answer, status = ask(opener, token, question)
        if status == 429:
            unchecked.append((gap_id, "rate limited (429)"))
            continue
        if status != 200:
            unchecked.append((gap_id, f"HTTP {status}"))
            continue
        reason = classify(answer, question)
        if reason:
            gaps.append(gap_id)
            path = write_draft(gap_id, question, answer, reason)
            print(f"GAP  {gap_id}: {reason}\n     draft -> {os.path.relpath(path, REPO)}")
        else:
            print(f"ok   {gap_id}")

    os.makedirs(os.path.dirname(GAPS_FILE), exist_ok=True)
    with open(GAPS_FILE, "w", encoding="utf-8") as fh:
        fh.write("".join(f"{g}\n" for g in gaps))

    for gap_id, why in unchecked:
        print(f"UNCHECKED {gap_id}: {why}")

    print(f"\nKB_GAPS={len(gaps)} UNCHECKED={len(unchecked)} ASKED={len(QUESTIONS)}")
    # Unchecked questions mean the layer did not fully run. Say so via exit code
    # so the caller cannot score a partial sweep as a clean one.
    return 0 if not unchecked else 4


if __name__ == "__main__":
    sys.exit(main())
