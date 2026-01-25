"""Google Gemini providers for embeddings and LLM arbitration."""

from __future__ import annotations

import os
import subprocess

import structlog
from google import genai

log = structlog.get_logger()


def _get_project() -> str:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        return project
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, check=True,
        )
        project = result.stdout.strip()
        if project:
            return project
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    raise RuntimeError(
        "No GCP project found. Set GOOGLE_CLOUD_PROJECT or run: "
        "gcloud config set project <PROJECT_ID>"
    )


def _make_client() -> genai.Client:
    project = _get_project()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    return genai.Client(vertexai=True, project=project, location=location)


class GeminiEmbeddingProvider:
    """EmbeddingProvider backed by Gemini text-embedding-004."""

    MODEL = "text-embedding-004"

    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or _make_client()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = self._client.models.embed_content(
            model=self.MODEL,
            contents=texts,
        )
        return [e.values for e in result.embeddings]


class GeminiLLMProvider:
    """LLMProvider backed by Gemini 2.0 Flash."""

    MODEL = "gemini-2.0-flash"

    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or _make_client()

    def query(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.MODEL,
            contents=prompt,
        )
        return response.text
