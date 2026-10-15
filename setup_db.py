"""
setup_db.py
-----------
One-time script to set up the GraphMind PostgreSQL database and create all tables.

USAGE
-----
  # Option A – pass password directly:
  python setup_db.py --pg-password YOUR_POSTGRES_PASSWORD

  # Option B – set env var first:
  $env:PGPASSWORD="YOUR_POSTGRES_PASSWORD"
  python setup_db.py

  # Option C – interactive (will prompt you):
  python setup_db.py

WHAT IT DOES
------------
  1. Creates a 'graphmind' database (owned by postgres superuser)
  2. Creates a 'graphmind' PostgreSQL user with password 'graphmind'
  3. Grants that user access to the database
  4. Creates all application tables (users, conversations, messages)
  5. Updates your .env DATABASE_URL automatically

NOTE: If you already created the database manually via pgAdmin, just run:
  python setup_db.py --skip-db --pg-password YOUR_PASSWORD
"""

import subprocess
import sys
import os
import argparse
import re
from pathlib import Path

PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"
ENV_FILE = Path(__file__).parent / ".env"

# We create a dedicated DB user for the app (better than using postgres directly)
DB_NAME     = "graphmind"
DB_USER     = "graphmind"
DB_PASSWORD = "graphmind"

SQL_COMMANDS = [
    f"CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';",
    f"CREATE DATABASE {DB_NAME} OWNER {DB_USER};",
    f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};",
]

CORRECT_DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@localhost:5432/{DB_NAME}"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_psql(pg_password: str, sql: str, db: str = "postgres") -> bool:
    env = os.environ.copy()
    env["PGPASSWORD"] = pg_password
    result = subprocess.run(
        [PSQL, "-U", "postgres", "-d", db, "-c", sql],
        env=env,
        capture_output=True,
        text=True,
    )
    already_exists = "already exists" in result.stderr
    if result.returncode == 0 or already_exists:
        status = "(already existed)" if already_exists else "created"
        print(f"  ✅  {sql[:70].strip()}  [{status}]")
        return True
    else:
        print(f"  ❌  {sql[:70].strip()}")
        print(f"      Error: {result.stderr.strip()}")
        return False


def test_connection(pg_password: str) -> bool:
    env = os.environ.copy()
    env["PGPASSWORD"] = pg_password
    result = subprocess.run(
        [PSQL, "-U", "postgres", "-c", "SELECT 1;"],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def update_env_database_url():
    if not ENV_FILE.exists():
        return
    content = ENV_FILE.read_text(encoding="utf-8")
    # Replace any existing DATABASE_URL line
    new_content = re.sub(
        r"^DATABASE_URL=.*$",
        f"DATABASE_URL={CORRECT_DATABASE_URL}",
        content,
        flags=re.MULTILINE,
    )
    if new_content != content:
        ENV_FILE.write_text(new_content, encoding="utf-8")
        print(f"  ✅  Updated DATABASE_URL in .env")
    else:
        print(f"  ℹ️   DATABASE_URL in .env already correct")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GraphMind database setup")
    parser.add_argument(
        "--pg-password", default=os.getenv("PGPASSWORD", ""),
        help="PostgreSQL superuser (postgres) password"
    )
    parser.add_argument(
        "--skip-db", action="store_true",
        help="Skip database/user creation (if you already did it via pgAdmin)"
    )
    args = parser.parse_args()

    print("\n" + "=" * 55)
    print("  GraphMind — Database Setup")
    print("=" * 55 + "\n")

    # ── Step 1: Get postgres password ─────────────────────────────────────────
    if not args.pg_password:
        print("Enter your PostgreSQL superuser (postgres) password.")
        print("(This is the password you set during PostgreSQL installation)\n")
        args.pg_password = input("Password: ").strip()

    if not args.pg_password:
        print("\n❌  No password provided. Exiting.")
        sys.exit(1)

    # ── Step 2: Test connection ──────────────────────────────────────────────
    print("\n[1/4] Testing connection to PostgreSQL...")
    if not test_connection(args.pg_password):
        print("\n❌  Could not connect with that password.")
        print("\n   → Try using pgAdmin 4 to reset your postgres password:")
        print("      1. Open pgAdmin 4 (Start Menu)")
        print("      2. Right-click 'Login/Group Roles → postgres → Properties'")
        print("      3. Go to 'Definition' tab → set a new password")
        print("      4. Re-run this script with the new password")
        sys.exit(1)

    print("  ✅  Connected to PostgreSQL successfully!\n")

    # ── Step 3: Create DB user and database ──────────────────────────────────
    if not args.skip_db:
        print("[2/4] Creating database user and database...")
        for sql in SQL_COMMANDS:
            run_psql(args.pg_password, sql)
        # Grant schema privileges
        run_psql(
            args.pg_password,
            f"GRANT ALL ON SCHEMA public TO {DB_USER};",
            db=DB_NAME,
        )
    else:
        print("[2/4] Skipping database creation (--skip-db flag set)")

    # ── Step 4: Update .env ───────────────────────────────────────────────────
    print("\n[3/4] Updating .env file...")
    update_env_database_url()

    # ── Step 5: Create tables ─────────────────────────────────────────────────
    print("\n[4/4] Creating application tables...")
    try:
        from backend.database import engine, Base
        import backend.models  # noqa: F401 – registers all models with Base
        Base.metadata.create_all(bind=engine)
        print("  ✅  Tables created: users, conversations, messages")
    except Exception as e:
        print(f"  ❌  Failed to create tables: {e}")
        print("\n  Make sure your .env DATABASE_URL is correct and try again.")
        sys.exit(1)

    # ── Done ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  ✅  Setup complete!")
    print("=" * 55)
    print("""
Next steps:
  1. Start the backend:
     .venv\\Scripts\\python.exe -m uvicorn backend.main:app --reload --port 8000

  2. Start the frontend (new terminal):
     cd frontend
     npm run dev

  3. Open your browser:
     http://localhost:5173
""")


if __name__ == "__main__":
    main()
