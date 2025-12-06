"""Docling-based implementation of the document parser port."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode, VlmPipelineOptions
from docling.document_converter import ConversionStatus, DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling.datamodel import vlm_model_specs

from application.ports.document_parser import DocumentParser
from config.settings import Settings
from config.ocr_utils import is_ocr_available, is_macos
from domain.models import ParsedDocument


logger = logging.getLogger(__name__)


class _DoclingPDFEngine:
    """Encapsulates Docling configuration for a given table/OCR strategy."""

    def __init__(self, *, use_tables: bool, use_ocr: bool) -> None:
        self._use_tables = use_tables
        # Respect requested use_ocr but disable it gracefully if no OCR
        # backend is available on this host (e.g. Linux without tesseract).
        if use_ocr and not is_ocr_available():
            logger.warning(
                "OCR requested but no OCR backend detected on this host — disabling OCR pass"
            )
            self._use_ocr = False
        else:
            self._use_ocr = use_ocr
        self._primary_converter = self._create_converter(
            do_cell_matching=True,
            images_scale=2.0,
            description="primary",
        )
        self._fallback_converter = self._create_converter(
            do_cell_matching=False,
            images_scale=3.0,
            description="fallback",
        )

    def _create_converter(
        self,
        *,
        do_cell_matching: bool,
        images_scale: float,
        description: str,
    ) -> DocumentConverter:
        pipeline_options = PdfPipelineOptions()

        if self._use_ocr:
            pipeline_options.do_ocr = True

        if self._use_tables:
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = do_cell_matching
            pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE

        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = images_scale

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                ),
            }
        )
        logger.debug(
            "Docling converter prepared (%s) cell_matching=%s images_scale=%.1f",
            description,
            do_cell_matching,
            images_scale,
        )
        return converter

    def parse_pdf(self, file_path: str) -> str | None:
        primary_markdown = self._convert(self._primary_converter, file_path, label="primary")
        fallback_markdown = self._convert(self._fallback_converter, file_path, label="fallback")
        return self._select_markdown(Path(file_path).name, primary_markdown, fallback_markdown)

    def _convert(self, converter: DocumentConverter, file_path: str, *, label: str) -> str | None:
        result = converter.convert(file_path)
        if result.status != ConversionStatus.SUCCESS:
            logger.warning("Docling conversion error (%s) for %s: %s", label, file_path, result.status)
            return None

        document = result.document
        markdown = document.export_to_markdown()
        preview = markdown[:2000]
        logger.debug("Docling %s preview for %s:\n%s", label, Path(file_path).name, preview)
        return markdown

    @staticmethod
    def _table_score(markdown: str | None) -> int:
        if not markdown:
            return 0
        return markdown.count("|")

    def _select_markdown(
        self,
        file_name: str,
        primary_markdown: str | None,
        fallback_markdown: str | None,
    ) -> str | None:
        if primary_markdown and not fallback_markdown:
            return primary_markdown
        if fallback_markdown and not primary_markdown:
            logger.info("Docling fallback markdown selected for %s", file_name)
            return fallback_markdown
        if not primary_markdown and not fallback_markdown:
            return None

        primary_score = self._table_score(primary_markdown)
        fallback_score = self._table_score(fallback_markdown)

        if fallback_score > primary_score:
            logger.info(
                "Docling fallback markdown chosen for %s (score %s vs %s)",
                file_name,
                fallback_score,
                primary_score,
            )
            return fallback_markdown

        return primary_markdown


class _DoclingVlmEngine:
    """Encapsulates a VLM-backed Docling configuration (Granite MLX)."""

    def __init__(self, vlm_options, use_tables: bool = True, use_ocr: bool = True) -> None:
        # vlm_options is expected to be a copy already (caller should copy to avoid
        # shared mutation across cached entries). Store as-is.
        self._vlm_options = vlm_options
        self._use_tables = use_tables
        self._use_ocr = use_ocr
        self._converter = self._create_converter()

    def _create_converter(self) -> DocumentConverter:
        pipeline_options = VlmPipelineOptions(vlm_options=self._vlm_options)

        # Note: VlmPipelineOptions does not expose PDF-specific flags such as
        # `do_ocr` or `do_table_structure`. Those are part of `PdfPipelineOptions`.
        # The VLM pipeline works differently: it can generate structured output
        # directly from the VLM, or rely on backend text when `force_backend_text`
        # is enabled. We avoid setting non-existent fields here to remain
        # compatible with installed docling versions.

        # Keep image generation settings; VLM pipeline often benefits from larger scale
        # (these can be tuned in the vlm spec if needed).
        pipeline_options.generate_picture_images = True

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline,
                    pipeline_options=pipeline_options,
                ),
            }
        )
        logger.info(
            "Docling VLM converter prepared (repo=%s framework=%s)",
            getattr(self._vlm_options, "repo_id", "unknown"),
            getattr(self._vlm_options, "inference_framework", "unknown"),
        )
        return converter

    def parse_pdf(self, file_path: str) -> str | None:
        result = self._converter.convert(file_path)
        if result.status != ConversionStatus.SUCCESS:
            logger.warning("Docling VLM conversion error for %s: %s", file_path, result.status)
            return None

        document = result.document
        markdown = document.export_to_markdown()
        preview = markdown[:2000]
        logger.debug("Docling VLM preview for %s:\n%s", Path(file_path).name, preview)
        return markdown


class DoclingDocumentParser(DocumentParser):
    """Concrete parser backed by Docling."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @lru_cache(maxsize=4)
    def _get_engine(self, use_tables: bool, use_ocr: bool) -> _DoclingPDFEngine:
        logger.info("Initializing Docling engine tables=%s ocr=%s", use_tables, use_ocr)
        return _DoclingPDFEngine(use_tables=use_tables, use_ocr=use_ocr)

    @lru_cache(maxsize=8)
    def _get_vlm_engine(
        self,
        model_key: str,
        use_tables: bool = True,
        use_ocr: bool = True,
        force_backend_text: bool = False,
    ) -> _DoclingVlmEngine:
        if model_key != "granite_docling_mlx":
            raise ValueError(f"Unsupported VLM model key: {model_key}")
        # Choose an appropriate base VLM spec depending on the host OS.
        # On macOS we prefer the MLX-backed Granite spec; on other systems
        # prefer a transformers-backed spec when available.
        try:
            if is_macos():
                base_spec = getattr(vlm_model_specs, "GRANITEDOCLING_MLX")
            else:
                # Prefer GRANITEDOCLING_TRANSFORMERS on non-macOS if present,
                # otherwise fall back to the MLX spec (we will attempt to
                # switch frameworks later if needed).
                base_spec = getattr(vlm_model_specs, "GRANITEDOCLING_TRANSFORMERS", None) or getattr(
                    vlm_model_specs, "GRANITEDOCLING_MLX"
                )
        except Exception:  # pragma: no cover - defensive fallback
            base_spec = getattr(vlm_model_specs, "GRANITEDOCLING_MLX")

        tuned_options = base_spec.model_copy()
        # Tweak prompt and scale for better markdown fidelity. Keep changes minimal.
        tuned_options.prompt = (
            "Convert this page to markdown. Preserve ALL text, keep reading order top-to-bottom, left-to-right. "
            "Keep tables as Markdown tables; do not summarize or omit any rows/columns. Do not invent content. "
            "Output only markdown."
        )
        tuned_options.scale = 2.8

        # Safely set generation config (different VLM option implementations may
        # expose generation config as a dict). Prefer updating `generation_config`
        # if present, otherwise set attribute defensively.
        try:
            gen = dict(getattr(tuned_options, "generation_config", {}) or {})
            gen.update({"max_new_tokens": 8192})
            tuned_options.generation_config = gen
        except Exception:  # pragma: no cover - defensive fallback
            # Some versions may expose a direct attribute; attempt to set it but
            # don't fail conversion if attribute absent.
            try:
                setattr(tuned_options, "max_new_tokens", 8192)
            except Exception:
                logger.debug("Could not set max_new_tokens on tuned_options; skipping")

        # Normalize VLM options for the current platform. On non-macOS hosts
        # prefer transformers and strip MLX-specific repo suffixes when
        # possible to avoid attempting to load native MLX libraries.
        def _normalize_vlm_options_for_platform(opts) -> None:
            try:
                if not is_macos():
                    if getattr(opts, "inference_framework", None) == "mlx":
                        try:
                            opts.inference_framework = "transformers"
                            logger.info(
                                "Non-macOS detected: switching Granite VLM inference_framework to 'transformers'"
                            )
                        except Exception:
                            logger.debug("Unable to set inference_framework on tuned_options")

                    try:
                        repo_id = getattr(opts, "repo_id", None)
                        if repo_id and isinstance(repo_id, str) and repo_id.endswith("-mlx"):
                            new_repo = repo_id[:-4]
                            opts.repo_id = new_repo
                            logger.info(
                                "Non-macOS detected: switching Granite VLM repo_id from %s to %s",
                                repo_id,
                                new_repo,
                            )
                    except Exception:
                        logger.debug("Unable to adjust repo_id on tuned_options")

            except Exception:
                logger.debug("Error while normalizing VLM options for platform")

        _normalize_vlm_options_for_platform(tuned_options)

        # Optionally ask the VLM to prefer backend OCR text as a basis for its
        # output. This enables a hybrid post-processing pattern where a robust
        # OCR + TableFormer pass is performed first and then the VLM corrects
        # and restructures the backend text.
        try:
            if force_backend_text:
                # Some VLM option implementations expose `force_backend_text`.
                setattr(tuned_options, "force_backend_text", True)
                logger.info("Configured tuned VLM options to force_backend_text=True")
        except Exception:
            logger.debug("Could not set force_backend_text on tuned_options; continuing without it")

        # Return engine configured according to requested flags.
        return _DoclingVlmEngine(tuned_options, use_tables=use_tables, use_ocr=use_ocr)

    def parse_many(
        self,
        file_paths: list[str],
        *,
        use_tables: bool = True,
        use_ocr: bool = True,
        pipeline: str | None = None,
    ) -> list[ParsedDocument]:
        pipeline_name = (pipeline or self._settings.docling_pipeline or "standard").lower()
        use_vlm = pipeline_name.startswith("vlm") or "granite" in pipeline_name

        logger.info("Docling parser using pipeline=%s", pipeline_name)

        results: list[ParsedDocument] = []

        for file_path in file_paths:
            filename = Path(file_path).name
            try:
                markdown: str | None = None

                if use_vlm:
                    # Hybrid flow: for scanned PDFs and table extraction we run
                    # a robust Pdf pipeline first (OCR + TableFormer) and then
                    # run the VLM as a post-processor with
                    # force_backend_text=True so it can correct/structure the
                    # backend OCR text. We then pick the better output based on
                    # a simple table-score heuristic.
                    if use_ocr or use_tables:
                        logger.info(
                            "Hybrid pipeline: running OCR+TableFormer then VLM post-process for %s",
                            filename,
                        )

                        # Ensure we run PDF pipeline with OCR and table structure
                        pdf_engine = self._get_engine(use_tables=True, use_ocr=True)
                        primary_markdown = pdf_engine.parse_pdf(file_path)

                        # Run VLM post-process which is instructed to prefer the
                        # backend text produced by OCR.
                        vlm_engine = self._get_vlm_engine(
                            "granite_docling_mlx",
                            use_tables=use_tables,
                            use_ocr=use_ocr,
                            force_backend_text=True,
                        )
                        try:
                            vlm_markdown = vlm_engine.parse_pdf(file_path)
                        except Exception as e:
                            # If the VLM post-processing fails (for example due
                            # to model shape mismatch or missing native libs),
                            # log and fall back to the primary OCR+TableFormer
                            # markdown instead of failing the whole conversion.
                            logger.warning(
                                "VLM post-processing failed for %s: %s — falling back to primary markdown",
                                filename,
                                e,
                            )
                            vlm_markdown = None

                        # Choose best output: prefer VLM if it preserved/produced
                        # at least as many table markers as the OCR pass.
                        primary_score = _DoclingPDFEngine._table_score(primary_markdown)
                        vlm_score = _DoclingPDFEngine._table_score(vlm_markdown)

                        if vlm_markdown and vlm_score >= primary_score:
                            markdown = vlm_markdown
                            logger.info("Hybrid: selected VLM post-processed markdown for %s", filename)
                        else:
                            markdown = primary_markdown
                            logger.info("Hybrid: selected primary OCR+Table markdown for %s", filename)
                    else:
                        # Simple VLM-only flow (no OCR/tables requested)
                        vlm_engine = self._get_vlm_engine(
                            "granite_docling_mlx", use_tables=use_tables, use_ocr=use_ocr
                        )
                        markdown = vlm_engine.parse_pdf(file_path)
                else:
                    # Standard PDF-only flow
                    pdf_engine = self._get_engine(use_tables, use_ocr)
                    markdown = pdf_engine.parse_pdf(file_path)

                if markdown is None:
                    results.append(
                        ParsedDocument(
                            filename=filename,
                            status="failed",
                            error="Failed to parse document",
                        )
                    )
                else:
                    results.append(
                        ParsedDocument(
                            filename=filename,
                            status="success",
                            markdown=markdown,
                        )
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Docling parsing failure for %s", filename)
                results.append(
                    ParsedDocument(
                        filename=filename,
                        status="failed",
                        error=str(exc),
                    )
                )

        return results