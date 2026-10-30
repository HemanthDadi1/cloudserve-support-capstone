import pytest


def test_known_question_finds_right_article(retriever):
    hits = retriever.search("I keep getting 429 Too Many Requests from the API")
    assert hits[0]["doc_id"] == "DOC-API-001"
    assert hits == sorted(hits, key=lambda h: -h["score"])


def test_passage_ids_resolve_to_corpus_text(retriever):
    for h in retriever.search("how do I roll back a failed release"):
        assert retriever.passage(h["chunk_id"])["text"] == h["text"]


@pytest.mark.parametrize("query", ["What is the capital of France?", "asdf qwerty", ""])
def test_irrelevant_query_returns_nothing(retriever, query):
    assert retriever.search(query) == []
