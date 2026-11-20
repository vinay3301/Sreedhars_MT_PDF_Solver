import os
import json
import base64
import tempfile
import threading
import queue
from pathlib import Path

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import pymupdf
from highlighter import process_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB
CORS(app, resources={r"/*": {"origins": "*"}})  # Restrict to GitHub Pages URL if desired.


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "Sreedhars_MT_PDF_Solver"})


@app.post("/process")
def process():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Please choose one PDF file."}), 400
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are accepted."}), 400

    original_name = Path(uploaded.filename).name
    download_name = Path(original_name).stem + " with answers.pdf"
    events = queue.Queue()

    def worker():
        try:
            with tempfile.TemporaryDirectory(prefix="sreedhars_pdf_") as temp_dir:
                input_path = Path(temp_dir) / "input.pdf"
                uploaded.save(input_path)
                events.put({"type": "log", "message": "Upload received. Checking the PDF..."})

                with input_path.open("rb") as f:
                    if f.read(5) != b"%PDF-":
                        raise ValueError("The uploaded file is not a valid PDF.")

                with pymupdf.open(str(input_path)) as check_doc:
                    page_count = len(check_doc)
                    if page_count < 1:
                        raise ValueError("The PDF is empty.")
                    if page_count > 20:
                        raise ValueError(
                            f"The PDF has {page_count} pages. Maximum allowed is 20."
                        )

                events.put({"type": "log", "message": f"PDF validated: {page_count} page(s)."})
                output_path = process_pdf(
                    input_path,
                    progress_callback=lambda message: events.put(
                        {"type": "log", "message": str(message)}
                    ),
                )

                pdf_bytes = output_path.read_bytes()
                events.put({
                    "type": "complete",
                    "filename": download_name,
                    "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                })
        except Exception as exc:
            app.logger.exception("PDF processing failed")
            events.put({
                "type": "error",
                "message": f"Could not process this PDF: {type(exc).__name__}: {exc}",
            })
        finally:
            events.put(None)

    def generate():
        yield json.dumps({
            "type": "log",
            "message": "Starting PDF processing. Please keep this page open."
        }) + "\n"

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            event = events.get()
            if event is None:
                break
            yield json.dumps(event, separators=(",", ":")) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "File is too large. Maximum upload size is 20 MB."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
