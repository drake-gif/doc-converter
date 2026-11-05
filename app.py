import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

# ---- Supported formats -------------------------------------------------
DOC_EXT = {"doc", "docx", "odt", "rtf", "txt", "html", "htm"}
SHEET_EXT = {"xls", "xlsx", "ods", "csv"}
SLIDE_EXT = {"ppt", "pptx", "odp"}
IMAGE_EXT = {"png", "jpg", "jpeg", "bmp", "gif", "webp", "tiff", "tif"}
OFFICE_EXT = DOC_EXT | SHEET_EXT | SLIDE_EXT

# LibreOffice export filters per category
EXPORT = {
    "doc": {"pdf": "pdf", "docx": "docx:MS Word 2007 XML", "doc": "doc:MS Word 97",
            "odt": "odt:writer8", "rtf": "rtf:Rich Text Format",
            "txt": "txt:Text (encoded):UTF8", "html": "html:HTML (StarWriter)"},
    "sheet": {"pdf": "pdf", "xlsx": "xlsx:Calc MS Excel 2007 XML", "xls": "xls:MS Excel 97",
              "ods": "ods:calc8", "csv": "csv:Text - txt - csv (StarCalc)",
              "html": "html:HTML (StarCalc)"},
    "slide": {"pdf": "pdf", "pptx": "pptx:Impress MS PowerPoint 2007 XML",
              "ppt": "ppt:MS PowerPoint 97", "odp": "odp:impress8"},
}
IMAGE_TARGETS = ["pdf", "png", "jpg", "webp", "bmp", "gif", "tiff"]
PDF_TARGETS = ["docx", "odt", "rtf", "txt", "html", "xlsx", "png", "jpg"]
ALIAS = {"jpeg": "jpg", "tif": "tiff", "htm": "html"}


def norm(ext):
    return ALIAS.get(ext, ext)


def category(ext):
    if ext in DOC_EXT:
        return "doc"
    if ext in SHEET_EXT:
        return "sheet"
    return "slide"


def build_targets():
    t = {"pdf": PDF_TARGETS}
    for ext in IMAGE_EXT:
        t[ext] = [x for x in IMAGE_TARGETS if x != norm(ext)]
    for ext in OFFICE_EXT:
        opts = list(EXPORT[category(ext)]) + ["png", "jpg"]
        t[ext] = [x for x in opts if x != norm(ext)]
    return t


TARGETS = build_targets()


# ---- Converters --------------------------------------------------------
def find_soffice():
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if Path(p).exists():
            return p
    return None


def office_convert(src: Path, out_dir: Path, target: str, cat: str) -> Path:
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice is not installed. Install it from libreoffice.org.")
    cmd = [soffice, f"-env:UserInstallation={(out_dir / 'lo_profile').as_uri()}", "--headless"]
    if src.suffix.lower() in (".html", ".htm"):
        cmd.append("--infilter=HTML (StarWriter)")
    cmd += ["--convert-to", EXPORT[cat][target], "--outdir", str(out_dir), str(src)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    result = out_dir / f"{src.stem}.{target}"
    if not result.exists():
        raise RuntimeError("Conversion failed.")
    return result


def image_convert(src: Path, out_dir: Path, target: str) -> Path:
    from PIL import Image
    fmt = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "bmp": "BMP",
           "gif": "GIF", "tiff": "TIFF", "pdf": "PDF"}[target]
    result = out_dir / f"{src.stem}.{target}"
    with Image.open(src) as img:
        if target in ("jpg", "bmp", "pdf") or img.mode not in ("RGB", "RGBA", "L", "P"):
            img = img.convert("RGB")
        img.save(result, fmt, **({"resolution": 150} if target == "pdf" else {}))
    return result


def pdf_to_docx(src: Path, out_dir: Path) -> Path:
    from pdf2docx import Converter
    result = out_dir / f"{src.stem}.docx"
    cv = Converter(str(src))
    try:
        cv.convert(str(result))
    finally:
        cv.close()
    return result


def pdf_to_text(src: Path, out_dir: Path, as_html=False) -> Path:
    import fitz  # PyMuPDF
    result = out_dir / f"{src.stem}.{'html' if as_html else 'txt'}"
    with fitz.open(src) as doc:
        parts = [page.get_text("html" if as_html else "text") for page in doc]
    result.write_text("\n".join(parts), encoding="utf-8")
    return result


def pdf_to_xlsx(src: Path, out_dir: Path) -> Path:
    import fitz
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    with fitz.open(src) as doc:
        for i, page in enumerate(doc, 1):
            ws = wb.create_sheet(f"Page {i}")
            tables = page.find_tables().tables
            if tables:  # real tables -> cells
                for t in tables:
                    for row in t.extract():
                        ws.append(["" if c is None else c for c in row])
                    ws.append([])
            else:  # no tables -> one text line per row
                for line in page.get_text().splitlines():
                    ws.append([line])
    result = out_dir / f"{src.stem}.xlsx"
    wb.save(result)
    return result


def pdf_to_images(src: Path, out_dir: Path, fmt: str) -> Path:
    import fitz
    files = []
    with fitz.open(src) as doc:
        for i, page in enumerate(doc, 1):
            f = out_dir / f"{src.stem}_page{i}.{fmt}"
            page.get_pixmap(dpi=150).save(f)
            files.append(f)
    if len(files) == 1:
        return files[0]
    zpath = out_dir / f"{src.stem}_{fmt}_pages.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    return zpath


def convert(src: Path, ext: str, target: str, out_dir: Path) -> Path:
    if ext == "pdf":
        if target == "docx":
            return pdf_to_docx(src, out_dir)
        if target in ("odt", "rtf"):
            return office_convert(pdf_to_docx(src, out_dir), out_dir, target, "doc")
        if target == "txt":
            return pdf_to_text(src, out_dir)
        if target == "html":
            return pdf_to_text(src, out_dir, as_html=True)
        if target == "xlsx":
            return pdf_to_xlsx(src, out_dir)
        if target in ("png", "jpg"):
            return pdf_to_images(src, out_dir, target)
    elif ext in IMAGE_EXT:
        return image_convert(src, out_dir, target)
    elif ext in OFFICE_EXT:
        if target in ("png", "jpg"):  # office -> pdf -> page images
            pdf = office_convert(src, out_dir, "pdf", category(ext))
            return pdf_to_images(pdf, out_dir, target)
        return office_convert(src, out_dir, target, category(ext))
    raise ValueError("Unsupported conversion.")


# ---- Routes ------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", targets=TARGETS)


@app.route("/health")
def health():
    return jsonify(status="ok", libreoffice=bool(find_soffice()))


@app.route("/convert", methods=["POST"])
def convert_route():
    file = request.files.get("file")
    target = request.form.get("target", "").lower()
    if not file or not file.filename:
        return jsonify(error="Please choose a file."), 400

    name = secure_filename(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if target not in TARGETS.get(ext, []):
        return jsonify(error=f"Cannot convert .{ext} to .{target}."), 400

    tmp = Path(tempfile.mkdtemp())
    try:
        src = tmp / name
        file.save(src)
        out = convert(src, ext, target, tmp)
        data, out_name = out.read_bytes(), out.name
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return send_file(io.BytesIO(data), as_attachment=True, download_name=out_name)


if __name__ == "__main__":
    # Local: python app.py -> http://127.0.0.1:5000
    # Online: set HOST=0.0.0.0 and DEBUG=0, or use the Dockerfile + gunicorn
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("DEBUG", "1") == "1")
