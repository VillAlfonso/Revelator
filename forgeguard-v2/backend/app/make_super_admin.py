"""
Promote users to super admin.

Usage (from the backend/ directory):
    python -m app.make_super_admin --all              # make all users super admin
    python -m app.make_super_admin user@example.com   # make specific user super admin
    python -m app.make_super_admin --revoke user@example.com  # revoke super admin role
"""

import argparse
import sys

from .database import SessionLocal, init_db
from .models import User


def main():
    parser = argparse.ArgumentParser(description="Promote users to super admin in Revelator.")
    parser.add_argument("email", nargs="?", help="Email of a specific user to modify")
    parser.add_argument("--all", action="store_true", help="Promote ALL users to super admin")
    parser.add_argument("--revoke", action="store_true", help="Revoke super admin role instead of granting it")
    args = parser.parse_args()

    if not args.all and not args.email:
        print("Error: Either provide an email or use --all")
        print("Usage:")
        print("  python -m app.make_super_admin --all")
        print("  python -m app.make_super_admin user@example.com")
        sys.exit(1)

    init_db()  # ensure tables + columns exist
    db = SessionLocal()
    try:
        if args.all:
            # Promote all users
            users = db.query(User).all()
            if not users:
                print("No users found in database")
                sys.exit(1)

            count = 0
            for user in users:
                user.role = "user" if args.revoke else "superadmin"
                count += 1

            db.commit()
            action = "revoked" if args.revoke else "granted"
            print(f"Super admin role {action} for {count} user(s)")
            for user in users:
                print(f"  - {user.email} (id={user.id}, plan={user.plan})")
        else:
            # Promote specific user
            user = db.query(User).filter(User.email == args.email).first()
            if not user:
                print(f"No user found with email: {args.email}")
                sys.exit(1)

            user.role = "user" if args.revoke else "superadmin"
            db.commit()
            action = "revoked" if args.revoke else "granted"
            print(f"Super admin role {action} for {user.email} (id={user.id}, plan={user.plan})")

    finally:
        db.close()


if __name__ == "__main__":
    main()
