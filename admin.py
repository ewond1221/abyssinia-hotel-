"""
Create an admin account, or reset an admin's password.

    python admin.py

The password is typed at a hidden prompt, so it is never saved in code, git
or your shell history. There is no built-in default password any more.

To change the LIVE site's admin, run this with DATABASE_URL set to the same
value you use on Vercel, for example:

    DATABASE_URL="postgresql://user:pass@host/db" python admin.py
"""
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from app import app
from orders import db, Admin
from security import password_problem


def main():
    if not os.environ.get("DATABASE_URL"):
        print("WARNING: DATABASE_URL is not set, so this will use a local SQLite file, NOT your live database.\n")

    with app.app_context():
        username = input("Admin username [admin]: ").strip() or "admin"
        password = getpass.getpass("New password (12+ characters): ")
        repeat = getpass.getpass("Repeat password: ")

        if password != repeat:
            sys.exit("Passwords do not match. Nothing was changed.")

        problem = password_problem(password, username)
        if problem:
            sys.exit(f"{problem} Nothing was changed.")

        admin = Admin.query.filter_by(username=username).first()

        if admin:
            admin.password_hash = generate_password_hash(password)
            action = "updated"
        else:
            db.session.add(Admin(username=username, password_hash=generate_password_hash(password), role="admin"))
            action = "created"

        db.session.commit()
        print(f"Admin '{username}' {action}.")
        print("Tip: to sign out everyone who is already logged in, change JWT_SECRET_KEY on Vercel and redeploy.")


if __name__ == "__main__":
    main()
