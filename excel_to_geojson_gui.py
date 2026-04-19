import tkinter as tk
from tkinter import ttk  # For themed widgets like Combobox
from tkinter import scrolledtext # For the output area
import threading # To keep the GUI responsive during processing

import pandas as pd
import json
import requests
import base64
from io import BytesIO
import os
from tkinter import filedialog
from tkinter import messagebox # To show error popups


from geopy.distance import geodesic
from shapely.geometry import Polygon, Point
import math
from shapely.geometry import mapping

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BRANCH = "main"



import configparser

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
config.read(config_path)

try:
    GITHUB_USERNAME = config.get('GitHub', 'Username')
    REPO_NAME = config.get('GitHub', 'RepoName')
    GITHUB_TOKEN = config.get('GitHub', 'Token')
except (configparser.NoSectionError, configparser.NoOptionError) as e:

    print(f"Error reading from config.ini: {e}")
  
    GITHUB_USERNAME, REPO_NAME, GITHUB_TOKEN = None, None, None


DATASETS = {
    "secchi": {
        "sheet_name": "Secchi",
        "geojson_file": "Data/geoJSONs/waiwanaka-secchi.geojson",
        "lat_col_start": "SurveyAreaLatitudeStart",
        "lon_col_start": "SurveyAreaLongitudeStart",
        "url_col": "url"
    },
    "stream testing": {
        "sheet_name": "Stream",
        "geojson_file": "Data/geoJSONs/waiwanaka-stream-testing.geojson",
        "lat_col_start": "SurveyAreaLatitudeStart",
        "lon_col_start": "SurveyAreaLongitudeStart",
        "url_col": "url"
    },
    "litter intelligence": {
        "sheet_name": "Litter",
        "base_geojson_path_by_type": "Data/geoJSONs/waiwanaka-litter-intelligence-",
        "lat_col_start": "SurveyAreaLatitudeStart",
        "lon_col_start": "SurveyAreaLongitudeStart",
        "lat_col_end": "SurveyAreaLatitudeEnd",
        "lon_col_end": "SurveyAreaLongitudeEnd",
        "url_col": "url",
        "types": ["beach", "freshwater", "stormwater", "unknown"]
    },
    "microplastics": {
        "sheet_name": "Microplastics",
        "geojson_file": "Data/geoJSONs/waiwanaka-microplastics.geojson",
        "lat_col_start": "SurveyAreaLatitudeStart",
        "lon_col_start": "SurveyAreaLongitudeStart",
        "url_col": "url"
    }
}

EXCEL_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Data", "excel datasheets", "Wai-Wanaka-Mapping-Data.xlsx")

def build_rectangle_from_line(start_lat, start_lon, end_lat, end_lon, width_m=20):
    # ... (your existing build_rectangle_from_line function code) ...
    mid_lat = (start_lat + end_lat) / 2
    mid_lon = (start_lon + end_lon) / 2
    start = (start_lat, start_lon)
    end = (end_lat, end_lon)
    distance = geodesic(start, end).meters
    # Using angle for line orientation relative to North/East
    angle = math.atan2(end_lon - start_lon, end_lat - start_lat)

    perp_angle_left = angle + math.pi / 2  # Perpendicular to the left
    perp_angle_right = angle - math.pi / 2 # Perpendicular to the right

    def offset_point(lat, lon, bearing_angle, dist_m):
        # Convert local bearing angle to change in lat/lon
        # dist_m is the distance to offset
        # R is Earth's radius in meters, approximately 6371000
        # More accurate conversion considering Earth's curvature:
        # However, for small distances (like half width of a 20m rectangle),
        # a simpler approximation is often used.
        # Using a simpler approximation for small offsets:
        # 1 degree of latitude ~ 111.32 km
        # 1 degree of longitude ~ 111.32 km * cos(latitude)
        
        # delta_lat_m = dist_m * math.cos(bearing_angle) # This would be if bearing_angle was from North
        # delta_lon_m = dist_m * math.sin(bearing_angle) # This would be if bearing_angle was from North

        # If 'angle' is from positive y-axis (North), and positive x-axis (East)
        # dx = dist_m * sin(angle)
        # dy = dist_m * cos(angle)
        
        # Corrected based on typical cartesian to geo offset:
        # angle is math.atan2(dx, dy) where dx is change in Easting, dy is change in Northing
        delta_lat_m = dist_m * math.cos(bearing_angle) # Northing component
        delta_lon_m = dist_m * math.sin(bearing_angle) # Easting component
        
        delta_lat_deg = delta_lat_m / 111320.0  # meters to degrees latitude
        # Latitude for longitude conversion should be the point's latitude
        delta_lon_deg = delta_lon_m / (111320.0 * math.cos(math.radians(lat))) # meters to degrees longitude
        
        return (lat + delta_lat_deg, lon + delta_lon_deg)

    # Offset points from start and end of the line
    # Points for the start of the line, offset perpendicularly
    p1 = offset_point(start_lat, start_lon, perp_angle_left, width_m / 2)
    p2 = offset_point(start_lat, start_lon, perp_angle_right, width_m / 2)
    # Points for the end of the line, offset perpendicularly
    p3 = offset_point(end_lat, end_lon, perp_angle_right, width_m / 2)
    p4 = offset_point(end_lat, end_lon, perp_angle_left, width_m / 2)
    
    # Shapely Polygon takes coordinates as (lon, lat)
    rectangle = Polygon([(p1[1], p1[0]), (p2[1], p2[0]), (p3[1], p3[0]), (p4[1], p4[0]), (p1[1], p1[0])])
    centre = rectangle.centroid
    return mapping(rectangle), (centre.y, centre.x)


def convert_excel_to_geojson(dataset_name, progress_callback=None): 

    if dataset_name not in DATASETS:
        if progress_callback:
            progress_callback(f"❌ Invalid dataset: {dataset_name}")
        else:
            print(f"❌ Invalid dataset: {dataset_name}")
        return []
    
    config = DATASETS[dataset_name]
    sheet_name = config["sheet_name"]
    is_litter = dataset_name == "litter intelligence"
    output_file_paths = []

    try:
        data_sheet = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
        if progress_callback:
            progress_callback(f"Successfully read sheet '{sheet_name}'. Number of rows: {len(data_sheet)}")
        else:
            print(f"Successfully read sheet '{sheet_name}'. Number of rows: {len(data_sheet)}")


        if is_litter:
            features_by_type = {survey_type: [] for survey_type in config["types"]}
            aggregated_points_by_type = {survey_type: {} for survey_type in config["types"]}

            for idx, row in data_sheet.iterrows():
                lat_col_start = config.get("lat_col_start")
                lon_col_start = config.get("lon_col_start")
                url_col = config.get("url_col", "url")

                lat_start_raw = row.get(lat_col_start)
                lon_start_raw = row.get(lon_col_start)
                url = row.get(url_col, "")

                if pd.isna(lat_start_raw) or pd.isna(lon_start_raw):
                    continue

                lat_start = round(float(lat_start_raw), 6)
                lon_start = round(float(lon_start_raw), 6)
                
                site_name = row.get("Site Name", f"Litter Site {idx + 1}")
                date_recorded_raw = row.get("Date Recorded")
                date_recorded_str = None
                if pd.notna(date_recorded_raw):
                    try:
                        date_recorded = pd.to_datetime(date_recorded_raw, errors="coerce")
                        if not pd.isna(date_recorded):
                            date_recorded_str = date_recorded.isoformat()
                    except Exception: # Handle potential errors if date format is unexpected
                        date_recorded_str = str(date_recorded_raw)


                survey_type_col = "type" 
                raw_survey_type_value = row.get(survey_type_col)
                
                current_survey_type = "unknown" 
                if pd.notna(raw_survey_type_value) and isinstance(raw_survey_type_value, str):
                    processed_type = str(raw_survey_type_value).strip().lower()
                    if processed_type in config["types"]: 
                        current_survey_type = processed_type
                    elif not processed_type: 
                        current_survey_type = "unknown"
                
                properties_base = {
                    "url": url,
                    "site_name": site_name,
                    "survey_type": current_survey_type,
                    "colour": config.get("colour", "#000000"),
                }
                if date_recorded_str:
                    properties_base["date_recorded"] = date_recorded_str

                lat_end_raw = row.get(config.get("lat_col_end"))
                lon_end_raw = row.get(config.get("lon_col_end"))

                if pd.notna(lat_end_raw) and pd.notna(lon_end_raw): 
                    lat_end = round(float(lat_end_raw), 6)
                    lon_end = round(float(lon_end_raw), 6)
                    geometry_polygon, centroid_coords = build_rectangle_from_line(lat_start, lon_start, lat_end, lon_end)

                    polygon_props = properties_base.copy()
                    polygon_props.update({
                        "id": f"survey-polygon-{current_survey_type}-{idx + 1}",
                        "centroid_coordinates": centroid_coords
                    })
                    polygon_feature = {"type": "Feature", "properties": polygon_props, "geometry": geometry_polygon}
                    features_by_type[current_survey_type].append(polygon_feature)

                    centroid_props = properties_base.copy()
                    centroid_props.update({
                        "id": f"survey-centroid-{current_survey_type}-{idx + 1}",
                        "is_centroid": True
                    })
                    centroid_feature = {
                        "type": "Feature",
                        "properties": centroid_props,
                        "geometry": {"type": "Point", "coordinates": [centroid_coords[1], centroid_coords[0]]}
                    }
                    features_by_type[current_survey_type].append(centroid_feature)
                else: 
                    point_key = f"{lon_start}-{lat_start}"
                    current_type_aggregated_points = aggregated_points_by_type[current_survey_type]

                    # Create details for the current survey event
                    current_event_detail = {}
                    if date_recorded_str:
                        current_event_detail["date_recorded"] = date_recorded_str
                    if url:
                        current_event_detail["url"] = url
                    
                    # Check if there's meaningful data for the event
                    is_meaningful_event = bool(current_event_detail.get("date_recorded") or current_event_detail.get("url"))

                    if point_key in current_type_aggregated_points:
                        current_type_aggregated_points[point_key]["properties"]["count"] += 1
                        if is_meaningful_event:
                            current_type_aggregated_points[point_key]["properties"]["survey_events"].append(current_event_detail)
                    else:
                        point_props = properties_base.copy()
                        point_props.update({
                            "id": f"survey-point-{current_survey_type}-{idx + 1}",
                            "count": 1,
                            "survey_events": [current_event_detail] if current_event_detail else [],
                            "is_centroid": False
                        })
                        current_type_aggregated_points[point_key] = {
                            "type": "Feature",
                            "properties": point_props,
                            "geometry": {"type": "Point", "coordinates": [lon_start, lat_start]}
                        }
            
            for survey_type_key in config["types"]:
                features_by_type[survey_type_key].extend(list(aggregated_points_by_type[survey_type_key].values()))

            for survey_type, features_list in features_by_type.items():
                if features_list:
                    # Construct the REPO-RELATIVE path for GitHub
                    repo_relative_path = f"{config['base_geojson_path_by_type']}{survey_type}.geojson"
                    # Construct the ABSOLUTE LOCAL path for saving the file
                    local_save_path = os.path.join(SCRIPT_DIR, "..", "..", repo_relative_path)

                    # Ensure directory exists locally
                    os.makedirs(os.path.dirname(local_save_path), exist_ok=True)

                    geojson_data = {"type": "FeatureCollection", "features": features_list}
                    with open(local_save_path, "w") as f: # Save to absolute local path
                        json.dump(geojson_data, f, indent=4)

                    msg = f"✅ GeoJSON saved for litter type '{survey_type}': {local_save_path}"
                    if progress_callback: progress_callback(msg)
                    else: print(msg)
                    # Use absolute local path for 'local', repo-relative path for 'repo'
                    output_file_paths.append({"local": local_save_path, "repo": repo_relative_path})

             
        
        else: # For Secchi, Stream Testing, Microplastics
            # Get the REPO-RELATIVE path from config
            repo_relative_path = config.get("geojson_file")
            # Construct the ABSOLUTE LOCAL path for saving
            local_save_path = os.path.join(SCRIPT_DIR, "..", "..", repo_relative_path)

            # Ensure directory exists locally
            os.makedirs(os.path.dirname(local_save_path), exist_ok=True)

            aggregated_points_generic = {}
            all_features_generic = []

            for idx, row in data_sheet.iterrows():
                lat_col_start = config.get("lat_col_start")
                lon_col_start = config.get("lon_col_start")
                url_col = config.get("url_col", "url")
                lat_start_raw = row.get(lat_col_start)
                lon_start_raw = row.get(lon_col_start)
                url = row.get(url_col, "")

                if pd.isna(lat_start_raw) or pd.isna(lon_start_raw):
                    continue
                
                lat_start = round(float(lat_start_raw), 6)
                lon_start = round(float(lon_start_raw), 6)
                point_key = f"{lon_start}-{lat_start}"

                site_name_col = "Site Name"
                date_col = "Date Recorded"
                id_col = "ID" 

                site_name = row.get(site_name_col, f"Site-{idx+1}")
                date_recorded_raw = row.get(date_col)
                date_recorded_str = None
                if pd.notna(date_recorded_raw):
                    try:
                        if sheet_name == 'Microplastics':
                            date_recorded_str = str(date_recorded_raw).strip()
                        else:
                            date_recorded = pd.to_datetime(date_recorded_raw, errors="coerce")
                            if not pd.isna(date_recorded):
                                date_recorded_str = date_recorded.isoformat()
                    except Exception:
                        date_recorded_str = str(date_recorded_raw)

                
                data_point_info = {"url": url} 
                if date_recorded_str:
                    data_point_info["date_recorded"] = date_recorded_str
                
                skip_cols_list = [
                    config.get("lat_col_start"), config.get("lon_col_start"),
                    config.get("lat_col_end"), config.get("lon_col_end"), # Add end cols if they exist
                    config.get("url_col"),
                    "Site Name", "Date Recorded", "ID", "type" # Add other common metadata cols
                ]
                # Filter out None values from skip_cols_list, in case some configs don't have all keys
                skip_cols = [col for col in skip_cols_list if col is not None]


                for col_name_iter in data_sheet.columns: 
                    if col_name_iter not in skip_cols:
                        value = row[col_name_iter]
                        if pd.isna(value):
                            data_point_info[col_name_iter] = None
                        else:
                            data_point_info[col_name_iter] = value
                            
                if point_key in aggregated_points_generic:
                    aggregated_points_generic[point_key]["properties"]["count"] += 1
                    if url and url not in aggregated_points_generic[point_key]["properties"]["urls"]:
                         aggregated_points_generic[point_key]["properties"]["urls"].append(url)
                    if "data_points" not in aggregated_points_generic[point_key]["properties"]:
                        aggregated_points_generic[point_key]["properties"]["data_points"] = []
                    aggregated_points_generic[point_key]["properties"]["data_points"].append(data_point_info)
                else:
                    props = {
                        "id": f"{dataset_name.replace(' ', '-')}-point-{idx + 1}",
                        "site_name": site_name,
                        "colour": config.get("colour", "#000000"),
                        "count": 1,
                        "urls": [url] if url else [],
                        "data_points": [data_point_info] # Store all other row data here
                    }
                    if date_recorded_str: 
                        props["date_recorded"] = date_recorded_str
                    
                    aggregated_points_generic[point_key] = {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon_start, lat_start]},
                        "properties": props
                    }
            all_features_generic.extend(list(aggregated_points_generic.values()))
            
            if all_features_generic:
                geojson_data = {"type": "FeatureCollection", "features": all_features_generic}
                with open(local_save_path, "w") as f: # Save to absolute local path
                    json.dump(geojson_data, f, indent=4)
                msg = f"✅ GeoJSON saved for {dataset_name}: {local_save_path}"
                if progress_callback: progress_callback(msg)
                else: print(msg)
                # Use absolute local path for 'local', repo-relative path for 'repo'
                output_file_paths.append({"local": local_save_path, "repo": repo_relative_path})
            else:
                msg = f"ℹ️ No features generated for {dataset_name}."
                if progress_callback: progress_callback(msg)
                else: print(msg)

        return output_file_paths

    except Exception as e:
        err_msg = f"❌ Error processing {dataset_name}: {e}"
        if progress_callback:
            progress_callback(err_msg)
        else:
            print(err_msg)
        import traceback
        # To print traceback to console even when using GUI:
        traceback.print_exc() 
        # If you want traceback in GUI (can be long):
        # if progress_callback: progress_callback(traceback.format_exc())
        return []


def upload_to_github(local_file_path, repo_file_path, progress_callback=None): # Added progress_callback
    # ... (your existing upload_to_github function code) ...
    # Replace print() calls with progress_callback()
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{repo_file_path}"
    try:
        with open(local_file_path, "rb") as file:
            content = file.read()
            encoded_content = base64.b64encode(content).decode("utf-8")
    except FileNotFoundError:
        msg = f"❌ Local file not found for upload: {local_file_path}"
        if progress_callback: progress_callback(msg)
        else: print(msg)
        return

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    # It's good practice to also set a User-Agent
    headers["User-Agent"] = "WaiWanakaGeoJSONScript/1.0"
    
    response_get = requests.get(url, headers=headers)
    sha = None
    if response_get.status_code == 200:
        sha = response_get.json().get("sha")
    elif response_get.status_code != 404:
        msg = f"❌ Error checking file on GitHub ({repo_file_path}): {response_get.status_code} - {response_get.text}"
        if progress_callback: progress_callback(msg)
        else: print(msg)
        # Don't return here, allow attempt to upload if it's just a check error but not 404

    data = {
        "message": f"Update {repo_file_path} via script",
        "content": encoded_content,
        "branch": BRANCH
    }
    if sha:
        data["sha"] = sha

    response_put = requests.put(url, headers=headers, data=json.dumps(data))
    if response_put.status_code in [200, 201]: # 200 for update, 201 for create
        try:
            html_url = response_put.json().get("content", {}).get("html_url", "N/A")
            msg = f"✅ Upload successful for {repo_file_path}: {html_url}"
            if progress_callback: progress_callback(msg)
            else: print(msg)
        except Exception: # Catch potential errors if response JSON is not as expected
            msg = f"✅ Upload successful for {repo_file_path} (Status: {response_put.status_code})"
            if progress_callback: progress_callback(msg)
            else: print(msg)
    else:
        msg = f"❌ Upload failed for {repo_file_path}: {response_put.status_code} - {response_put.text}"
        if progress_callback: progress_callback(msg)
        else: print(msg)

# --- END OF THE COPIED/UNCHANGED CODE ---


class GeoJSONApp:
    def __init__(self, root):
        self.root = root
        root.title("GeoJSON Converter")

        # Frame for controls
        controls_frame = ttk.Frame(root, padding="10")
        controls_frame.grid(row=0, column=0, sticky="ew")

        ttk.Label(controls_frame, text="Select dataset to process:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.dataset_var = tk.StringVar()
        dataset_options = list(DATASETS.keys()) + ['all']
        self.dataset_combo = ttk.Combobox(controls_frame, textvariable=self.dataset_var, values=dataset_options, state="readonly")
        self.dataset_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        if dataset_options:
            self.dataset_combo.set(dataset_options[-1])  # Default to 'all'

        self.run_button = ttk.Button(controls_frame, text="Run Conversion", command=self.start_processing_thread)
        self.run_button.grid(row=1, column=0, padx=5, pady=10, sticky="ew")

        self.exit_button = ttk.Button(controls_frame, text="Exit", command=root.destroy)
        self.exit_button.grid(row=1, column=1, padx=5, pady=10, sticky="ew")
        
        controls_frame.columnconfigure(1, weight=1) # Make combobox expand

        # Frame for output
        output_frame = ttk.Frame(root, padding="10")
        output_frame.grid(row=1, column=0, sticky="nsew")

        ttk.Label(output_frame, text="Output:").grid(row=0, column=0, sticky="w")
        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=15, width=70)
        self.output_text.grid(row=1, column=0, sticky="nsew")
        self.output_text.config(state=tk.DISABLED) # Make it read-only initially

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(1, weight=1)

        self.excel_path_var = tk.StringVar(value="No Excel file selected.")

        # Add a label to show the selected file path
        ttk.Label(controls_frame, text="Excel File:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.excel_path_label = ttk.Label(controls_frame, textvariable=self.excel_path_var, font=('Helvetica', 9, 'italic'))
        self.excel_path_label.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # Add a button to browse for the file
        self.browse_button = ttk.Button(controls_frame, text="Browse for Excel File", command=self.browse_for_excel)
        self.browse_button.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Adjust the grid rows of your Run and Exit buttons
        self.run_button.grid(row=4, column=0, padx=5, pady=10, sticky="ew")
        self.exit_button.grid(row=4, column=1, padx=5, pady=10, sticky="ew")

    def browse_for_excel(self):
        # This is a new method to add to your GeoJSONApp class
        file_path = filedialog.askopenfilename(
            title="Select the Wai-Wanaka Excel File",
            filetypes=[("Excel Files", "*.xlsx"), ("All files", "*.*")]
        )
        if file_path:
            # Update the global EXCEL_PATH variable your functions use
            global EXCEL_PATH
            EXCEL_PATH = file_path
            self.excel_path_var.set(os.path.basename(file_path)) # Show just the filename
            self.log_message(f"Selected Excel file: {file_path}")

    def log_message(self, message):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END) # Scroll to the end
        self.output_text.config(state=tk.DISABLED)
        self.root.update_idletasks() # Refresh GUI

    def clear_log(self):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        self.output_text.config(state=tk.DISABLED)

    def processing_logic(self):
        if not all([GITHUB_USERNAME, REPO_NAME, GITHUB_TOKEN]):
            messagebox.showerror("Configuration Error", "GitHub details are missing. Please check your config.ini file.")
            self.log_message("❌ Error: Could not load GitHub configuration.")
            return
        global EXCEL_PATH
        if not EXCEL_PATH or not os.path.exists(EXCEL_PATH):
            messagebox.showerror("Error", "Please select a valid Excel file before running the conversion.")
            self.log_message("❌ Error: No valid Excel file selected.")
            return # Stop processing
        self.run_button.config(state=tk.DISABLED)
        self.clear_log()
        self.log_message("Starting process...")

        dataset_type_input = self.dataset_var.get()
        
        datasets_to_process = []
        if not dataset_type_input:
            self.log_message("❌ No dataset type selected.")
            self.run_button.config(state=tk.NORMAL)
            return

        if dataset_type_input == "all":
            datasets_to_process = list(DATASETS.keys())
        elif dataset_type_input in DATASETS:
            datasets_to_process = [dataset_type_input]
        else:
            self.log_message(f"❌ Invalid dataset type selected: {dataset_type_input}")
            self.run_button.config(state=tk.NORMAL)
            return

        for dataset_name in datasets_to_process:
            self.log_message(f"\n📌 Processing {dataset_name}...")
            # Pass the log_message method as the progress_callback
            generated_files_info = convert_excel_to_geojson(dataset_name, progress_callback=self.log_message)

            for file_info in generated_files_info:
                if file_info and file_info.get("local") and file_info.get("repo"):
                    # Pass the log_message method as the progress_callback
                    upload_to_github(file_info["local"], file_info["repo"], progress_callback=self.log_message)
                else:
                    self.log_message(f"⚠️ Skipping upload for an invalid file entry for {dataset_name}. Info: {file_info}")
            self.log_message(f"✅ Finished processing dataset: {dataset_name}")
        
        self.log_message("\n🎉 All selected datasets processed!")
        self.run_button.config(state=tk.NORMAL)


    def start_processing_thread(self):
        # Run the processing logic in a separate thread to keep the GUI responsive
        # This is important for longer tasks.
        thread = threading.Thread(target=self.processing_logic, daemon=True)
        thread.start()


if __name__ == "__main__":
    # --- Your VS Code Python Diagnostics (can be removed for final version) ---
    # print("--- VS Code Python Diagnostics ---")
    # print("Python Executable:", sys.executable)
    # print("Python Version:", sys.version)
    # print("Sys Path (first few entries):")
    # for p in sys.path[:5]:
    #     print(p)
    # print("--- End Diagnostics ---")
    
    # This check is crucial for Tkinter to work
    try:
        # Attempt to import _tkinter to catch the error early
        # and provide a more specific message if it's missing.
        import _tkinter
    except ImportError:
        print("ERROR: The '_tkinter' module was not found.")
        print("This means your Python installation does not have Tcl/Tk support.")
        print("Please ensure Tcl/Tk is installed and your Python was compiled with Tk support.")
        print("On macOS with Homebrew, try: 'brew install python-tk' or 'brew install tcl-tk' then 'brew reinstall python'.")
        print("You may need to recreate your virtual environment after fixing the base Python installation.")
        exit(1) # Exit if Tkinter support is missing

    root = tk.Tk()
    app = GeoJSONApp(root)
    root.mainloop()