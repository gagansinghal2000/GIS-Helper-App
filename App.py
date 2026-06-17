import streamlit as st
import geopandas as gpd
import tempfile
import os
import zipfile
from datetime import datetime
from shapely.geometry import Polygon
import gspread
from google.oauth2.service_account import Credentials

# =========================
# Google Sheets Logging
# =========================
SHEET_NAME = "GIS Toolkit Logs"  # must match the Google Sheet's name exactly

@st.cache_resource
def get_worksheet():
    """Authenticate and return the worksheet object (cached across reruns)."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

def log_usage(operation, filename, extra_info=""):
    """Append a usage entry as a new row in the Google Sheet."""
    try:
        sheet = get_worksheet()
        sheet.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation,
            filename,
            extra_info
        ])
    except Exception as e:
        # Don't let logging failures break the actual app functionality
        st.warning(f"Logging failed (app still works fine): {e}")

# =========================
# Utility: Find Shapefile
# =========================
def find_shapefile(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".shp"):
                return os.path.join(root, file)
    return None

# =========================
# Function: KML/KMZ → Shapefile
# =========================
def kml_to_shapefile(kml_file, keep_proj=False):
    input_name = os.path.splitext(os.path.basename(kml_file.name))[0]
    temp_dir = tempfile.mkdtemp()

    # Handle KMZ
    if kml_file.name.lower().endswith('.kmz'):
        kmz_path = os.path.join(temp_dir, f"{input_name}.kmz")
        with open(kmz_path, "wb") as f:
            f.write(kml_file.read())
        with zipfile.ZipFile(kmz_path, 'r') as zf:
            zf.extractall(temp_dir)
        kml_files = [f for f in os.listdir(temp_dir) if f.endswith('.kml')]
        if not kml_files:
            raise Exception("No KML file found inside the KMZ.")
        kml_path = os.path.join(temp_dir, kml_files[0])
    else:
        # Handle KML
        kml_path = os.path.join(temp_dir, f"{input_name}.kml")
        with open(kml_path, "wb") as f:
            f.write(kml_file.read())

    # Read KML
    gdf = gpd.read_file(kml_path, driver='KML')

    # Reproject if needed
    if not keep_proj:
        gdf = gdf.to_crs(epsg=27700)  # BNG

    # Save as shapefile
    shapefile_path = os.path.join(temp_dir, f"{input_name}.shp")
    gdf.to_file(shapefile_path)

    # Zip shapefile
    zip_path = os.path.join(temp_dir, f"{input_name}_shapefile.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:
            file_path = shapefile_path.replace('.shp', ext)
            if os.path.exists(file_path):
                zf.write(file_path, os.path.basename(file_path))
    return zip_path

# =========================
# Function: Shapefile → KML
# =========================
def shapefile_to_kml(shapefile_zip, keep_proj=False):
    temp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(shapefile_zip, 'r') as zf:
        zf.extractall(temp_dir)
    shp_path = find_shapefile(temp_dir)
    if shp_path is None:
        raise Exception("No shapefile found in the uploaded ZIP.")
    gdf = gpd.read_file(shp_path)

    if not keep_proj:
        gdf = gdf.to_crs(epsg=4326)  # WGS84

    input_name = os.path.splitext(os.path.basename(shp_path))[0]
    kml_path = os.path.join(temp_dir, f"{input_name}.kml")
    gdf.to_file(kml_path, driver='KML')
    return kml_path

# =========================
# Function: Buffer Shapefile
# =========================
def buffer_shapefile(shapefile_zip, distance, keep_proj=False):
    temp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(shapefile_zip, 'r') as zf:
        zf.extractall(temp_dir)
    shp_path = find_shapefile(temp_dir)
    if shp_path is None:
        raise Exception("No shapefile found in the uploaded ZIP.")
    gdf = gpd.read_file(shp_path)

    if not keep_proj:
        gdf = gdf.to_crs(epsg=27700)  # BNG

    gdf['geometry'] = gdf.buffer(distance)
    input_name = os.path.splitext(os.path.basename(shp_path))[0]
    buffer_shp_path = os.path.join(temp_dir, f"{input_name}_buffer.shp")
    gdf.to_file(buffer_shp_path)

    zip_path = os.path.join(temp_dir, f"{input_name}_buffer.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:
            file_path = buffer_shp_path.replace('.shp', ext)
            if os.path.exists(file_path):
                zf.write(file_path, os.path.basename(file_path))
    return zip_path

# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="GIS Toolkit", layout="centered")

# Hidden admin link for users with ?admin=1
is_admin_mode = st.query_params.get("admin", "0") == "1"

ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

if is_admin_mode:
    pwd = st.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        st.success("Access granted")
        st.markdown("## Admin Dashboard")
        try:
            sheet = get_worksheet()
            records = sheet.get_all_records()
            if records:
                import pandas as pd
                df = pd.DataFrame(records)
                st.markdown(f"**Total records:** {len(df)}")
                st.dataframe(df)
                st.download_button("Download logs (CSV)", df.to_csv(index=False).encode("utf-8"), "usage_log.csv")
            else:
                st.info("No usage logs yet.")
            if st.button("Clear all logs"):
                sheet.clear()
                sheet.append_row(["Timestamp", "Operation", "Filename", "Details"])
                st.success("Logs cleared. Refresh the page.")
        except Exception as e:
            st.error(f"Could not load logs: {e}")
    else:
        if pwd:
            st.error("Incorrect password")
        st.info("Enter admin password to view dashboard.")

else:
    st.markdown("<h1 style='text-align:center;'>GIS Toolkit</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center; color:grey;'>Simple GIS tasks, one click away!</h3>", unsafe_allow_html=True)

    # Subtle Non-UK checkbox
    st.markdown("<span style='font-size:small; color:grey;'>Check for Non-UK files to keep original projection</span>", unsafe_allow_html=True)
    non_uk = st.checkbox("Non-UK file")

    operation = st.radio("Choose operation:", ["KML/KMZ → Shapefile", "Shapefile → KML", "Buffer Shapefile"])

    if operation == "KML/KMZ → Shapefile":
        kml_file = st.file_uploader("Upload KML or KMZ file", type=['kml', 'kmz'])
        if kml_file and st.button("Convert"):
            try:
                output = kml_to_shapefile(kml_file, keep_proj=non_uk)
                log_usage("KML/KMZ → Shapefile", kml_file.name)
                with open(output, "rb") as f:
                    st.download_button("Download Shapefile (ZIP)", f, file_name=os.path.basename(output))
            except Exception as e:
                st.error(f"Error: {e}")

    elif operation == "Shapefile → KML":
        shapefile_zip = st.file_uploader("Upload Shapefile (zipped)", type=['zip'])
        if shapefile_zip and st.button("Convert"):
            try:
                output = shapefile_to_kml(shapefile_zip, keep_proj=non_uk)
                log_usage("Shapefile → KML", shapefile_zip.name)
                with open(output, "rb") as f:
                    st.download_button("Download KML", f, file_name=os.path.basename(output))
            except Exception as e:
                st.error(f"Error: {e}")

    elif operation == "Buffer Shapefile":
        shapefile_zip = st.file_uploader("Upload Shapefile (zipped)", type=['zip'])
        distance = st.number_input("Buffer distance (meters)", min_value=1, value=100)
        if shapefile_zip and st.button("Create Buffer"):
            try:
                output = buffer_shapefile(shapefile_zip, distance, keep_proj=non_uk)
                log_usage("Buffer Shapefile", shapefile_zip.name, f"Distance: {distance} m")
                with open(output, "rb") as f:
                    st.download_button("Download Buffered Shapefile (ZIP)", f, file_name=os.path.basename(output))
            except Exception as e:
                st.error(f"Error: {e}")

st.markdown("---")
st.markdown(
    "<div style='text-align: center; font-size: small; color: grey;'>Created by Gagan Singhal | 📧 <a href='mailto:gagan.singhal@stantec.com'>Gagan.Singhal@Stantec.com</a></div>",
    unsafe_allow_html=True
)
