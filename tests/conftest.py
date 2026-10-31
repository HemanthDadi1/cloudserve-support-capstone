import pytest

from src.classify import Classifier
from src.retrieve import Retriever


@pytest.fixture(scope="session")
def retriever(tmp_path_factory):
    return Retriever(chroma_path=str(tmp_path_factory.mktemp("chroma")))


@pytest.fixture(scope="session")
def classifier(retriever):
    return Classifier(retriever)
