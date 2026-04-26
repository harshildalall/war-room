from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import certifi
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient


AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = AGENT_DIR / "source_manifest.json"
REQUIRED_FIELDS = {
    "source_id",
    "source_type",
    "title",
    "local_path",
    "url",
    "citation_label",
    "codes",
    "condition_terms",
    "service_terms",
    "manual_reviewed",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Manifest must be a JSON list of source objects.")

    seen: set[str] = set()
    for source in data:
        missing = REQUIRED_FIELDS - set(source)
        if missing:
            raise ValueError(f"{source.get('source_id', '<unknown>')} missing fields: {sorted(missing)}")
        if source["source_id"] in seen:
            raise ValueError(f"Duplicate source_id: {source['source_id']}")
        seen.add(source["source_id"])

        local_path = AGENT_DIR / source["local_path"]
        if not local_path.exists():
            raise FileNotFoundError(f"Missing source file for {source['source_id']}: {local_path}")
        if local_path.suffix.lower() != ".txt":
            raise ValueError(f"Only .txt curated sources are supported for now: {local_path}")

    return data


def read_source_text(source: dict[str, Any]) -> str:
    path = AGENT_DIR / source["local_path"]
    text = path.read_text(encoding="utf-8", errors="replace")
    text = text.replace("\f", "\n\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return [re.sub(r"\s+", " ", paragraph) for paragraph in paragraphs]


def chunk_text(text: str, max_chars: int = 1800, overlap_chars: int = 250) -> list[str]:
    paragraphs = split_paragraphs(text)
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(paragraph), max_chars - overlap_chars):
                chunks.append(paragraph[start : start + max_chars].strip())
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current.strip())
        overlap = current[-overlap_chars:].strip() if overlap_chars and current else ""
        current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph

    if current:
        chunks.append(current.strip())

    return [chunk for chunk in chunks if chunk]


def source_document(source: dict[str, Any], text: str) -> dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "source_type": source["source_type"],
        "title": source["title"],
        "url": source["url"],
        "citation_label": source["citation_label"],
        "insurer": source.get("insurer"),
        "effective_date": source.get("effective_date"),
        "codes": source.get("codes", []),
        "diagnosis_codes": source.get("diagnosis_codes", []),
        "condition_terms": source.get("condition_terms", []),
        "service_terms": source.get("service_terms", []),
        "manual_reviewed": source["manual_reviewed"],
        "local_path": source["local_path"],
        "text_hash": stable_hash(text),
        "text_length": len(text),
        "updated_at": utc_now(),
    }


def chunk_documents(source: dict[str, Any], chunks: list[str]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    citation = {
        "title": source["title"],
        "url": source["url"],
        "citation_label": source["citation_label"],
        "source_type": source["source_type"],
        "effective_date": source.get("effective_date"),
    }

    for index, text in enumerate(chunks):
        chunk_id = f"{source['source_id']}_{index:04d}"
        docs.append(
            {
                "chunk_id": chunk_id,
                "source_id": source["source_id"],
                "source_type": source["source_type"],
                "title": source["title"],
                "url": source["url"],
                "citation": citation,
                "insurer": source.get("insurer"),
                "effective_date": source.get("effective_date"),
                "codes": source.get("codes", []),
                "diagnosis_codes": source.get("diagnosis_codes", []),
                "condition_terms": source.get("condition_terms", []),
                "service_terms": source.get("service_terms", []),
                "manual_reviewed": source["manual_reviewed"],
                "chunk_index": index,
                "text": text,
                "text_hash": stable_hash(text),
                "text_length": len(text),
                "embedding": None,
                "created_at": utc_now(),
            }
        )
    return docs


def get_collections():
    load_dotenv(AGENT_DIR / ".env")
    uri = os.getenv("MONGODB_URI")
    if not uri or "<" in uri:
        raise ValueError("MONGODB_URI is missing or still contains placeholders.")

    client = MongoClient(uri, serverSelectionTimeoutMS=12000, tlsCAFile=certifi.where())
    client.admin.command("ping")
    db = client[os.getenv("MONGODB_DB", "counterclaim")]
    sources = db[os.getenv("MONGODB_EVIDENCE_SOURCES_COLLECTION", "evidence_sources")]
    chunks = db[os.getenv("MONGODB_EVIDENCE_CHUNKS_COLLECTION", "evidence_chunks")]
    return sources, chunks


def ensure_indexes(chunks) -> None:
    for field in ["source_id", "source_type", "insurer", "codes", "condition_terms", "service_terms"]:
        chunks.create_index([(field, ASCENDING)], name=f"{field}_1")
    chunks.create_index([("chunk_id", ASCENDING)], name="chunk_id_1", unique=True)


def ingest(manifest_path: Path, write: bool, source_ids: set[str] | None) -> None:
    manifest = load_manifest(manifest_path)
    if source_ids:
        manifest = [source for source in manifest if source["source_id"] in source_ids]
        missing = source_ids - {source["source_id"] for source in manifest}
        if missing:
            raise ValueError(f"Unknown source_id filter(s): {sorted(missing)}")

    prepared: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = []
    for source in manifest:
        text = read_source_text(source)
        chunks = chunk_text(text)
        prepared.append((source, source_document(source, text), chunk_documents(source, chunks)))

    print(f"manifest={manifest_path}")
    print(f"mode={'write' if write else 'dry-run'}")
    for source, source_doc, docs in prepared:
        print(
            f"source_id={source['source_id']} chunks={len(docs)} "
            f"text_length={source_doc['text_length']} citation={source['citation_label']}"
        )

    if not write:
        return

    sources_collection, chunks_collection = get_collections()
    ensure_indexes(chunks_collection)
    for source, source_doc, docs in prepared:
        sources_collection.update_one(
            {"source_id": source["source_id"]},
            {"$set": source_doc},
            upsert=True,
        )
        chunks_collection.delete_many({"source_id": source["source_id"]})
        if docs:
            chunks_collection.insert_many(docs)

    print("write_complete=true")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest curated External Evidence sources into MongoDB.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to source manifest JSON.")
    parser.add_argument("--write", action="store_true", help="Write parsed sources and chunks to MongoDB.")
    parser.add_argument("--source-id", action="append", help="Only ingest the given source_id. May be repeated.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ingest(Path(args.manifest), write=args.write, source_ids=set(args.source_id or []) or None)
