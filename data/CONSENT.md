# Consent Policy

Every image placed in `data/subjects/` must belong to a person who has
**explicitly consented** to participate in this project demo.

## What counts as consent

- A verbal "yes" recorded during the project session, **or**
- A signed/digital consent form (template can be added later).

## How we track it

1. Each subject gets a subdirectory: `data/subjects/<name>/`.
2. Inside that directory, place a `consent.txt` file containing:
   - Subject's name (or alias)
   - Date consent was given
   - Brief description of how consent was obtained
   - Optionally: a line for "scope" (e.g. "demo only, not production")

Example:
```
# data/subjects/alice/consent.txt
Name: Alice
Date: 2026-09-02
Scope: hackathon demo only
Method: Verbal consent during team meeting, confirmed by two witnesses.
```

## What NOT to do

- Do **not** add images of anyone who has not given consent.
- Do **not** add images scraped from the internet or social media.
- Do **not** use this folder for testing with random/fake faces — the
  pipeline should work with **real** consented subjects only.

## Enforcement

A future Phase 1 script (`face_id/validate_consent.py`) will scan
`data/subjects/` and warn/error if any image directory is missing
`consent.txt`.
