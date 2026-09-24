"""The single-row runtime settings table: auto-approve mode, thresholds,
weights, weekly cap, nudge config. Mutated via /autoapprove, /threshold and
/settings; app/config.py stays for secrets and things that never change.
"""

from __future__ import annotations

from sqlmodel import Session

from app.db.models import AppSettings

SETTINGS_ID = 1


def get_settings(session: Session) -> AppSettings:
    settings = session.get(AppSettings, SETTINGS_ID)
    if settings is None:
        settings = AppSettings(id=SETTINGS_ID)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def update_settings(session: Session, **fields) -> AppSettings:
    settings = get_settings(session)
    for key, value in fields.items():
        if value is not None:
            setattr(settings, key, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def weights(settings: AppSettings) -> dict[str, float]:
    return {
        "facts": settings.weight_facts,
        "voice": settings.weight_voice,
        "structure": settings.weight_structure,
        "hook": settings.weight_hook,
        "reader": settings.weight_reader,
    }
