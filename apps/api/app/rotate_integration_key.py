"""Re-encrypt stored integration credentials under a new INTEGRATION_TOKEN_KEY.

INTEGRATION_TOKEN_KEY derives the Fernet key for every stored Google refresh
token. Changing it in place makes all of them undecryptable, which silently
breaks every sync and forces each client to reconnect Google. This rotates
without that: decrypt with whichever key works, re-encrypt with the current one.

Usage, on the API service:

    # 1. Keep the old value, set the new one
    INTEGRATION_TOKEN_KEY_PREVIOUS=<old>   # the value being replaced
    INTEGRATION_TOKEN_KEY=<new 32+ byte secret>

    # 2. Check what would change
    python -m app.rotate_integration_key --dry-run

    # 3. Rotate
    python -m app.rotate_integration_key

    # 4. Remove INTEGRATION_TOKEN_KEY_PREVIOUS

Safe to re-run: rows already under the current key are left alone.
"""

from __future__ import annotations

import argparse
import logging
import sys

from cryptography.fernet import InvalidToken

from app.core.crypto import _fernet, _previous_fernet, encrypt_json
from app.core.db import SessionLocal
from app.core.settings import INSECURE_TOKEN_KEY, get_settings
from app.models.integration import Integration

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("organiciq.rotate")


def _decrypt_with(fernet, blob: str):
    import json

    return json.loads(fernet.decrypt(blob.encode("utf-8")).decode("utf-8"))


def rotate(*, dry_run: bool = False) -> int:
    settings = get_settings()

    if settings.integration_token_key == INSECURE_TOKEN_KEY:
        logger.error(
            "INTEGRATION_TOKEN_KEY is still the development default. Set a real "
            "one before rotating, or this re-encrypts to a publicly known key."
        )
        return 1

    current = _fernet()
    previous = _previous_fernet()

    db = SessionLocal()
    rotated = already_current = failed = 0
    try:
        rows = db.query(Integration).filter(Integration.credentials.isnot(None)).all()
        logger.info("Found %d integration row(s) with stored credentials.", len(rows))

        for row in rows:
            blob = row.credentials
            if not blob:
                continue

            try:
                _decrypt_with(current, blob)
                already_current += 1
                continue
            except InvalidToken:
                pass

            if previous is None:
                failed += 1
                logger.error(
                    "Row %s cannot be read with the current key and no "
                    "INTEGRATION_TOKEN_KEY_PREVIOUS is set.",
                    row.id,
                )
                continue

            try:
                payload = _decrypt_with(previous, blob)
            except InvalidToken:
                failed += 1
                logger.error("Row %s is readable with neither key.", row.id)
                continue

            if not dry_run:
                row.credentials = encrypt_json(payload)
            rotated += 1

        if dry_run:
            db.rollback()
            logger.info(
                "DRY RUN — would rotate %d, already current %d, unreadable %d.",
                rotated,
                already_current,
                failed,
            )
        else:
            db.commit()
            logger.info(
                "Rotated %d, already current %d, unreadable %d.",
                rotated,
                already_current,
                failed,
            )
    finally:
        db.close()

    # Unreadable rows mean a grant is lost and that client must reconnect.
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    return rotate(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
