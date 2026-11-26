"""Operator tool: vouches for accounts from the server, where Google sign-in can't.

Staff and admin rights need a verified account. Google sign-in verifies one by proving the person owns
the mailbox. For an address that isn't a Google account (or for local testing), whoever runs the server
can verify it here instead: having shell access to the server is the proof.

Run it from the folder that holds kahoot.db (on the server: ~/quiz-app, with venv/bin/python):
    python verify_email.py legend@csumb.edu dnegel@csumb.edu   mark existing accounts verified
    python verify_email.py --create you@csumb.edu              create a verified account (asks for a password)
    python verify_email.py --password you@csumb.edu            set a new password (asks for it)

Only vouch for addresses you know belong to the person using that account.
"""
import argparse
import getpass
import os
import re
import sys

from dotenv import load_dotenv
from passlib.context import CryptContext

import models
from database import SessionLocal, add_missing_columns, engine

# Same hashing as main.py's sign-up and sign-in
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
CSUMB_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]*@csumb\.edu")
MIN_PASSWORD = 8
GOOGLE_ONLY = "GOOGLE_SSO_USER"


def admin_emails() -> set:
    load_dotenv()
    return {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}


def ask_password(ask) -> str:
    for _ in range(3):
        first = ask("New password: ")
        if len(first) < MIN_PASSWORD:
            print(f"Passwords need at least {MIN_PASSWORD} characters.")
            continue
        if ask("Type it again: ") != first:
            print("Those didn't match.")
            continue
        return first
    raise SystemExit("No password set.")


def describe(db, email: str, admins: set) -> str:
    if email in admins:
        return "is an admin (ADMIN_EMAILS)"
    if db.query(models.StaffEmail).filter(models.StaffEmail.email == email).first():
        return "is on the staff list"
    return "is not on the staff list or in ADMIN_EMAILS, so it gets no extra rights"


def main(argv=None, ask=getpass.getpass) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--create", action="store_true", help="create the account if it doesn't exist")
    mode.add_argument("--password", action="store_true", help="set a new password for the account")
    parser.add_argument("emails", nargs="+")
    args = parser.parse_args(argv)
    if (args.create or args.password) and len(args.emails) != 1:
        parser.error("--create and --password take one email at a time")

    add_missing_columns(engine)
    models.Base.metadata.create_all(bind=engine)
    admins = admin_emails()
    db = SessionLocal()
    failed = False
    try:
        for raw in args.emails:
            email = raw.strip().lower()
            user = db.query(models.User).filter(models.User.email == email).first()

            if args.create and user is None:
                if not CSUMB_EMAIL.fullmatch(email):
                    print(f"{email}: not a valid @csumb.edu address.")
                    failed = True
                    continue
                user = models.User(email=email, hashed_password=pwd_context.hash(ask_password(ask)))
                db.add(user)
            elif user is None:
                print(f"{email}: no account. Use --create to make one.")
                failed = True
                continue
            elif args.password:
                if user.hashed_password == GOOGLE_ONLY:
                    print(f"{email}: this account signs in with Google; it has no password to change.")
                    failed = True
                    continue
                user.hashed_password = pwd_context.hash(ask_password(ask))

            user.email_verified = True
            db.commit()
            print(f"{email}: verified; {describe(db, email, admins)}.")
    finally:
        db.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
