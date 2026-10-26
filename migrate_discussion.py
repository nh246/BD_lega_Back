from app.core.database import engine
from sqlalchemy import text

def run_migration():
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS case_id UUID REFERENCES case_posts(id) ON DELETE CASCADE;
            ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS bid_id UUID REFERENCES case_bids(id) ON DELETE CASCADE;
            CREATE INDEX IF NOT EXISTS ix_direct_messages_case_bid ON direct_messages(case_id, bid_id, created_at);
        """))
        conn.commit()
    print("Migration successful: case_id and bid_id added to direct_messages!")

if __name__ == "__main__":
    run_migration()
