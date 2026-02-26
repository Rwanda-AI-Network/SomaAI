"""Embeddings provider factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)

# Singleton embeddings model
_EMBEDDINGS_MODEL: HuggingFaceEmbeddings | OpenAIEmbeddings | None = None


def get_embeddings(settings: Settings) -> HuggingFaceEmbeddings | OpenAIEmbeddings:
    """Get singleton embeddings model.

    Args:
        settings: Application settings

    Returns:
        Shared Embeddings instance
    """
    global _EMBEDDINGS_MODEL
    if _EMBEDDINGS_MODEL is None:
        if settings.openai_api_key:
            logger.info("Creating OpenAI embeddings model")
            _EMBEDDINGS_MODEL = OpenAIEmbeddings(
                api_key=settings.openai_api_key,
                model="text-embedding-3-small",
            )
        else:
            logger.info("Creating HuggingFace embeddings model (local)")
            _EMBEDDINGS_MODEL = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
    return _EMBEDDINGS_MODEL
