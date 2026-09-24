from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.db.migrations import run_all_migrations
from app.db.models import AppSettings, Draft, Note  # noqa: F401 - registers tables on SQLModel.metadata


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_migration_maps_old_decision_values_to_rejected():
    engine = _engine()
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO note (text, source, status, received_at) VALUES "
                "('n1', 'import', 'drafted', '2026-01-01T00:00:00'), "
                "('n2', 'import', 'drafted', '2026-01-01T00:00:00'), "
                "('n3', 'import', 'drafted', '2026-01-01T00:00:00')"
            )
        )
        session.execute(
            text(
                "INSERT INTO draft (note_id, version, body, decision, is_current, word_count, "
                "verify_count, created_at, human_edited, auto_redraft_count) VALUES "
                "(1, 1, 'a', 'AUTO_APPROVED', 1, 0, 0, '2026-01-01T00:00:00', 0, 0), "
                "(2, 1, 'b', 'NEEDS_REVIEW', 1, 0, 0, '2026-01-01T00:00:00', 0, 0), "
                "(3, 1, 'c', 'LOW_QUALITY', 1, 0, 0, '2026-01-01T00:00:00', 0, 0)"
            )
        )
        session.commit()

        run_all_migrations(session)

        rows = session.execute(text("SELECT note_id, decision FROM draft ORDER BY note_id")).all()

    decisions = {note_id: decision for note_id, decision in rows}
    assert decisions[1] == "APPROVED"
    assert decisions[2] == "REJECTED"
    assert decisions[3] == "REJECTED"


def test_migration_maps_shadow_mode_to_on():
    engine = _engine()
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO appsettings (id, mode, auto_approve_threshold, weekly_cap, "
                "weight_facts, weight_voice, weight_structure, weight_hook, weight_reader, "
                "nudge_enabled, nudge_hour_ist) VALUES "
                "(1, 'SHADOW', 85, 3, 0.2, 0.2, 0.2, 0.2, 0.2, 1, 19)"
            )
        )
        session.commit()

        run_all_migrations(session)

        mode = session.execute(text("SELECT mode FROM appsettings WHERE id=1")).scalar_one()
    assert mode == "ON"


def test_migration_is_idempotent_and_safe_on_empty_db():
    engine = _engine()
    with Session(engine) as session:
        run_all_migrations(session)  # nothing to migrate, must not raise
        run_all_migrations(session)  # running twice must also not raise
