"""
BD Legal Guide AI - Database Migration Runner
Idempotent migrations for SQLite and PostgreSQL.
Safely adds missing tables, columns, and indexes with IF NOT EXISTS guards.
"""

import sys
import os
from pathlib import Path

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import text, inspect
from app.core.database import Base, engine
import app.models  # Register all models


def run_migration():
    print("[*] Running idempotent database migrations...")

    # 1. Ensure all core tables exist
    Base.metadata.create_all(bind=engine)
    print(" [+] Ensured core tables exist (Base.metadata.create_all)")

    inspector = inspect(engine)
    is_sqlite = engine.dialect.name == "sqlite"

    with engine.connect() as conn:
        # 2. Check and add columns on direct_messages
        if inspector.has_table("direct_messages"):
            dm_cols = {c["name"] for c in inspector.get_columns("direct_messages")}
            if "case_id" not in dm_cols:
                fk_clause = "REFERENCES case_posts(id) ON DELETE CASCADE" if not is_sqlite else ""
                conn.execute(text(f"ALTER TABLE direct_messages ADD COLUMN case_id CHAR(36) {fk_clause}".strip()))
                print(" [+] Added direct_messages.case_id")
            if "bid_id" not in dm_cols:
                fk_clause = "REFERENCES case_bids(id) ON DELETE CASCADE" if not is_sqlite else ""
                conn.execute(text(f"ALTER TABLE direct_messages ADD COLUMN bid_id CHAR(36) {fk_clause}".strip()))
                print(" [+] Added direct_messages.bid_id")
            if "attachments" not in dm_cols:
                json_type = "JSON" if not is_sqlite else "TEXT"
                default_val = "'[]'::json" if not is_sqlite else "'[]'"
                conn.execute(text(f"ALTER TABLE direct_messages ADD COLUMN attachments {json_type} DEFAULT {default_val}"))
                print(" [+] Added direct_messages.attachments")

        # 3. Check and add columns on bookings
        if inspector.has_table("bookings"):
            b_cols = {c["name"] for c in inspector.get_columns("bookings")}
            if "trx_id" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN trx_id VARCHAR(255)"))
                print(" [+] Added bookings.trx_id")
            if "screenshot_asset_id" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN screenshot_asset_id CHAR(36)"))
                print(" [+] Added bookings.screenshot_asset_id")
            if "meeting_link" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN meeting_link VARCHAR(500)"))
                print(" [+] Added bookings.meeting_link")
            if "meeting_started_at" not in b_cols:
                ts_type = "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"
                conn.execute(text(f"ALTER TABLE bookings ADD COLUMN meeting_started_at {ts_type}"))
                print(" [+] Added bookings.meeting_started_at")
            if "meeting_ended_at" not in b_cols:
                ts_type = "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"
                conn.execute(text(f"ALTER TABLE bookings ADD COLUMN meeting_ended_at {ts_type}"))
                print(" [+] Added bookings.meeting_ended_at")
            if "extended_minutes" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN extended_minutes INTEGER DEFAULT 0"))
                print(" [+] Added bookings.extended_minutes")
            if "completion_requested_at" not in b_cols:
                ts_type = "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"
                conn.execute(text(f"ALTER TABLE bookings ADD COLUMN completion_requested_at {ts_type}"))
                print(" [+] Added bookings.completion_requested_at")
            if "completion_requested_by" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN completion_requested_by VARCHAR(50)"))
                print(" [+] Added bookings.completion_requested_by")
            if "completed_at" not in b_cols:
                ts_type = "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"
                conn.execute(text(f"ALTER TABLE bookings ADD COLUMN completed_at {ts_type}"))
                print(" [+] Added bookings.completed_at")
            if "case_brief" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN case_brief TEXT"))
                print(" [+] Added bookings.case_brief")
            if "fee" not in b_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN fee INTEGER"))
                print(" [+] Added bookings.fee")

        # 4. Check and add columns on lawyer_profiles
        if inspector.has_table("lawyer_profiles"):
            lp_cols = {c["name"] for c in inspector.get_columns("lawyer_profiles")}
            if "hourly_rate" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN hourly_rate INTEGER DEFAULT 2000"))
                print(" [+] Added lawyer_profiles.hourly_rate")
            if "years_exp" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN years_exp INTEGER DEFAULT 8"))
                print(" [+] Added lawyer_profiles.years_exp")
            if "languages" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN languages VARCHAR(255) DEFAULT 'Bangla, English'"))
                print(" [+] Added lawyer_profiles.languages")
            if "payment_methods" not in lp_cols:
                json_type = "JSON" if not is_sqlite else "TEXT"
                default_val = "'[]'::json" if not is_sqlite else "'[]'"
                conn.execute(text(f"ALTER TABLE lawyer_profiles ADD COLUMN payment_methods {json_type} DEFAULT {default_val}"))
                print(" [+] Added lawyer_profiles.payment_methods")
            if "payment_instructions" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN payment_instructions TEXT"))
                print(" [+] Added lawyer_profiles.payment_instructions")
            if "meeting_provider" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN meeting_provider VARCHAR(100)"))
                print(" [+] Added lawyer_profiles.meeting_provider")
            if "meeting_link" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN meeting_link VARCHAR(500)"))
                print(" [+] Added lawyer_profiles.meeting_link")
            if "verification_note" not in lp_cols:
                conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN verification_note TEXT"))
                print(" [+] Added lawyer_profiles.verification_note")

        # 5. Idempotent Index creation with IF NOT EXISTS
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_direct_messages_case_bid ON direct_messages(case_id, bid_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_direct_messages_lawyer_created ON direct_messages(lawyer_profile_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_direct_messages_sender_created ON direct_messages(sender_user_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_is_read_created_at ON notifications(user_id, is_read, created_at)"))

        conn.commit()

    print("[*] Migration completed successfully and idempotently!")


if __name__ == "__main__":
    run_migration()
