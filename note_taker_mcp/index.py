"""Chroma-backed vector index for note summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.api.client import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.utils import embedding_functions


class IndexError(Exception):
    """Generic index-related error."""


@dataclass
class SearchHit:
    """Represents a similarity search result."""

    note_id: str
    score: float  # similarity score (1 - cosine distance)
    when_to_use: str | None
    path: str | None
    tags: list[str] | None


class NotesIndex:
    """A thin wrapper around a Chroma collection for note summaries."""

    def __init__(
        self,
        chroma_path: Path,
        collection_name: str = "notes",
        embedder: embedding_functions.EmbeddingFunction | None = None,
    ) -> None:
        self.chroma_path = Path(chroma_path)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder or embedding_functions.DefaultEmbeddingFunction()
        self.client: ClientAPI = chromadb.PersistentClient(path=str(self.chroma_path))
        self.collection: Collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embedder,
        )

    def add_entry(
        self,
        note_id: str,
        when_to_use: str,
        path: str,
        tags: list[str] | None = None,
    ) -> None:
        """Insert a new entry or overwrite an existing one."""
        # Chroma metadata fields must be scalar (str/int/float/bool/None), so we
        # store tags as a JSON string and decode on read.
        normalized_tags = [str(tag) for tag in tags] if tags is not None else []
        metadata = {
            "note_id": note_id,
            "path": path,
            "when_to_use": when_to_use,
        }
        if normalized_tags:
            metadata["tags"] = json.dumps(normalized_tags)
        self.collection.upsert(
            ids=[note_id],
            documents=[when_to_use],
            metadatas=[metadata],
        )

    def update_entry(
        self,
        note_id: str,
        when_to_use: str,
        path: str,
        tags: list[str] | None = None,
    ) -> None:
        """Update an existing entry (upsert semantics)."""
        self.add_entry(note_id, when_to_use, path, tags)

    def remove_entry(self, note_id: str) -> None:
        """Remove an entry from the index."""
        self.collection.delete(ids=[note_id])

    def search(
        self,
        query: str,
        k: int = 5,
        tags: list[str] | None = None,
        score_threshold: float = 0.75,
    ) -> list[SearchHit]:
        """Return up to k notes for a query, filtered by tags and similarity threshold."""
        if k <= 0 or score_threshold < 0:
            return []

        tag_set: set[str] = set(tags or [])

        query_k = max(k * 3, k)
        results = self.collection.query(
            query_texts=[query],
            n_results=query_k,
            include=["distances", "metadatas", "documents"],
        )
        hits: list[SearchHit] = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        for idx, note_id in enumerate(ids):
            meta = metadatas[idx] if idx < len(metadatas) else {}
            distance = distances[idx] if idx < len(distances) else 0.0
            similarity = 1 - float(distance)
            similarity = max(min(similarity, 1.0), -1.0)
            when_to_use = meta.get("when_to_use") if isinstance(meta, dict) else None
            path = meta.get("path") if isinstance(meta, dict) else None
            raw_tags = meta.get("tags") if isinstance(meta, dict) else None
            note_tags_list: list[str] = []
            if isinstance(raw_tags, list):
                note_tags_list = [str(tag) for tag in raw_tags]
            elif isinstance(raw_tags, str):
                try:
                    decoded = json.loads(raw_tags)
                    if isinstance(decoded, list):
                        note_tags_list = [str(tag) for tag in decoded]
                    elif decoded is not None:
                        note_tags_list = [str(decoded)]
                except Exception:
                    # Fallback if stored as plain string
                    note_tags_list = [raw_tags]
            fallback_doc = documents[idx] if idx < len(documents) else None
            # Lightweight lexical boost so obvious substring matches are not rejected
            query_lc = query.lower()
            doc_text = (when_to_use or fallback_doc or "").lower()
            if query_lc and doc_text and query_lc in doc_text:
                similarity = max(similarity, 0.99)
            matches_tags = True
            if tag_set:
                matches_tags = bool(set(note_tags_list) & tag_set)
            if similarity > score_threshold and matches_tags:
                hits.append(
                    SearchHit(
                        note_id=str(note_id),
                        score=similarity,
                        when_to_use=when_to_use or fallback_doc,
                        path=path,
                        tags=note_tags_list,
                    )
                )
        return hits[:k]
