import os
import tempfile
from pathlib import Path
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import pymupdf
from highlighter import process_pdf

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB
CORS(app, resources={r"/*": {"origins": "*"}})  # Restrict to GitHub Pages URL after deployment.

@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'Sreedhars_MT_PDF_Solver'})

@app.post('/process')
def process():
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return jsonify({'error': 'Please choose one PDF file.'}), 400
    if not uploaded.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are accepted.'}), 400

    with tempfile.TemporaryDirectory(prefix='sreedhars_pdf_') as temp_dir:
        input_path = Path(temp_dir) / 'input.pdf'
        uploaded.save(input_path)
        # Check PDF signature before handing it to PyMuPDF.
        with input_path.open('rb') as f:
            if f.read(5) != b'%PDF-':
                return jsonify({'error': 'The uploaded file is not a valid PDF.'}), 400
        try:
            with pymupdf.open(str(input_path)) as check_doc:
                page_count = len(check_doc)
                if page_count < 1:
                    return jsonify({'error': 'The PDF is empty.'}), 400
                if page_count > 20:
                    return jsonify({'error': f'The PDF has {page_count} pages. Maximum allowed is 20.'}), 400
            output_path = process_pdf(input_path)
            download_name = Path(uploaded.filename).stem + ' with answers.pdf'
            return send_file(output_path, as_attachment=True, download_name=download_name, mimetype='application/pdf')
        except Exception as exc:
            app.logger.exception('PDF processing failed')
            return jsonify({'error': f'Could not process this PDF: {type(exc).__name__}: {exc}'}), 422

@app.errorhandler(413)
def too_large(_error):
    return jsonify({'error': 'File is too large. Maximum upload size is 20 MB.'}), 413

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
