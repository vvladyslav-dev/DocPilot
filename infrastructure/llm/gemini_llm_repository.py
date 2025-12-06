"""Gemini LLM implementation for table extraction."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from application.ports.llm_repository import LLMRepository
from config.settings import Settings
from domain.models import ExtractionResult, ParsedDocument
import google.generativeai as genai

logger = logging.getLogger(__name__)


def _extract_json_block(text: str) -> str:
    fence = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()

    fence_any = re.search(r"```\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fence_any:
        return fence_any.group(1).strip()

    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)

    return text.strip()


def _ensure_columns_rows(payload: Any) -> tuple[list[str], list[list[Any]]]:
    if isinstance(payload, dict) and "columns" in payload and "rows" in payload:
        columns = payload["columns"]
        rows = payload["rows"]
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise ValueError("Invalid schema: 'columns' must be list and 'rows' must be list")
        return columns, rows

    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        columns = list({key for row in payload for key in row.keys()})
        rows = [[row.get(column) for column in columns] for row in payload]
        return columns, rows

    raise ValueError("Model response missing 'columns'/'rows' or list of dicts")


def _build_prompt(documents: list[ParsedDocument], instruction: str) -> str:
    intro = (
        "You are a precise data extraction engine.\n"
        "Read the provided invoice documents (in Markdown extracted by Docling).\n"
        "Follow the user's instruction EXACTLY. Pay special attention to which columns are requested.\n"
        "Return ONLY a JSON object with keys: 'columns' (list of strings) and 'rows' (list of lists).\n"
        "CRITICAL: If user specifies which columns to return, include ONLY those columns - no extra fields.\n"
        "Do not include explanations or extra text. No code fences unless JSON is fenced.\n"
        "If documents lack requested fields, include empty values for those columns.\n"
    )

    docs_blob = []
    for document in documents:
        if document.status != "success" or not document.markdown:
            continue
        docs_blob.append(f"### FILE: {document.filename}\n{document.markdown}")

    documents_section = "\n\n".join(docs_blob)

    user_section = (
        "USER INSTRUCTION:\n"
        f"{instruction}\n\n"
        "DOCUMENTS (Markdown):\n"
        f"{documents_section}\n\n"
        "Return JSON in this format:\n"
        "{\n  \"columns\": [\"col1\", \"col2\", ...],\n"
        "  \"rows\": [\n    [value1, value2, ...],\n    [value1, value2, ...]\n  ]\n}\n\n"
        "IMPORTANT: Include ONLY the columns explicitly requested in the USER INSTRUCTION above.\n"
    )

    return intro + "\n" + user_section


class GeminiLLMRepository(LLMRepository):
    """Concrete LLM repository using Google Gemini."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract_table(
        self,
        documents: list[ParsedDocument],
        *,
        instruction: str,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> ExtractionResult:
        if not documents:
            return ExtractionResult(columns=[], rows=[])

        key = (api_key or self._settings.gemini_api_key or "").strip()
        if not key:
            raise RuntimeError("GOOGLE_API_KEY is not configured. Set it as an environment variable.")

        model = (model_name or self._settings.gemini_model or "gemini-2.5-flash").strip()

        genai.configure(api_key=key)

        prompt = _build_prompt(documents, instruction)
        logger.debug("Gemini prompt length: %s", len(prompt))

        model_client = genai.GenerativeModel(model)
        response = model_client.generate_content(prompt)

        if hasattr(response, "text"):
            raw_text = response.text or ""
        else:
            try:
                raw_text = "".join(
                    part.text
                    for candidate in getattr(response, "candidates", [])
                    if getattr(candidate, "content", None) is not None
                    for part in getattr(candidate.content, "parts", [])
                    if hasattr(part, "text")
                )
            except Exception as exc:  # pragma: no cover - defensive
                raise RuntimeError("Unexpected response format from Gemini API") from exc

        json_str = _extract_json_block(raw_text)
        logger.debug("Gemini JSON snippet: %s", json_str[:500])

        payload = json.loads(json_str)
        columns, rows = _ensure_columns_rows(payload)

        return ExtractionResult(columns=columns, rows=rows)
