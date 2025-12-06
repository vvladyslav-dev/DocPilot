"""Streamlit UI for the DocPilot application built with Clean Architecture."""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from io import BytesIO
from typing import Iterable

import pandas as pd
import sys
import streamlit as st
from mediatr import Mediator

import application.usecases as usecases_pkg
from application.usecases.build_default_table import BuildDefaultTableRequest
from application.usecases.cleanup_uploads import CleanupUploadsRequest
from application.usecases.extract_table import ExtractTableRequest
from application.usecases.parse_documents import ParseDocumentsRequest
from application.usecases.save_uploaded_files import SaveUploadedFilesRequest
from config.container import Container
from config.settings import Settings
from domain import ExtractionResult, ParsedDocument, UploadedFilePayload


DEFAULT_LLM_INSTRUCTION = (
    "Extract all"
)


def _import_all_submodules(package) -> None:
    """Import all submodules to register Mediator handlers."""

    for module_info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(module_info.name)


_import_all_submodules(usecases_pkg)

container = Container()
container.init_resources()
container.wire(packages=[usecases_pkg])
settings: Settings = container.settings()


def _run_usecase(request):
    """Execute a Mediator use case synchronously."""

    coroutine = Mediator.send_async(request)
    try:
        return asyncio.run(coroutine)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()


def _documents_success(documents: Iterable[ParsedDocument]) -> list[ParsedDocument]:
    return [document for document in documents if document.status == "success"]


def _result_to_dataframe(result: ExtractionResult | None) -> pd.DataFrame | None:
    if result is None or not result.rows:
        return None
    return pd.DataFrame(result.rows, columns=result.columns)


def initialize_session_state() -> None:
    """Initialize Streamlit session state for the application."""

    defaults = {
        "stored_documents": [],
        "parsed_documents": [],
        "extraction_result": None,
        "upload_failures": [],
        "user_instruction": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


st.set_page_config(
    page_title="DocPilot",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    button[data-testid="stDataFrameDownloadButton"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    """Main application function."""

    initialize_session_state()

    st.title("📄 DocPilot")
    st.markdown(
        "DocPilot — batch document processor. Upload a batch of PDFs, automatically parse and extract structured data; invoices are one example. Use the sidebar to choose document type and extraction instructions."
    )

    with st.sidebar:
        st.header("⚙️ Settings")

        st.subheader("1️⃣ File Upload")
        uploaded_files = st.file_uploader(
            "Upload PDF files",
            type=[extension.lstrip(".") for extension in settings.supported_formats],
            accept_multiple_files=True,
            help=(
                f"Maximum {settings.max_files_upload} files, up to {settings.max_file_size_mb} MB each"
            ),
        )

        if uploaded_files:
            st.success(f"✅ Uploaded files: {len(uploaded_files)}")

        # Extraction instruction UI removed — use default extraction or configure
        # extraction instruction programmatically via application settings or
        # downstream LLM configuration. The `user_instruction` session state
        # remains available if templates are added later.

        st.subheader("🔑 Gemini API Key")
        gemini_key = (settings.gemini_api_key or "").strip()
        if gemini_key:
            st.success("GOOGLE_API_KEY loaded from environment.")
        else:
            st.warning(
                "GOOGLE_API_KEY not set. Configure it as an environment variable to enable LLM extraction."
            )
        gemini_model = st.text_input(
            "Gemini Model",
            value=settings.gemini_model,
            help="Example: gemini-1.5-flash. Specify current available model if needed.",
        )

        st.subheader("🧠 Docling Pipeline")
        # Allow the user to choose Granite on any host; the app will auto-switch
        # the VLM inference framework depending on the detected platform.
        pipeline_options = [
            "Standard (TableFormer + OCR)",
            "Granite (LLM-based VLM + OCR)",
        ]

        pipeline_help = (
            "Standard: fast, uses TableFormer + OCR. "
            "Granite: an LLM-backed VLM pipeline that runs a hybrid flow — a robust OCR+TableFormer pass is executed first and then the VLM post-processes the backend text.\n"
            "The application will automatically pick an appropriate VLM backend: MLX on macOS, and "
            "transformers on non-macOS (Linux) hosts."
        )

        pipeline_label = st.selectbox(
            "Choose Docling pipeline",
            options=pipeline_options,
            index=0 if settings.docling_pipeline.lower() == "standard" else 1,
            help=pipeline_help,
        )

        # Show which backend will be used for Granite on this host
        if "Granite" in pipeline_label:
            backend = "mlx (MLX)" if sys.platform == "darwin" else "transformers"
            st.info(f"Selected Granite — the app will use {backend} as the VLM backend on this host.")
        # Keep backward-compatible pipeline_value mapping based on selected label
        pipeline_value = "vlm_granite_mlx" if "Granite" in pipeline_label else "standard"

        parse_button = st.button("🚀 Parse Files", use_container_width=True, type="primary")

        if st.button("🗑️ Clear Data", use_container_width=True):
            _run_usecase(CleanupUploadsRequest())
            for key in ("stored_documents", "parsed_documents", "extraction_result", "upload_failures"):
                st.session_state[key] = [] if key.endswith("s") else None
            st.session_state.user_instruction = ""
            st.success("✅ Data cleared")
            st.experimental_rerun()

    if parse_button and uploaded_files:
        with st.spinner("⏳ Parsing documents and extracting..."):
            try:
                st.info(f"📂 Step 1/4: Saving {len(uploaded_files)} files...")
                payloads = [
                    UploadedFilePayload(
                        filename=file.name,
                        data=file.getvalue(),
                        content_type=file.type,
                    )
                    for file in uploaded_files
                ]

                save_response = _run_usecase(SaveUploadedFilesRequest(files=payloads))
                st.session_state.upload_failures = save_response.failures
                stored_documents = save_response.stored_documents

                for document in stored_documents:
                    st.write(f"  ✅ Saved: {document.filename}")

                if save_response.failures:
                    for failure in save_response.failures:
                        st.warning(f"  ⚠️ {failure.filename}: {failure.reason}")

                if not stored_documents:
                    st.error("❌ No files saved after validation")
                    return

                st.session_state.stored_documents = stored_documents

                pipeline_desc = (
                    "Docling Standard Pipeline + OCR"
                    if pipeline_value == "standard"
                    else "Docling Granite (LLM-based VLM) — hybrid: OCR+TableFormer then VLM post-process"
                )
                st.info(
                    f"📄 Step 2/4: Parsing {len(stored_documents)} PDFs via {pipeline_desc}..."
                )
                parse_response = _run_usecase(
                    ParseDocumentsRequest(
                        documents=stored_documents,
                        use_tables=settings.docling_use_tables,
                        use_ocr=settings.docling_use_ocr,
                        pipeline=pipeline_value,
                    )
                )
                st.session_state.parsed_documents = parse_response.documents

                for document in parse_response.documents:
                    if document.status == "success" and document.markdown:
                        st.write(
                            f"  ✅ {document.filename}: {len(document.markdown)} characters extracted"
                        )
                    else:
                        st.write(
                            f"  ❌ {document.filename}: {document.error or 'Unknown error'}"
                        )

                user_instruction = (st.session_state.user_instruction or "").strip()

                successes = len(_documents_success(parse_response.documents))
                failures = len(parse_response.documents) - successes

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Documents", len(parse_response.documents))
                with col2:
                    st.metric("✅ Successful", successes, delta=f"-{failures}" if failures else None)
                with col3:
                    st.metric("❌ Errors", failures)

                if gemini_key:
                    instruction = user_instruction or DEFAULT_LLM_INSTRUCTION
                    if user_instruction:
                        st.info("🤖 Step 3/4: Extracting table via Gemini...")
                    else:
                        st.info(
                            "🤖 Step 3/4: Instruction not provided — defaulting to 'extract all' via Gemini."
                        )
                    extract_response = _run_usecase(
                        ExtractTableRequest(
                            documents=parse_response.documents,
                            instruction=instruction,
                            api_key=gemini_key,
                            model_name=gemini_model,
                        )
                    )
                    st.session_state.extraction_result = extract_response.result
                    st.success("✅ LLM extraction completed")
                else:
                    st.warning("⚠️ Gemini API key not specified in environment")
                    st.info(
                        "⚠️ Step 3/4: Gemini unavailable - creating default table with raw data"
                    )
                    default_response = _run_usecase(
                        BuildDefaultTableRequest(documents=parse_response.documents)
                    )
                    st.session_state.extraction_result = default_response.result

            except Exception as exc:  # pragma: no cover - defensive
                st.error(f"❌ Processing error: {exc}")

    parsed_documents: list[ParsedDocument] = st.session_state.parsed_documents
    extraction_result: ExtractionResult | None = st.session_state.extraction_result

    if parsed_documents:
        st.divider()
        st.subheader("📊 Parsing Results")

        table_tab, details_tab, export_tab = st.tabs(["Table", "Details", "Export"])

        with table_tab:
            df = _result_to_dataframe(extraction_result)
            if df is not None:
                st.dataframe(df, use_container_width=True, height=400)
            else:
                st.info(
                    "No table generated yet. Run the parser to produce a table (LLM extraction requires configured API key)."
                )

        with details_tab:
            filenames = [document.filename for document in parsed_documents]
            if not filenames:
                st.info("No documents parsed yet.")
            else:
                selected_file = st.selectbox("Select file to view details", options=filenames)
                document = next(doc for doc in parsed_documents if doc.filename == selected_file)
                if document.status == "success" and document.markdown:
                    st.text_area(
                        "Markdown excerpt",
                        document.markdown[:4000],
                        height=300,
                    )
                else:
                    st.error(document.error or "Unknown parsing error")

        with export_tab:
            df = _result_to_dataframe(extraction_result)
            if df is None or df.empty:
                st.info("No data to export. Perform LLM extraction first.")
            else:
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                buffer = BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")

                csv_col, xlsx_col = st.columns(2)
                with csv_col:
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv_bytes,
                        file_name="docpilot_results.csv",
                        mime="text/csv",
                        use_container_width=True,
                        type="secondary",
                    )
                with xlsx_col:
                    st.download_button(
                        label="📥 Download XLSX",
                        data=buffer.getvalue(),
                        file_name="docpilot_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        type="primary",
                    )

    with st.expander("ℹ️ Application Information"):
        st.markdown(
            f"""
            **DocPilot** — batch document processor.

            ### Features:
            - 📄 Upload multiple PDF files
            - 🤖 Automatic data extraction using Docling AI
            - 🔍 OCR support for scanned documents
            - 📊 Export results to CSV/XLSX
            - 💾 Save parsing history

            "### How to use:
            1. Upload PDF files in the sidebar
            2. (optional) Provide extraction instructions via configuration or templates (LLM)
            3. Choose export format
            4. Click \"Parse Files\"
            5. Download results in the selected format

            ### Limitations:
            - Maximum {settings.max_files_upload} files at once
            - Maximum file size: {settings.max_file_size_mb} MB
            - Supported formats: {", ".join(settings.supported_formats)}
            """
        )


if __name__ == "__main__":
    main()
