# Sreedhar's Institute – Model Test PDF Solver

A web-based PDF answer highlighter designed specifically for **Sreedhar's Institute Model Test question papers**.

Upload a question paper PDF, generate a solution PDF, and automatically highlight the correct answer options. The application also identifies questions that need manual review without stopping the entire processing operation.

## Features

- **Simple web interface:** Upload and process PDFs directly from a website.
- **Automatic answer-key detection:** Extracts the answer key from the last page of the question paper.
- **Automatic answer highlighting:** Highlights matched correct options in green.
- **Manual review highlighting:** Marks detected options in yellow when the correct option cannot be matched automatically.
- **Live processing log:** Displays detailed processing steps in the browser, similar to the Google Colab output.
- **Page-by-page updates:** Shows which PDF pages have been processed.
- **Cross-check reporting:** Displays answer-key validation results and questions requiring manual review.
- **Automatic PDF download:** Generates and downloads the solution PDF.
- **Temporary file processing:** Uploaded PDFs and generated files are stored temporarily during processing and are not retained as permanent user files.

## Usage

1. Open the Model Test PDF Solver website.
2. Select a Sreedhar's Institute Model Test question paper in PDF format.
3. Click **Generate Solution PDF**.
4. Follow the live processing log to monitor progress.
5. Once processing is complete, the solution PDF will be downloaded automatically.

The output filename follows this format:

`Original_File_Name with answers.pdf`

## PDF Upload Requirements

| Requirement | Limit |
|---|---|
| File format | PDF only |
| PDFs per request | One |
| Maximum pages | 20 |
| Maximum file size | 20 MB |
| Answer key | Expected on the last page |
| PDF text | Extractable text required |

**Note:** Image-only or scanned PDFs requiring OCR are not supported. The application is designed for Sreedhar's Institute Model Test PDFs.

## Highlighting System

| Highlight colour | Meaning |
|---|---|
| Green | Correct answer successfully matched with the answer key |
| Yellow | Question requires manual review because the correct option could not be matched automatically |

A failed answer-key cross-check does not stop the entire processing operation. The application continues generating the solution PDF and marks detected options requiring review in yellow.

## Live Processing Log

The website displays real processing messages from the Python backend, including:

- PDF upload and validation.
- Answer-key extraction.
- Number of answers detected.
- Page-by-page processing updates.
- Correct-option matching.
- Answer-key cross-check results.
- Questions requiring manual review.
- Green and yellow highlight counts.
- Solution PDF generation and download status.

These messages are generated during actual processing rather than being simulated progress updates.

## Project File Structure

The repository contains the following files:

| File | Purpose |
|---|---|
| `index.html` | Frontend website. Provides the PDF upload interface, displays the live processing log, communicates with the backend API, and downloads the generated solution PDF. |
| `app.py` | Flask backend application. Handles PDF uploads, validates file type, size and page count, provides the health-check endpoint, streams processing updates, and returns the completed PDF. |
| `highlighter.py` | Core PDF-processing engine. Extracts the answer key, detects question options, matches correct answers, applies green and yellow highlights, performs cross-checking, and generates the solution PDF. |
| `requirements.txt` | Lists the Python dependencies required to run the backend. |
| `Procfile` | Defines the command used by Render to start the Flask application using Gunicorn. |
| `README.md` | Project documentation, features, usage instructions, and deployment information. |

## Technologies Used

### Frontend
- HTML5
- CSS3
- JavaScript
- Fetch API
- Streaming response handling

### Backend
- Python
- Flask
- Flask-CORS
- PyMuPDF
- Gunicorn

### Hosting and Deployment
- GitHub – Source code repository and version control.
- GitHub Pages – Frontend website hosting.
- Render – Python backend hosting.

## Application Architecture

The application uses a separate frontend and backend.

1. The user opens the website hosted on GitHub Pages.
2. The user uploads a PDF.
3. The frontend sends the PDF to the Flask backend hosted on Render.
4. The backend validates the PDF and calls the PDF-processing engine.
5. The processing engine extracts the answer key and highlights the correct options.
6. Real-time processing messages are streamed back to the website.
7. The completed solution PDF is returned to the browser for download.

## Deployment

### Frontend – GitHub Pages

The frontend is hosted using GitHub Pages.

Repository:  
https://github.com/vinay3301/Sreedhars_MT_PDF_Solver

### Backend – Render

The Python backend is hosted using Render.

Backend URL:  
https://sreedhars-mt-pdf-solver.onrender.com

Health-check endpoint:  
https://sreedhars-mt-pdf-solver.onrender.com/health

### Automatic Deployment

- Changes committed to the GitHub repository trigger GitHub Pages publishing.
- Changes to backend files trigger a new Render deployment.

## Important Hosting Note

The backend uses Render's free hosting service. When the service has been inactive, it may take some time to start responding to the first request.

If the website displays a connection error on the first attempt after inactivity, wait briefly and try again.

## Privacy and File Handling

- No user login is required.
- PDFs are processed using temporary server-side storage.
- Temporary processing files are automatically cleaned up after processing.
- The application does not maintain a permanent user PDF storage system.

## Project Objective

The objective of this project is to simplify the process of solving Sreedhar's Institute Model Test question papers by automatically identifying correct answers, highlighting them in the original PDF, and generating a downloadable solution document.

---

**Developed for Sreedhar's Institute Model Test PDFs.**
