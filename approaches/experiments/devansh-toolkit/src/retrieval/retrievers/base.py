"""The one interface every retriever implements, and the registry that makes them plug-and-play.

Add a retriever:

    @register("my_algo")
    class MyAlgo(Retriever):
        def fit(self, chunks): ...
        def search(self, query, k): return [Hit(chunk_id, score), ...]   # best first

then use {"type": "my_algo", ...params} in a pipeline config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..corpus import Chunk

REGISTRY: dict[str, type["Retriever"]] = {}


def register(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        REGISTRY[name] = cls
        cls.name = name
        return cls
    return deco


@dataclass
class Hit:
    chunk_id: int
    score: float


class Retriever:
    name = "base"

    def __init__(self, **params):
        self.params = params

    def fit(self, chunks: list[Chunk]) -> "Retriever":
        raise NotImplementedError

    def search(self, query: str, k: int = 100) -> list[Hit]:
        raise NotImplementedError

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        """Override when batching is cheaper (dense encoders)."""
        return [self.search(q, k) for q in queries]


def build(config: dict) -> Retriever:
    """{"type": "bm25", "k1": 1.2} -> BM25(k1=1.2). Nested retrievers (fusion, rerank) are built recursively."""
    config = dict(config)
    kind = config.pop("type")
    if kind not in REGISTRY:
        raise KeyError(f"unknown retriever {kind!r}; available: {sorted(REGISTRY)}")
    return REGISTRY[kind](**config)


# ---- shared text helpers -------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on or shall that the this to which with"
    " be been being such any all each other than then there these those may not no only".split()
)


def tokenize(text: str, stopwords: bool = True) -> list[str]:
    """Lowercase word tokens; paragraph numbers like 6.7.4.1 stay one token."""
    toks = _TOKEN.findall(text.lower())
    return [t for t in toks if t not in STOPWORDS] if stopwords else toks


def chunk_text(chunk: Chunk, with_title: bool = True) -> str:
    """The text a retriever indexes: the regulation title gives every paragraph its topic (cheap 'contextual retrieval')."""
    head = f"{chunk.regulation} {chunk.title}. {chunk.paragraph or ''}\n" if with_title else ""
    return head + chunk.text
