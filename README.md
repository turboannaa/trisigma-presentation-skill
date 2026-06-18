# Trisigma Presentation Skill

Claude skill for creating Trisigma-branded Google Slides presentations.

## Setup

1. Get `credentials.json` from Google Cloud Console → APIs & Services → Credentials
2. Place it in the project root
3. Run auth: `python3 scripts/auth.py`
4. Install dependencies: `pip install google-api-python-client google-auth-oauthlib Pillow`

## Usage

Create a `plan.json` file (see SKILL.md for format), then run:

```bash
python3 scripts/create_presentation.py plan.json
```

The script will output a Google Slides link.

## Template

[Trisigma Slides Template](https://docs.google.com/presentation/d/1r3JViMJ_gH-OGTBb4U1ijwDDvR14ulvYF4lVAckf5n0/edit)
