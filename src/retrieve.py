"""Retrieve: search the documentation corpus for passages relevant to a ticket (A4).

Chunking: one passage per article section (Symptoms, Common causes, Resolution, Notes), each
prefixed with the article title. On the 500 dev tickets this put the expected article first
90% of the time vs 87% for whole articles, and never splits a numbered resolution sequence.
Passage IDs look like "DOC-AUTH-001#resolution" and resolve back via Retriever.passage() (A6).
"""
import hashlib
import json
import os
import re
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DOCS_PATH = os.getenv("DOCS_PATH", str(ROOT / "data/documentation.json"))
CHROMA_PATH = os.getenv("CHROMA_PATH", str(ROOT / "storage/chroma"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
# From evaluation/retrieval_threshold.py on dev tickets: off-topic text tops out at 0.29; below 0.40
# the top passage is right only 2 times in 4; at 0.40+ it is right 82-95% of the time.
MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.40"))


def chunk(doc: dict) -> list[dict]:
    parts = re.split(r"\n(?=## )", doc["content"])
    out = []
    for part in parts[1:]:  # parts[0] is the title and applies-to line
        heading = part.splitlines()[0].removeprefix("## ").strip()
        out.append({
            "chunk_id": f"{doc['doc_id']}#{re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')}",
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "section": heading,
            "text": f"{doc['title']}\n{part.strip()}",
        })
    return out


class Retriever:
    def __init__(self, docs_path: str = DOCS_PATH, chroma_path: str = CHROMA_PATH):
        raw = Path(docs_path).read_bytes()
        self.chunks = {c["chunk_id"]: c for d in json.loads(raw) for c in chunk(d)}
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        # Collection name carries a hash of the corpus, so an edited corpus is re-indexed automatically.
        name = f"docs-{hashlib.sha256(raw).hexdigest()[:12]}"
        self.collection = chromadb.PersistentClient(path=chroma_path).get_or_create_collection(
            name, metadata={"hnsw:space": "cosine"})
        if self.collection.count() != len(self.chunks):
            ids = list(self.chunks)
            self.collection.upsert(ids=ids, embeddings=self.embed([self.chunks[i]["text"] for i in ids]),
                                   metadatas=[{"doc_id": self.chunks[i]["doc_id"]} for i in ids])

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def search(self, text: str, k: int = TOP_K, min_score: float = MIN_SCORE) -> list[dict]:
        """Ranked passages scoring at least min_score; an empty list means nothing relevant."""
        if not text.strip():
            return []
        res = self.collection.query(query_embeddings=self.embed([text]), n_results=k)
        hits = [{**self.chunks[cid], "score": round(1 - dist, 4)}
                for cid, dist in zip(res["ids"][0], res["distances"][0])]
        return [h for h in hits if h["score"] >= min_score]

    def passage(self, chunk_id: str) -> dict | None:
        return self.chunks.get(chunk_id)
