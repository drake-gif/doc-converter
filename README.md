📄 Doc Converter

A web app that converts documents, spreadsheets, presentations, images and PDFs between different formats.
Upload a file, pick the output format, download the result.

Supported conversions

 ```
| From   -->                     | To |
                         
| DOC, DOCX, ODT, RTF, TXT, HTML | PDF, DOCX, DOC, ODT, RTF, TXT, HTML, PNG, JPG |
| XLS, XLSX, ODS, CSV            | PDF, XLSX, XLS, ODS, CSV, HTML, PNG, JPG |
| PPT, PPTX, ODP                 | PDF, PPTX, PPT, ODP, PNG, JPG |
| PNG, JPG, WEBP, BMP, GIF, TIFF | PDF and other image formats |
| PDF                            | DOCX, ODT, RTF, TXT, HTML, XLSX, PNG, JPG |
```

Requirements include:
> Python 3.9+
> [LibreOffice](https://www.libreoffice.org/download) (needed for Word, Excel and PowerPoint files conversion)

Run locally
```bash
git clone https://github.com/drake-gif/doc-converter.git
cd doc-converter
python -m venv venv
venv\Scripts\activate          # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

Run with Docker
```bash
docker build -t doc-converter .
docker run -p 8000:8000 doc-converter
```

Technologies
Python, Flask, LibreOffice, PyMuPDF, pdf2docx, Pillow, openpyxl.
