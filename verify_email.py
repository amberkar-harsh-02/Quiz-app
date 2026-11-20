"""Marks an account's email as verified, so staff access on the Staff page or in ADMIN_EMAILS applies to it.

Normally Google sign-in does this. Use it for local testing without Google, or for a staff member who can't
use Google sign-in. Only run it for an address you know belongs to the person using that account.

Run it from the folder that holds kahoot.db:
    python verify_email.py name@csumb.edu
"""
import sys

import models
from database import SessionLocal, add_missing_columns, engine


def main(email: str) -> int:
    add_missing_columns(engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
        if user is None:
            print(f"No account for {email}. Sign up first, then run this again.")
            return 1
        user.email_verified = True
        db.commit()
        print(f"{user.email} is verified.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
