import streamlit as st
import geopandas as gpd
import tempfile
import os
import zipfile
import csv
from datetime import datetime
from shapely.geometry import Polygon

# =========================
# Logging Function
# =========================
LOG_FILE = "usage_log.csv"

def log_usage(operation, filename, extra_info=""):
    """Append a usage entry to the CSV log file."""
    log_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not log_exists:
            writer.writerow(["Timestamp", "Operation", "Filename", "Details"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation,
            filename,
            extra_info
        ])

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
st.set_page_config(page_title="GIS Helper App", layout="centered")

# Hidden admin link for users with ?admin=1
query_params = st.query_params
is_admin_mode = query_params.get("admin", ["0"])[0] == "1"

ADMIN_PASSWORD = "Gagan321"

if is_admin_mode:
    pwd = st.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        st.success("Access granted")
        st.markdown("## Admin Dashboard")
        if os.path.exists(LOG_FILE):
            import pandas as pd
            df = pd.read_csv(LOG_FILE)
            st.markdown(f"**Total records:** {len(df)}")
            st.dataframe(df)
            st.download_button("Download logs (CSV)", df.to_csv(index=False).encode("utf-8"), "usage_log.csv")
            if st.button("Clear all logs"):
                open(LOG_FILE, 'w').close()
                st.success("Logs cleared. Refresh the page.")
    else:
        if pwd:
            st.error("Incorrect password")
        st.info("Enter admin password to view dashboard.")

else:
    st.markdown("<h1 style='text-align:center;'>GIS Helper App</h1>", unsafe_allow_html=True)
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