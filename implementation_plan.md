# Implementation Plan

## Overview
Make the existing "Public Notices" page (`/services/notices/`) easily discoverable by adding navigation links so every citizen can reach it without knowing the URL.

## Context
The Public Notices feature is fully implemented and works: the `PublicNotice` model in `services/models.py`, the `notice_list`/`notice_detail` views in `services/views.py`, the URL routes in `services/urls.py`, and the list/detail templates (`templates/services/notice_list.html`, `templates/services/notice_detail.html`) all function correctly. The reported problem is purely **discoverability**: the page has no link from the main navigation, the footer, or the mobile menu. A user must manually type `/services/notices/` to reach it.

Investigation confirmed the navigation gaps:
- `templates/base/_nav_partial.html` — the "Civic" dropdown links to `/announcements/` (`core:announcements_public`), `/ward-projects/`, `/transparency/`, and complaint pages, but **not** to `/services/notices/`.
- `templates/base/base.html` — the footer "City Services" column has no notice link, and the mobile bottom nav has no notice link.
- The mobile menu (inside `_nav_partial.html`) also lacks a notice link.

The fix is frontend-only and additive: add links to the Public Notices page in the Civic dropdown, the footer, and the mobile menu. This changes nothing about the existing models, views, or URL routing, so nothing that already works is affected.

## Types
No type, model, database, or schema changes are required.

## Files
Edits are confined to two existing HTML templates; no new files are created or deleted.

- `templates/base/_nav_partial.html` (modified)
  - Add a "Public Notices" link to the **Civic dropdown menu**, next to the existing Announcements link.
  - Add a matching "Public Notices" link to the **mobile menu**.
- `templates/base/base.html` (modified)
  - Add a "Public Notices" link to the **footer "City Services"** column list.

## Functions
No function modifications are required. The existing `notice_list` and `notice_detail` views in `services/views.py` are unchanged and remain the sole handler for the page.

## Classes
No class modifications are required.

## Dependencies
No dependency changes are required.

## Testing
Add a regression test in `services/tests.py` (within the existing `PublicNoticeTests` class) that asserts the public notices page renders and contains the notice title, and add a template-level assertion that the nav/footer link to the notices page is present.

## Implementation Order
1. Add the "Public Notices" link to the Civic dropdown in `templates/base/_nav_partial.html`.
2. Add the "Public Notices" link to the mobile menu in `templates/base/_nav_partial.html`.
3. Add the "Public Notices" link to the footer "City Services" column in `templates/base/base.html`.
4. Add/extend a test in `services/tests.py` to verify the notices page and the new navigation link are present.
5. Run the test suite and manually verify the link appears on the homepage and navigates to `/services/notices/`.
