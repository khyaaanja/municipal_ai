"""Contact details the municipality publishes about itself.

One place, because there were twelve. `+977-1-6610000` was reaching citizens
from complaint confirmations, password-reset mail, marketplace mail, dashboard
notifications and the assistant's own "I don't know" reply, and it is not a
number bhaktapurmun.gov.np publishes anywhere. A rounded, plausible-looking
number is the worst kind of wrong: nobody reviewing the text would doubt it,
and the citizen who calls it is the one who finds out.

Every value here was read from the municipality's own site. Nothing is
inferred, and a detail that cannot be found there does not belong in this
file -- the same rule `seed_official_contacts` follows. Import these names
rather than retyping a number; a literal phone number in application code is
a number nobody will ever re-verify.
"""

SOURCE = 'https://bhaktapurmun.gov.np'

# Published as two switchboard lines; neither is a 24-hour emergency line.
PHONE_PRIMARY = '977-01-6613957'
PHONE_SECONDARY = '977-01-6610096'
EMAIL = 'info@bhaktapurmun.gov.np'
WEBSITE = SOURCE

#: For running text: "call 977-01-6613957 or 977-01-6610096".
PHONES = f'{PHONE_PRIMARY} or {PHONE_SECONDARY}'
#: The same pair for a Nepali sentence -- an English "or" inside Devanagari
#: reads as a mistake to the person it is meant to help.
PHONES_NE = f'{PHONE_PRIMARY} वा {PHONE_SECONDARY}'

#: National emergency numbers. These are not municipal lines, and a citizen
#: in an emergency should not be routed through an office switchboard.
POLICE = '100'
FIRE = '101'
AMBULANCE = '102'

#: One line, safe to append to any citizen-facing message.
OFFICE_LINE_EN = (
    f'Bhaktapur Municipality: {PHONES} | {EMAIL} | {WEBSITE}'
)
OFFICE_LINE_NE = (
    f'भक्तपुर नगरपालिका: {PHONES_NE} | {EMAIL} | {WEBSITE}'
)
EMERGENCY_LINE_EN = (
    f'In an emergency call Police {POLICE}, Fire {FIRE}, Ambulance {AMBULANCE}.'
)
# Devanagari numerals, matching how the municipality's own Nepali pages and
# the seeded Nepali entries write them.
_NE_DIGITS = str.maketrans('0123456789', '०१२३४५६७८९')
EMERGENCY_LINE_NE = (
    'आपतकालीन अवस्थामा: '
    f'प्रहरी {POLICE.translate(_NE_DIGITS)}, '
    f'दमकल {FIRE.translate(_NE_DIGITS)}, '
    f'एम्बुलेन्स {AMBULANCE.translate(_NE_DIGITS)}।'
)
