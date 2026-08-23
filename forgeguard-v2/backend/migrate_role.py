"""
Migrate users table: replace is_admin + is_super_admin booleans with a single role column.
role values: 'user' | 'admin' | 'superadmin'
"""

import sqlite3

conn = sqlite3.connect("forgeguard.db")
conn.row_factory = sqlite3.Row

try:
    conn.execute("BEGIN")

    conn.execute("""
        CREATE TABLE users_new (
            id VARCHAR PRIMARY KEY,
            email VARCHAR NOT NULL UNIQUE,
            username VARCHAR NOT NULL UNIQUE,
            hashed_password VARCHAR,
            full_name VARCHAR DEFAULT '',
            google_id VARCHAR,
            is_active BOOLEAN DEFAULT 1,
            is_verified BOOLEAN DEFAULT 0,
            role VARCHAR NOT NULL DEFAULT 'user',
            created_at DATETIME,
            updated_at DATETIME,
            plan VARCHAR DEFAULT 'free',
            stripe_customer_id VARCHAR,
            stripe_subscription_id VARCHAR,
            paymongo_customer_id VARCHAR,
            paymongo_source_id VARCHAR,
            scans_this_month INTEGER DEFAULT 0,
            scan_reset_date DATETIME
        )
    """)

    rows = conn.execute("SELECT * FROM users").fetchall()
    for row in rows:
        if row["is_super_admin"]:
            role = "superadmin"
        elif row["is_admin"]:
            role = "admin"
        else:
            role = "user"

        conn.execute("""
            INSERT INTO users_new VALUES (
                :id, :email, :username, :hashed_password, :full_name, :google_id,
                :is_active, :is_verified, :role,
                :created_at, :updated_at, :plan,
                :stripe_customer_id, :stripe_subscription_id,
                :paymongo_customer_id, :paymongo_source_id,
                :scans_this_month, :scan_reset_date
            )
        """, {**dict(row), "role": role})

    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users_new RENAME TO users")
    conn.execute("COMMIT")

    cols = [col[1] for col in conn.execute("PRAGMA table_info(users)").fetchall()]
    print(f"✓ Migration complete. Columns: {cols}")
    print(f"✓ Migrated {len(rows)} user(s)")

except Exception as e:
    conn.execute("ROLLBACK")
    print(f"✗ Migration failed: {e}")
finally:
    conn.close()
