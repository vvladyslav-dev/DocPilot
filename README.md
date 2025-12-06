# DocPilot — Document Batch Processor

DocPilot is a parser that analyses various PDF documents and returns the structure specified by the user using prompts.

Upload several PDF documents (invoices, receipts, contracts, etc.), specify which fields you want extracted or any filters to apply (e.g., date range, totals > 1000) in the prompt, run the parser, and download the cleaned results as CSV or XLSX.

DocPilot also supports scans and can process low-quality documents.

## Use cases

Below are several practical scenarios that demonstrate the capabilities of the application and show how it can be used in real-world tasks.

- Aggregate analytics — Yearly totals
  - Goal: Upload multiple invoices and obtain the total amount billed in 2025.
  - How to: Upload all PDF files using the uploader, select the fields you need (for example "total" or "amount"), enable parsing and — if desired — the LLM/Granite post-processing to improve extraction. After parsing, export results to CSV/XLSX and apply a date filter for 2025 and sum the `total` column.
  - Example query (when using VLM/LLM post-processing): "Return the total amount billed in 2025 across all uploaded invoices."

- Field extraction by period
  - Goal: Retrieve only specific fields (invoice_number, date, total) for a given period, for example from 2025-01-01 to 2025-06-30.
  - How to: Upload the documents, select the desired fields in the UI or in extraction settings, run the parsing. In the exported CSV/XLSX filter rows to the target date range.
  - Example query: "List invoice_number, date and total for invoices between 2025-01-01 and 2025-06-30."

- Amount-based filtering (e.g. < $1000)
  - Goal: Find all invoices where the invoice total is less than $1000.
  - How to: After parsing, export the table and apply a filter on the `total` column (total < 1000). If you use LLM post-processing, you can also instruct the model to return only such rows.
  - Example query: "Return invoices where total is less than 1000 USD."

- Bulk audit and extraction
  - Goal: Automatically extract fields (vendor, client, invoice_number, date, total, tax) for a large set of PDF files and save them into a single export file for downstream analytics.
  - How to: Upload the batch of files, specify the list of extraction fields in settings, enable Granite if higher accuracy is required, then download the consolidated CSV/XLSX.

These examples illustrate common workflows; you can combine date ranges, filters and export formats according to your needs.

What it does
- Upload multiple PDF documents (batch mode).
- Run a reliable Docling PDF pipeline (OCR + TableFormer in ACCURATE mode) to extract text and table structure.
- Optionally run a Vision‑Language Model (Granite) as a post‑processor to correct and improve structure (hybrid flow: OCR → VLM).
- Export parsed results to CSV or XLSX.

How it works (high level)
1. User uploads PDFs through the Streamlit UI.
2. Docling PDF pipeline runs OCR and TableFormer to recover text and table structure.
3. If the Granite pipeline is selected, the app runs a VLM post‑processing pass that can use backend OCR text (force_backend_text) to refine output.
4. The app chooses the best result (simple heuristic) and returns Markdown, which is later used for extraction and export.


Quick start (local) for Apple Silicon 

1. Clone or open the project folder and switch to it:

```bash
cd "/Users/dev/Desktop/docpilot"
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Note for Apple Silicon: on Macs with Apple M-series chips (M1/M2/etc.) it's recommended to run the app natively on the host (not inside a Linux-based Docker container). Granite/MLX models benefit from native MPS acceleration and will typically run several times faster when executed locally on macOS.

3. Install Python dependencies:

```bash
pip install -r requirements.txt
```

Optional (macOS, MLX acceleration):

```bash
pip install mlx-vlm
```

4. (Optional) Set the Gemini API key for LLM-based extraction:

```bash
export GOOGLE_API_KEY="your_gemini_api_key"
```

5. Run the app:

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.

UI notes
- Sidebar → choose pipeline:
  - "Standard (TableFormer + OCR)" — run only the classical Docling PDF pipeline.
  - "Granite (LLM-based VLM)" — triggers the hybrid flow: OCR + TableFormer first, then VLM post‑process for refinement.

Deployment notes
- MLX (Apple MPS) requires macOS (local Mac or cloud Mac hosts like AWS EC2 Mac / MacStadium). For production, prefer the Transformers/VLLM backend on GPU or a managed inference API (Hugging Face Endpoints) unless you specifically need MLX.
- Store model weights and other artifacts in object storage (S3 / GCS / Azure Blob) and prefetch them to `DOCLING_ARTIFACTS_PATH` on app startup to avoid long cold starts.

Configuration
- `config/settings.py` contains toggles such as `docling_use_ocr`, `docling_use_tables`, and `docling_pipeline`.

### Quick start

1. **Upload PDF files** — use the sidebar uploader to select up to 10 files
2. **Pick extraction fields** — select fields such as invoice_number, dates, totals, vendor, client, or leave blank for the raw parsed table
3. **Choose an export format** — CSV or XLSX
4. **Run parsing** — click `🚀 Parse files`
5. **Download results** — grab the file with `📥 Download results`

## 🏗️ Project structure (example)

```
parser/
├── app.py                     # Streamlit UI and presentation layer
├── application/
│   ├── ports/                 # Clean Architecture contracts (interfaces)
│   └── usecases/              # Mediator-based application services
├── config/
│   ├── container.py           # Dependency Injector container
│   └── settings.py            # Typed configuration object
├── domain/                    # Core business entities (Pydantic models)
├── infrastructure/
│   ├── files/                 # File-system adapters
│   ├── llm/                   # Gemini adapter
│   └── parsers/               # Docling parser implementation
├── data/                      # Persistent storage (created automatically)
├── temp/                      # Working directory for uploads/exports
└── README.md
```

## 🔧 Configuration

All core options live in `config/settings.py` (`Settings` dataclass):

- `max_file_size_mb` — maximum upload size per file (default 50 MB)
- `max_files_upload` — maximum files per batch (default 10)
- `supported_formats` — allowed upload extensions (default `.pdf`)
- `docling_use_tables` / `docling_use_ocr` — Docling parsing defaults
- `gemini_model` / `gemini_api_key` — Gemini invocation defaults
- `uploads_dir`, `exports_dir` — automatically created workspace paths

## 📊 Extracted fields (examples)

Typical fields when processing structured documents. Use these as examples or adapt prompts for other document types:

- **invoice_number / receipt_id** — document identifier
- **date** — document date (issue, due, or payment terms)
- **amount / total** — totals and taxes
- **vendor / merchant** — seller or merchant details
- **client / customer** — customer information

If no extraction fields are specified, the app falls back to returning the parsed table/text produced by Docling.

## 💾 Export formats

### CSV
- Lightweight text format encoded in UTF-8
- Opens in Excel, Google Sheets, or any editor

### XLSX
- Native Microsoft Excel format
- Preserves column typing and is ideal for tabular review

## 🔒 Security

- Uploaded files stay inside the local workspace
- Temporary files clear automatically once processing finishes
- Docling runs locally; no document data is sent to external services

## ⚙️ Advanced capabilities

### OCR for scans

OCR is enabled by default; Docling automatically switches to OCRMac (on macOS) or the configured backend when it detects scanned documents.

### Batch processing

Documents are processed sequentially inside a batch, with dedicated logging for each step (upload → parse → LLM → export).


Ensure dependencies are installed inside the active virtual environment:
```bash
pip install -r requirements.txt
```

### The initial run is slow

Docling downloads and initializes models on first use. Subsequent runs reuse the cache and start faster.

### The parsed table is empty or incomplete

1. Confirm the PDF contains selectable text; scans rely on OCR quality
2. Keep `MAX_FILE_SIZE_MB` within limits for large documents
3. Review the UI logs to see whether the LLM returned empty data; the fallback table should still appear


