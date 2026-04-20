from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from excel_to_geojson_gui import DATASETS, convert_excel_to_geojson


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "Data"
GEOJSON_DIR = DATA_DIR / "geoJSONs"
MAP_FILE_NAME = "WAIWanaka (1).html"
ALLOWED_EXTENSIONS = {".xlsx"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
GEOJSON_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

DATASET_LABELS = {
    "secchi": "Secchi",
    "stream testing": "Stream Testing",
    "litter intelligence": "Litter Intelligence",
    "microplastics": "Microplastics",
    "gyfw": "Get Your Feet Wet (GYFW)",
}


def _is_allowed_excel(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_EXTENSIONS


def _selected_datasets(selection: str):
    normalized = (selection or "all").strip().lower()
    if normalized == "all":
        return list(DATASETS.keys())
    if normalized in DATASETS:
        return [normalized]
    return []


@app.get("/")
def home():
    return render_template(
        "upload.html",
        dataset_labels=DATASET_LABELS,
        selected_dataset="all",
        messages=[],
        status=None,
    )


@app.get("/map")
def map_view():
    return send_from_directory(BASE_DIR, MAP_FILE_NAME)


@app.get("/Data/<path:filename>")
def data_files(filename):
    return send_from_directory(DATA_DIR, filename)


@app.post("/upload")
def upload_excel():
    uploaded_file = request.files.get("excel_file")
    selected_dataset = request.form.get("dataset", "all")
    datasets_to_process = _selected_datasets(selected_dataset)
    messages = []

    if not datasets_to_process:
        return render_template(
            "upload.html",
            dataset_labels=DATASET_LABELS,
            selected_dataset=selected_dataset,
            messages=["Invalid dataset selection."],
            status="error",
        )

    if not uploaded_file or not uploaded_file.filename:
        return render_template(
            "upload.html",
            dataset_labels=DATASET_LABELS,
            selected_dataset=selected_dataset,
            messages=["Please choose an Excel (.xlsx) file."],
            status="error",
        )

    if not _is_allowed_excel(uploaded_file.filename):
        return render_template(
            "upload.html",
            dataset_labels=DATASET_LABELS,
            selected_dataset=selected_dataset,
            messages=["Only .xlsx files are supported."],
            status="error",
        )

    safe_name = secure_filename(uploaded_file.filename)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_path = UPLOAD_DIR / f"{timestamp}-{safe_name}"
    uploaded_file.save(saved_path)
    messages.append(f"Saved upload: {saved_path}")

    overall_success = True

    for dataset_name in datasets_to_process:
        messages.append(f"Processing dataset: {dataset_name}")

        def _capture_log(log_line):
            messages.append(str(log_line))

        generated_files = convert_excel_to_geojson(
            dataset_name=dataset_name,
            progress_callback=_capture_log,
            excel_path=str(saved_path),
            output_root=str(BASE_DIR),
        )

        if generated_files:
            for file_info in generated_files:
                messages.append(f"Updated: {file_info['local']}")
        else:
            overall_success = False
            messages.append(f"No output generated for dataset: {dataset_name}")

    status = "success" if overall_success else "error"
    return render_template(
        "upload.html",
        dataset_labels=DATASET_LABELS,
        selected_dataset=selected_dataset,
        messages=messages,
        status=status,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
