# WAI Wanaka Local Demo Guide

## What this version includes
- GYFW (Get Your Feet Wet) dataset integration into the existing converter and map.
- Staff upload page to update one dataset or all datasets.
- Flask backend that saves uploaded Excel files, runs conversion, and updates local GeoJSON files.
- Existing map kept in place, now reading local GeoJSON files served by Flask.

## File overview
- Converter: `C:\wai_project\excel_to_geojson_gui.py`
- Backend: `C:\wai_project\app.py`
- Upload page: `C:\wai_project\templates\upload.html`
- Map frontend: `C:\wai_project\WAIWanaka (1).html`
- Generated GeoJSON output: `C:\wai_project\Data\geoJSONs\`
- Upload storage: `C:\wai_project\uploads\`
- GYFW sample workbook: `C:\wai_project\Wai-Wanaka-Mapping-Data-GYFW-Test.xlsx`

## Local run steps
1. Install dependencies:
```powershell
py -m ensurepip --upgrade
C:\wai_project\Scripts\pip3.exe install -r C:\wai_project\requirements.txt
```

2. Start backend:
```powershell
cd C:\wai_project
py app.py
```

3. Open upload page:
- [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

4. Upload Excel:
- Choose `.xlsx` file.
- Select `All datasets` or one dataset (including `Get Your Feet Wet (GYFW)`).
- Click **Upload and Convert**.

5. View updated map:
- [http://127.0.0.1:5000/map](http://127.0.0.1:5000/map)
- Refresh map after a successful upload to load latest GeoJSON.

## Staff update workflow (simple)
1. Prepare or receive updated Excel file.
2. Open upload page in browser.
3. Select file and dataset scope (`All` recommended for regular updates).
4. Submit and confirm success message.
5. Open map and click points to verify data appears correctly.

## System flow
1. Staff uploads Excel via web form.
2. Flask saves file into `uploads/`.
3. Flask calls existing converter (`convert_excel_to_geojson`) per selected dataset.
4. Converter reads Excel sheets and writes GeoJSON to `Data/geoJSONs/`.
5. Map fetches GeoJSON from `/Data/geoJSONs/*.geojson` and displays latest data.
