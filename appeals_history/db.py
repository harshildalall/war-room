"""
appeal_history.db
~~~~~~~~~~~~~~~~~
MongoDB client and database handle for the appeal_history database.

Uses the same cluster as the counterclaim evidence database but addresses
a separate database so the two are fully isolated at the operational level.

    cluster/
        counterclaim          <- existing evidence DB, read-only at runtime
            evidence_sources
            evidence_chunks
        appeal_history        <- this module
            appeal_records

Required environment variables (add to your .env):
    MONGODB_URI                 connection string   (shared with counterclaim)
    MONGODB_APPEAL_DB           database name       default: "appeal_history"
    MONGODB_APPEAL_COLLECTION   collection name     default: "appeal_records"
"""
from __future__ import annotations

import os
import threading

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database

# ─────────────────────────────────────────────────────────────────────────────
# Singleton client — created once on first use so that environment variables
# loaded by dotenv after import are picked up correctly.
# MongoClient manages its own connection pool; one instance serves both the
# counterclaim and appeal_history databases.
# ─────────────────────────────────────────────────────────────────────────────
_client: MongoClient | None = None
_lock = threading.Lock()


def get_client() -> MongoClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                uri = os.environ["MONGODB_URI"]
                _client = MongoClient(
                    uri,
                    serverSelectionTimeoutMS=5_000,
                    connectTimeoutMS=5_000,
                    socketTimeoutMS=10_000,
                )
    return _client


def get_db() -> Database:
    db_name = os.getenv("MONGODB_APPEAL_DB", "appeal_history")
    return get_client()[db_name]


def get_collection() -> Collection:
    col_name = os.getenv("MONGODB_APPEAL_COLLECTION", "appeal_records")
    return get_db()[col_name]


# ─────────────────────────────────────────────────────────────────────────────
# Indexes
# Call init_db() ONCE at application startup — not inside query or write
# functions. MongoDB is idempotent on index creation so repeated calls are
# safe, but each call makes a network round-trip.
# ─────────────────────────────────────────────────────────────────────────────

def init_db() -> None:
    col = get_collection()
    col.create_index([("case_id", ASCENDING)],               unique=True,  name="case_id_unique")
    col.create_index([("insurer_name", ASCENDING)],                         name="insurer_name")
    col.create_index([("denial_reason_category", ASCENDING)],               name="denial_reason_category")
    col.create_index([("cpt_hcpcs_codes", ASCENDING)],                      name="cpt_hcpcs_codes")
    col.create_index([("icd10_codes", ASCENDING)],                          name="icd10_codes")
    col.create_index([("denial_date", ASCENDING)],                          name="denial_date")
    col.create_index([("appeal_deadline", ASCENDING)],                      name="appeal_deadline")
    col.create_index([("recorded_at", DESCENDING)],                         name="recorded_at_desc")
    col.create_index([("outcome.outcome_status", ASCENDING)],               name="outcome_status")


def ping() -> bool:
    """Return True if the MongoDB server is reachable."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False