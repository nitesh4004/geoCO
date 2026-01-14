import streamlit as st
import ee
import json
import geemap.foliumap as geemap
import xml.etree.ElementTree as ET
import re
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import numpy as np
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta
import pandas as pd

# --- 1. PAGE CONFIG ---
st.set_page_config(
    page_title="GeoSarovar - Water Intelligence",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Inter:wght@400;600&display=swap');

    :root {
        --bg-color: #ffffff;
        --accent-primary: #00204a;
        --accent-secondary: #005792;
        --text-primary: #00204a;
    }

    .stApp {
        background-color: var(--bg-color);
        font-family: 'Inter', sans-serif;
        color: var(--text-primary);
    }

    h1, h2, h3, .title-font {
        font-family: 'Rajdhani', sans-serif !important;
        color: var(--accent-primary) !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #d1d9e6;
    }

    /* Primary Buttons */
    div.stButton > button:first-child {
        background: var(--accent-primary);
        border: none;
        color: white !important;
        font-family: 'Rajdhani', sans-serif;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 0.6rem;
        border-radius: 6px;
        width: 100%;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        background: var(--accent-secondary);
        transform: translateY(-2px);
    }

    /* HUD Header */
    .hud-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #ffffff;
        border-bottom: 2px solid var(--accent-primary);
        padding: 15px 25px;
        border-radius: 0 0 10px 10px;
        margin-bottom: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    .hud-title {
        font-family: 'Rajdhani', sans-serif;
        font-size: 2.2rem;
        font-weight: 700;
        color: var(--accent-primary);
    }

    /* Cards */
    .glass-card {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
    }
    .card-label {
        font-family: 'Rajdhani', sans-serif;
        color: var(--accent-primary);
        font-size: 1.1rem;
        font-weight: 700;
        text-transform: uppercase;
        border-bottom: 2px solid #f0f0f0;
        padding-bottom: 8px;
        margin-bottom: 12px;
    }
    .alert-card {
        background: #fff5f5;
        border: 1px solid #fc8181;
        padding: 15px;
        border-radius: 12px;
        margin-bottom: 15px;
        margin-top: 15px;
    }
    .date-badge {
        background-color: #eef2f6;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #00204a;
        margin-top: 5px;
        display: inline-block;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. AUTHENTICATION (GEE) ---
try:
    if "gcp_service_account" in st.secrets:
        service_account = st.secrets["gcp_service_account"]["client_email"]
        secret_dict = dict(st.secrets["gcp_service_account"])
        key_data = json.dumps(secret_dict)
        credentials = ee.ServiceAccountCredentials(service_account, key_data=key_data)
        ee.Initialize(credentials)
    else:
        ee.Initialize()
except Exception as e:
    st.error(f"⚠️ GEE Authentication Error: {e}")

# --- STATE MANAGEMENT ---
if 'calculated' not in st.session_state: st.session_state['calculated'] = False
if 'roi' not in st.session_state: st.session_state['roi'] = None
if 'mode' not in st.session_state: st.session_state['mode'] = "🌦️ Rainfall Analysis"
if 'detected_state' not in st.session_state: st.session_state['detected_state'] = None 

# --- 5. APP HELPER FUNCTIONS ---

def parse_kml(content):
    try:
        if isinstance(content, bytes): content = content.decode('utf-8')
        match = re.search(r'<coordinates>(.*?)</coordinates>', content, re.DOTALL | re.IGNORECASE)
        if match: return process_coords(match.group(1))
        root = ET.fromstring(content)
        for elem in root.iter():
            if elem.tag.lower().endswith('coordinates') and elem.text:
                return process_coords(elem.text)
    except: pass
    return None

def process_coords(text):
    raw = text.strip().split()
    coords = [[float(x.split(',')[0]), float(x.split(',')[1])] for x in raw if len(x.split(',')) >= 2]
    return ee.Geometry.Polygon([coords]) if len(coords) > 2 else None

def geojson_to_ee(geo_json):
    """Converts a GeoJSON geometry dictionary to an Earth Engine Geometry."""
    try:
        if geo_json['type'] == 'Polygon':
            return ee.Geometry.Polygon(geo_json['coordinates'])
        elif geo_json['type'] == 'Point':
            return ee.Geometry.Point(geo_json['coordinates'])
        return None
    except:
        return None

def detect_state_from_geometry(geometry):
    """
    Detects which Indian State the geometry center falls into using FAO GAUL.
    """
    try:
        states = ee.FeatureCollection("FAO/GAUL/2015/level1")
        center = geometry.centroid(100)
        intersecting_state = states.filterBounds(center).first()
        state_name = intersecting_state.get('ADM1_NAME').getInfo()
        return state_name
    except:
        return None

# --- ADVANCED STATIC MAP GENERATOR ---
def generate_static_map_display(image, roi, vis_params, title, cmap_colors=None, is_categorical=False, class_names=None):
    try:
        if isinstance(roi, ee.Geometry):
            try:
                roi_json = roi.getInfo()
                roi_bounds = roi.bounds().getInfo()['coordinates'][0]
            except: return None
        else:
            roi_json = roi
            roi_bounds = roi['coordinates'][0]

        lons = [p[0] for p in roi_bounds]
        lats = [p[1] for p in roi_bounds]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        width_deg = max_lon - min_lon
        height_deg = max_lat - min_lat
        if height_deg == 0: height_deg = 0.001

        aspect_ratio = (width_deg * np.cos(np.radians((min_lat + max_lat) / 2))) / height_deg
        fig_width = 12
        fig_height = fig_width / aspect_ratio
        if fig_height > 20: fig_height = 20
        if fig_height < 4: fig_height = 4

        s2_background = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")\
            .filterBounds(roi).filterDate('2023-01-01', '2023-12-31')\
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\
            .median().visualize(min=0, max=3000, bands=['B4', 'B3', 'B2'])

        if 'palette' in vis_params or 'min' in vis_params:
            analysis_vis = image.visualize(**vis_params)
        else:
            analysis_vis = image

        final_image = s2_background.blend(analysis_vis)

        thumb_url = final_image.getThumbURL({
            'region': roi_json, 'dimensions': 1000, 'format': 'png', 'crs': 'EPSG:4326'
        })

        response = requests.get(thumb_url, timeout=120)
        if response.status_code != 200: return None

        img_pil = Image.open(BytesIO(response.content))

        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=300, facecolor='#ffffff')
        extent = [min_lon, max_lon, min_lat, max_lat]
        ax.imshow(img_pil, extent=extent, aspect='auto')
        ax.set_title(title, fontsize=18, fontweight='bold', pad=20, color='#00204a')

        ax.tick_params(colors='black', labelsize=10)
        for spine in ax.spines.values(): spine.set_edgecolor('black')

        if is_categorical and class_names and 'palette' in vis_params:
            patches = [mpatches.Patch(color=c, label=n) for n, c in zip(class_names, vis_params['palette'])]
            legend = ax.legend(handles=patches, loc='upper center', bbox_to_anchor=(0.5, -0.08),
                                     frameon=False, ncol=min(len(class_names), 4))
        elif cmap_colors and 'min' in vis_params:
            cmap = mcolors.LinearSegmentedColormap.from_list("custom", cmap_colors)
            norm = mcolors.Normalize(vmin=vis_params['min'], vmax=vis_params['max'])
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
            cbar = plt.colorbar(sm, cax=cax)
            cbar.set_label('Index Value', color='black', fontsize=12)

        buf = BytesIO()
        plt.savefig(buf, format='jpg', bbox_inches='tight', facecolor='#ffffff')
        buf.seek(0)
        plt.close(fig)
        return buf
    except: return None

# --- 6. SIDEBAR ---
with st.sidebar:
    st.image("https://raw.githubusercontent.com/nitesh4004/GeoSarovar/main/geosarovar.png", use_container_width=True)
    st.markdown("### 1. Select Module")
    app_mode = st.radio("Choose Functionality:",
                        ["🌦️ Rainfall & Climate Analysis",
                         "💧 Rainwater Harvesting Potential",
                         "⚠️ Encroachment (S1 SAR)",
                         "Flood Extent Mapping",
                         "🧪 Water Quality"],
                        label_visibility="collapsed")
    st.markdown("---")

    # --- UPDATED LOCATION LOGIC ---
    st.markdown("### 2. Location (ROI)")
    # Reordered Menu as requested
    roi_method = st.radio("Selection Mode", ["Upload KML", "Point & Buffer", "Draw on Map"], label_visibility="collapsed")
    new_roi = None
    
    # Context variable for smart weights
    current_state_context = st.session_state.get('detected_state', None)

    if roi_method == "Upload KML":
        kml = st.file_uploader("Upload KML", type=['kml'])
        if kml: 
            new_roi = parse_kml(kml.read())
            if new_roi:
                st.session_state['roi'] = new_roi.simplify(maxError=50)

    elif roi_method == "Point & Buffer":
        c1, c2 = st.columns(2)
        lat = c1.number_input("Lat", value=20.59)
        lon = c2.number_input("Lon", value=78.96)
        rad = st.number_input("Radius (m)", value=5000)
        new_roi = ee.Geometry.Point([lon, lat]).buffer(rad).bounds()
        if new_roi:
            st.session_state['roi'] = new_roi
            
    elif roi_method == "Draw on Map":
        # Instructions handled in main area
        if st.session_state['roi'] is not None:
             st.info(f"📍 ROI Set: {st.session_state.get('detected_state', 'Custom Area')}")
             if st.button("🗑️ Reset / Draw New"):
                st.session_state['roi'] = None
                st.session_state['calculated'] = False
                st.session_state['detected_state'] = None
                st.rerun()

    # --- ROI LOCKING & STATE DETECTION ---
    # Note: For "Draw on Map", detection happens in the main body after drawing
    if roi_method != "Draw on Map" and st.session_state['roi']:
        if not st.session_state['detected_state']:
            with st.spinner("Detecting Location..."):
                detected = detect_state_from_geometry(st.session_state['roi'])
                if detected:
                    st.session_state['detected_state'] = detected
                    st.success(f"ROI Locked ✅ ({detected})")
                else:
                    st.success("ROI Locked ✅")
        else:
             st.success(f"ROI Locked ✅ ({st.session_state['detected_state']})")

    st.markdown("---")

    params = {}
    if app_mode == "🌦️ Rainfall & Climate Analysis":
        st.markdown("### 3. Data & Time Parameters")
        dataset = st.selectbox("Dataset Source", ["CHIRPS (Daily Climatology)", "GPM (IMERG Near-Real-Time)"])
        
        st.markdown("**Analysis Period**")
        col1, col2 = st.columns(2)
        rain_start = col1.date_input("Start Date", datetime(2023, 6, 1))
        rain_end = col2.date_input("End Date", datetime(2023, 9, 30))
        
        calc_mode = st.radio("Calculation Mode", ["Total Accumulation (mm)", "Rainfall Anomaly (%)"])
        
        params = {
            'dataset': dataset,
            'start': rain_start.strftime("%Y-%m-%d"),
            'end': rain_end.strftime("%Y-%m-%d"),
            'calc_mode': calc_mode
        }

    elif app_mode == "💧 Rainwater Harvesting Potential":
        st.markdown("### 3. Suitability Criteria")
        rwh_type = st.selectbox("Target Structure", ["Percolation Tank (Recharge)", "Check Dam (Streams)", "Farm Pond (Storage)"])
        
        # --- SMART AUTO-WEIGHT LOGIC ---
        # Default Weights (General / Plateau)
        def_rain, def_slope, def_soil, def_lulc, def_drain = 0.25, 0.20, 0.20, 0.15, 0.20
        geo_zone = "General (Plateau)"

        # Use the detected state if available
        state_for_logic = st.session_state.get('detected_state', None)

        if state_for_logic:
            # 1. Arid / Semi-Arid (Rajasthan, Gujarat)
            if state_for_logic in ["Rajasthan", "Gujarat", "Haryana"]:
                geo_zone = "Arid/Semi-Arid"
                def_rain, def_slope, def_soil, def_lulc, def_drain = 0.35, 0.15, 0.25, 0.10, 0.15
            
            # 2. Hilly / Himalayan (Uttarakhand, HP, NE States)
            elif state_for_logic in ["Himachal Pradesh", "Uttarakhand", "Sikkim", "Arunachal Pradesh", "Jammu and Kashmir", "Ladakh"]:
                geo_zone = "Hilly/Mountainous"
                def_rain, def_slope, def_soil, def_lulc, def_drain = 0.10, 0.40, 0.15, 0.10, 0.25
            
            # 3. Coastal / High Rainfall (Kerala, Goa)
            elif state_for_logic in ["Kerala", "Goa", "Konkan"]:
                geo_zone = "Coastal/Wet"
                def_rain, def_slope, def_soil, def_lulc, def_drain = 0.10, 0.30, 0.20, 0.20, 0.20
            
            # 4. Plains (UP, Bihar, WB, Punjab)
            elif state_for_logic in ["Uttar Pradesh", "Bihar", "West Bengal", "Punjab"]:
                geo_zone = "Alluvial Plains"
                def_rain, def_slope, def_soil, def_lulc, def_drain = 0.20, 0.10, 0.15, 0.30, 0.25

        st.info(f"📍 Detected Zone: **{geo_zone}**")
        st.caption("Weights auto-adjusted for this terrain.")

        st.markdown("**Criteria Weights (0-1)**")
        w_rain = st.slider("Rainfall", 0.0, 1.0, def_rain, 0.05, help="Weight for Precipitation.")
        w_slope = st.slider("Slope (Topography)", 0.0, 1.0, def_slope, 0.05, help="Weight for Slope.")
        w_soil = st.slider("Soil Texture", 0.0, 1.0, def_soil, 0.05, help="Weight for Infiltration.")
        w_lulc = st.slider("Land Use", 0.0, 1.0, def_lulc, 0.05, help="Avoid Urban/Agri conflicts.")
        w_drain = st.slider("Drainage Density", 0.0, 1.0, def_drain, 0.05, help="Proximity to streams.")
        
        # Normalize weights
        total = w_rain + w_slope + w_soil + w_lulc + w_drain
        if total == 0: total = 1
        
        params = {
            'type': rwh_type,
            'w': {
                'rain': w_rain/total, 'slope': w_slope/total, 'soil': w_soil/total, 
                'lulc': w_lulc/total, 'drain': w_drain/total
            }
        }

    elif app_mode == "⚠️ Encroachment (S1 SAR)":
        st.markdown("### 3. Comparison Dates")
        orbit = st.radio("Orbit Pass", ["BOTH", "ASCENDING", "DESCENDING"])
        st.markdown("**Initial Period (Baseline)**")
        col1, col2 = st.columns(2)
        d1_start = col1.date_input("Start 1", datetime(2018, 6, 1))
        d1_end = col2.date_input("End 1", datetime(2018, 9, 30))
        st.markdown("**Final Period (Current)**")
        col3, col4 = st.columns(2)
        d2_start = col3.date_input("Start 2", datetime(2024, 6, 1))
        d2_end = col4.date_input("End 2", datetime(2024, 9, 30))
        params = {'d1_start': d1_start.strftime("%Y-%m-%d"), 'd1_end': d1_end.strftime("%Y-%m-%d"), 'd2_start': d2_start.strftime("%Y-%m-%d"), 'd2_end': d2_end.strftime("%Y-%m-%d"), 'orbit': orbit}

    elif app_mode == "Flood Extent Mapping":
        st.markdown("### 3. Flood Event Details")
        orbit = st.radio("Orbit Pass", ["BOTH", "ASCENDING", "DESCENDING"])
        st.markdown("**Before Flood (Dry)**")
        col1, col2 = st.columns(2)
        pre_start = col1.date_input("Pre Start", datetime(2023, 4, 1))
        pre_end = col2.date_input("Pre End", datetime(2023, 6, 1))
        st.markdown("**After Flood (Wet)**")
        col3, col4 = st.columns(2)
        post_start = col3.date_input("Post Start", datetime(2023, 9, 29))
        post_end = col4.date_input("Post End", datetime(2023, 10, 15))
        threshold = st.slider("Difference Threshold", 1.0, 1.5, 1.25, 0.05)
        params = {'pre_start': pre_start.strftime("%Y-%m-%d"), 'pre_end': pre_end.strftime("%Y-%m-%d"), 'post_start': post_start.strftime("%Y-%m-%d"), 'post_end': post_end.strftime("%Y-%m-%d"), 'threshold': threshold, 'orbit': orbit}

    elif app_mode == "🧪 Water Quality":
        st.markdown("### 3. Monitoring Config")
        wq_param = st.selectbox("Parameter", ["Turbidity (NDTI)", "Total Suspended Solids (TSS)", "Cyanobacteria Index", "Chlorophyll-a", "CDOM (Organic Matter)"])
        st.markdown("**Timeframe**")
        col1, col2 = st.columns(2)
        wq_start = col1.date_input("Start", datetime.now()-timedelta(days=90))
        wq_end = col2.date_input("End", datetime.now())
        cloud_thresh = st.slider("Max Cloud Cover %", 5, 50, 20)
        params = {'param': wq_param, 'start': wq_start.strftime("%Y-%m-%d"), 'end': wq_end.strftime("%Y-%m-%d"), 'cloud': cloud_thresh}

    st.markdown("###")
    if st.button("RUN ANALYSIS 🚀"):
        if st.session_state['roi']:
            st.session_state['calculated'] = True
            st.session_state['mode'] = app_mode
            st.session_state['params'] = params
        else:
            st.error("Please draw or select an ROI first.")

# --- 7. MAIN CONTENT ---
st.markdown(f"""
<div class="hud-header">
    <div>
        <div class="hud-title">GeoSarovar</div>
        <div style="color:#5c6b7f; font-size:0.9rem; font-weight:600;">MODULE: {app_mode.upper()}</div>
    </div>
    <div style="text-align:right;">
        <span style="background:#e6f0ff; color:#00204a; padding:5px 12px; border-radius:20px; font-weight:bold; font-size:0.8rem;">LIVE SYSTEM</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Helper for Safe Map Loading
def get_safe_map(height=500):
    m = geemap.Map(height=height, basemap="HYBRID")
    return m

# --- CASE 1: DRAW MODE ACTIVE, ROI NOT SET ---
if roi_method == "Draw on Map" and st.session_state['roi'] is None:
    st.info("🗺️ **Instructions:**\n1. Use the **Polygon** or **Rectangle** tool on the map sidebar.\n2. Draw your area of interest.\n3. Click the **'✅ Set as ROI'** button below to lock it.")
    
    # Instantiate Map for Drawing (Default tools are included)
    m_draw = geemap.Map(height=550, basemap="HYBRID", center=[20.59, 78.96], zoom=5)
    
    # Capture map output
    map_output = m_draw.to_streamlit(width=None, height=550)

    # Confirm Button Logic
    if st.button("✅ Set as ROI", type="primary"):
        # RECTIFIED CODE: Added isinstance check to prevent TypeError
        if map_output and isinstance(map_output, dict) and map_output.get('last_active_drawing'):
            drawn_geom = map_output['last_active_drawing']['geometry']
            ee_geom = geojson_to_ee(drawn_geom)
            
            if ee_geom:
                st.session_state['roi'] = ee_geom
                
                # Detect State Immediately
                with st.spinner("Locking Region & Detecting State..."):
                    detected = detect_state_from_geometry(ee_geom)
                    if detected:
                        st.session_state['detected_state'] = detected
                    else:
                        st.session_state['detected_state'] = "Custom Area"
                
                st.success("ROI Locked! Please click 'RUN ANALYSIS' in the sidebar.")
                st.rerun()
        else:
            st.warning("⚠️ No drawing detected! Please draw a polygon on the map first.")

# --- CASE 2: ROI IS SET BUT NOT CALCULATED YET ---
elif not st.session_state['calculated']:
    st.info(f"👈 ROI Locked ({st.session_state.get('detected_state', 'Unknown')}). Please click **RUN ANALYSIS** in the sidebar.")
    m = get_safe_map(500)
    if st.session_state['roi']:
        m.centerObject(st.session_state['roi'], 12)
        m.addLayer(ee.Image().paint(st.session_state['roi'], 2, 3), {'palette': 'yellow'}, 'ROI')
    m.to_streamlit()

# --- CASE 3: ANALYSIS RESULTS ---
else:
    roi = st.session_state['roi']
    mode = st.session_state['mode']
    p = st.session_state['params']

    col_map, col_res = st.columns([3, 1])
    m = get_safe_map(700)
    m.centerObject(roi, 13)
    image_to_export = None
    vis_export = {}

    # ==========================================
    # LOGIC A: RAINFALL & CLIMATE
    # ==========================================
    if mode == "🌦️ Rainfall & Climate Analysis":
        with st.spinner("Processing Meteorological Data..."):
            try:
                # 1. Dataset Selection
                col = None
                rain_band = ''
                scale_res = 5000 # Meters

                if "CHIRPS" in p['dataset']:
                    col = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(p['start'], p['end']).filterBounds(roi)
                    rain_band = 'precipitation'
                    scale_res = 5566 
                elif "GPM" in p['dataset']:
                    col = ee.ImageCollection("NASA/GPM_L3/IMERG_V06").filterDate(p['start'], p['end']).filterBounds(roi)
                    rain_band = 'precipitationCal'
                    scale_res = 10000 

                if col.size().getInfo() == 0:
                    st.error("No data found for the selected date range.")
                else:
                    main_layer = None
                    legend_title = ""
                    vis_params_rain = {}

                    if "Accumulation" in p['calc_mode']:
                        main_layer = col.select(rain_band).sum().clip(roi)
                        stats = main_layer.reduceRegion(ee.Reducer.minMax(), roi, scale=scale_res, bestEffort=True).getInfo()
                        min_val = stats.get(f'{rain_band}_min', 0)
                        max_val = stats.get(f'{rain_band}_max', 500)
                        
                        vis_params_rain = {'min': min_val, 'max': max_val, 'palette': ['#ffffcc', '#a1dab4', '#41b6c4', '#225ea8', '#081d58']}
                        legend_title = "Total Rainfall (mm)"
                        
                    elif "Anomaly" in p['calc_mode']:
                        current_sum = col.select(rain_band).sum().clip(roi)
                        start_dt = datetime.strptime(p['start'], "%Y-%m-%d")
                        end_dt = datetime.strptime(p['end'], "%Y-%m-%d")
                        baseline_years = range(start_dt.year - 5, start_dt.year)
                        baseline_imgs = []
                        for y in baseline_years:
                            s = start_dt.replace(year=y).strftime("%Y-%m-%d")
                            e = end_dt.replace(year=y).strftime("%Y-%m-%d")
                            baseline_imgs.append(ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(s, e).select('precipitation').sum())
                        ltm = ee.ImageCollection(baseline_imgs).mean().clip(roi)
                        main_layer = current_sum.subtract(ltm).divide(ltm).multiply(100).rename('anomaly')
                        vis_params_rain = {'min': -50, 'max': 50, 'palette': ['red', 'orange', 'white', 'cyan', 'blue']}
                        legend_title = "Rainfall Anomaly (%)"

                    m.addLayer(main_layer, vis_params_rain, legend_title)
                    m.add_colorbar(vis_params_rain, label=legend_title)
                    
                    image_to_export = main_layer
                    vis_export = vis_params_rain

                    with col_res:
                        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                        st.markdown('<div class="card-label">📈 STATISTICS</div>', unsafe_allow_html=True)
                        roi_mean = main_layer.reduceRegion(ee.Reducer.mean(), roi, scale=scale_res, bestEffort=True).values().get(0).getInfo()
                        unit = "mm" if "Accumulation" in p['calc_mode'] else "%"
                        st.metric("Region Average", f"{roi_mean:.1f} {unit}")
                        st.markdown("</div>", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Error in Rainfall Module: {e}")

    # ==========================================
    # LOGIC B: RAINWATER HARVESTING SUITABILITY
    # ==========================================
    elif mode == "💧 Rainwater Harvesting Potential":
        with st.spinner("Calculating Multi-Criteria Hydrological Suitability..."):
            try:
                # 1. Inputs
                # Rainfall (Norm)
                chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").filterDate('2020-01-01', '2023-12-31').filterBounds(roi)
                rain_mean = chirps.reduce(ee.Reducer.mean()).clip(roi)
                min_max_r = rain_mean.reduceRegion(ee.Reducer.minMax(), roi, 5000, bestEffort=True).getInfo()
                r_min = min_max_r.get('precipitation_mean_min', 0)
                r_max = min_max_r.get('precipitation_mean_max', 2000)
                norm_rain = rain_mean.unitScale(r_min, r_max)

                # Slope (Norm: Flatter is better 2-8%)
                dem = ee.Image("USGS/SRTMGL1_003").clip(roi)
                slope = ee.Terrain.slope(dem)
                # Invert: High slope = 0 suitability, Low slope = 1
                norm_slope = slope.unitScale(0, 30).multiply(-1).add(1).clamp(0, 1)

                # Drainage (Flow Acc)
                flow_acc = ee.Image("WWF/HydroSHEDS/15ACC").clip(roi)
                log_flow = flow_acc.log()
                norm_drain = log_flow.unitScale(0, 12).clamp(0, 1)

                # Soil (OpenLandMap)
                soil_tex = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02").clip(roi)
                # Remap based on structure type
                soil_weights = []
                # Classes: 1:Clay... 12:Sand
                if "Pond" in p['type']: 
                    # Prefer Clay (1,2,6) for storage
                    soil_suit = soil_tex.remap([1,2,3,4,5,6,7,8,9,10,11,12], 
                                             [1.0, 0.9, 0.7, 0.6, 0.5, 0.9, 0.5, 0.4, 0.3, 0.4, 0.1, 0.2])
                else: 
                    # Prefer Sand/Loam (9,10,11,12) for recharge
                    soil_suit = soil_tex.remap([1,2,3,4,5,6,7,8,9,10,11,12], 
                                             [0.1, 0.2, 0.3, 0.4, 0.5, 0.3, 0.6, 0.7, 0.9, 0.9, 1.0, 0.9])
                
                # LULC (ESA WorldCover)
                esa = ee.ImageCollection("ESA/WorldCover/v100").first().clip(roi)
                # 40:Ag(1.0), 30:Grass(0.9), 50:Urban(0.0)
                lulc_suit = esa.remap([10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100],
                                    [0.6, 0.8, 0.9, 1.0, 0.0, 0.1, 0.2, 0.0, 0.5, 0.0, 0.1])

                # 2. Weighted Overlay
                ws = p['w']
                final_idx = (norm_rain.multiply(ws['rain'])) \
                    .add(norm_slope.multiply(ws['slope'])) \
                    .add(soil_suit.multiply(ws['soil'])) \
                    .add(lulc_suit.multiply(ws['lulc'])) \
                    .add(norm_drain.multiply(ws['drain']))
                
                final_idx = final_idx.rename('suitability')
                
                # 3. Visualization
                vis_suit = {'min': 0, 'max': 0.8, 'palette': ['red', 'orange', 'yellow', 'green', 'darkgreen']}
                
                m.addLayer(norm_rain, {'min':0, 'max':1, 'palette':['white','blue']}, 'Rainfall Input', False)
                m.addLayer(norm_slope, {'min':0, 'max':1, 'palette':['black','white']}, 'Slope Input', False)
                m.addLayer(final_idx, vis_suit, 'RWH Suitability Index')
                m.add_colorbar(vis_suit, label="Suitability Index (0-1)")
                
                # High Potential Zones
                high_pot = final_idx.updateMask(final_idx.gt(0.65))
                m.addLayer(high_pot, {'palette':['cyan']}, 'High Potential Zones (>0.65)')
                
                image_to_export = final_idx
                vis_export = vis_suit
                
                with col_res:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.markdown('<div class="card-label">📊 MODEL STATS</div>', unsafe_allow_html=True)
                    
                    mean_suit = final_idx.reduceRegion(ee.Reducer.mean(), roi, scale=1000, bestEffort=True).values().get(0).getInfo()
                    st.metric("Avg Suitability", f"{mean_suit:.2f} / 1.0")
                    
                    st.markdown("**Criteria Weights:**")
                    st.progress(ws['rain'], text="Rain")
                    st.progress(ws['slope'], text="Slope")
                    st.progress(ws['soil'], text="Soil")
                    st.caption(f"Structure: {p['type']}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"RWH Analysis Error: {e}")

    # ==========================================
    # LOGIC C: ENCROACHMENT DETECTION
    # ==========================================
    elif mode == "⚠️ Encroachment (S1 SAR)":
        with st.spinner("Processing Sentinel-1 SAR Data..."):

            def get_sar_collection(start_d, end_d, roi_geom, orbit_pass):
                s1 = ee.ImageCollection('COPERNICUS/S1_GRD')\
                    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))\
                    .filter(ee.Filter.eq('instrumentMode', 'IW'))\
                    .filterDate(start_d, end_d)\
                    .filterBounds(roi_geom)
                if orbit_pass != "BOTH":
                    s1 = s1.filter(ee.Filter.eq('orbitProperties_pass', orbit_pass))
                return s1

            def process_water_mask(col, roi_geom):
                if col.size().getInfo() == 0: return None, "N/A"
                date_found = ee.Date(col.first().get('system:time_start')).format('YYYY-MM-dd').getInfo()
                def speckle_filter(img): return img.select('VV').focal_median(50, 'circle', 'meters').rename('VV_smoothed')
                mosaic = col.map(speckle_filter).min().clip(roi_geom)
                water_mask = mosaic.lt(-16).selfMask()
                return water_mask, date_found

            try:
                col_initial = get_sar_collection(p['d1_start'], p['d1_end'], roi, p['orbit'])
                col_final = get_sar_collection(p['d2_start'], p['d2_end'], roi, p['orbit'])

                water_initial, date_init = process_water_mask(col_initial, roi)
                water_final, date_fin = process_water_mask(col_final, roi)

                if water_initial and water_final:
                    encroachment = water_initial.unmask(0).And(water_final.unmask(0).Not()).selfMask()
                    new_water = water_initial.unmask(0).Not().And(water_final.unmask(0)).selfMask()
                    stable_water = water_initial.unmask(0).And(water_final.unmask(0)).selfMask()

                    change_map = ee.Image(0).where(stable_water, 1).where(encroachment, 2).where(new_water, 3).clip(roi).selfMask()
                    image_to_export = change_map
                    vis_export = {'min': 1, 'max': 3, 'palette': ['cyan', 'red', 'blue']}

                    left_layer = geemap.ee_tile_layer(water_initial, {'palette': 'blue'}, "Initial Water")
                    right_layer = geemap.ee_tile_layer(water_final, {'palette': 'cyan'}, "Final Water")
                    m.split_map(left_layer, right_layer)

                    m.addLayer(encroachment, {'palette': 'red'}, '🔴 Encroachment (Loss)')
                    m.addLayer(new_water, {'palette': 'blue'}, '🔵 New Water (Gain)')

                    pixel_area = encroachment.multiply(ee.Image.pixelArea())
                    val_loss = pixel_area.reduceRegion(ee.Reducer.sum(), roi, 10, maxPixels=1e9).values().get(0).getInfo()
                    loss_ha = round((val_loss or 0) / 10000, 2)

                    pixel_area_gain = new_water.multiply(ee.Image.pixelArea())
                    val_gain = pixel_area_gain.reduceRegion(ee.Reducer.sum(), roi, 10, maxPixels=1e9).values().get(0).getInfo()
                    gain_ha = round((val_gain or 0) / 10000, 2)

                    with col_res:
                        st.markdown('<div class="alert-card">', unsafe_allow_html=True)
                        st.markdown(f"### ⚠️ Change Report")
                        st.metric("🔴 Water Loss", f"{loss_ha} Ha", help="Potential Encroachment")
                        st.metric("🔵 Water Gain", f"{gain_ha} Ha", help="Flooding/New Storage")

                        st.markdown(f"""
                        <div class="date-badge">📅 Base: {date_init}</div>
                        <div class="date-badge">📅 Curr: {date_fin}</div>
                        """, unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                        st.markdown('<div class="card-label">⏱️ TIMELAPSE</div>', unsafe_allow_html=True)
                        if st.button("Create Timelapse"):
                            with st.spinner("Generating GIF..."):
                                try:
                                    s1_tl = get_sar_collection(p['d1_start'], p['d2_end'], roi, p['orbit']).select('VV')
                                    video_args = {'dimensions': 600, 'region': roi, 'framesPerSecond': 5, 'min': -25, 'max': -5, 'palette': ['black', 'blue', 'white']}
                                    monthly = geemap.create_timeseries(s1_tl, p['d1_start'], p['d2_end'], frequency='year', reducer='median')
                                    gif_url = monthly.getVideoThumbURL(video_args)
                                    st.image(gif_url, caption="Radar Intensity (Dark=Water)", use_container_width=True)
                                except Exception as e: st.error(f"Timelapse Error: {e}")
                        st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.warning("Insufficient SAR data for selected dates and orbit.")
                    image_to_export = ee.Image(0)
            except Exception as e:
                st.error(f"Computation Error: {e}")

    # ==========================================
    # LOGIC D: FLOOD EXTENT MAPPING
    # ==========================================
    elif mode == "Flood Extent Mapping":
        with st.spinner("Processing Flood Extent..."):
            try:
                collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
                    .filter(ee.Filter.eq('instrumentMode', 'IW')) \
                    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
                    .filter(ee.Filter.eq('resolution_meters', 10)) \
                    .filterBounds(roi) \
                    .select('VH')

                if p['orbit'] != "BOTH":
                    collection = collection.filter(ee.Filter.eq('orbitProperties_pass', p['orbit']))

                before_col = collection.filterDate(p['pre_start'], p['pre_end'])
                after_col = collection.filterDate(p['post_start'], p['post_end'])

                if before_col.size().getInfo() > 0 and after_col.size().getInfo() > 0:
                    date_pre = ee.Date(before_col.first().get('system:time_start')).format('YYYY-MM-dd').getInfo()
                    date_post = ee.Date(after_col.first().get('system:time_start')).format('YYYY-MM-dd').getInfo()

                    before = before_col.median().clip(roi)
                    after = after_col.mosaic().clip(roi)

                    smoothing = 50
                    before_f = before.focal_mean(smoothing, 'circle', 'meters')
                    after_f = after.focal_mean(smoothing, 'circle', 'meters')

                    difference = after_f.divide(before_f)
                    difference_binary = difference.gt(p['threshold'])

                    gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
                    occurrence = gsw.select('occurrence')
                    permanent_water_mask = occurrence.gt(30)

                    flooded = difference_binary.updateMask(permanent_water_mask.Not())

                    dem = ee.Image('WWF/HydroSHEDS/03VFDEM')
                    slope = ee.Algorithms.Terrain(dem).select('slope')
                    flooded = flooded.updateMask(slope.lt(5))

                    flooded = flooded.updateMask(flooded.connectedPixelCount().gte(8))
                    flooded = flooded.selfMask()

                    image_to_export = flooded
                    vis_export = {'min': 0, 'max': 1, 'palette': ['#0000FF']}

                    m.addLayer(before_f, {'min': -25, 'max': 0}, 'Before Flood (Dry)', False)
                    m.addLayer(after_f, {'min': -25, 'max': 0}, 'After Flood (Wet)', True)
                    m.addLayer(flooded, {'palette': ['#0000FF']}, '🌊 Estimated Flood Extent')

                    flood_stats = flooded.multiply(ee.Image.pixelArea()).reduceRegion(reducer=ee.Reducer.sum(), geometry=roi, scale=10, bestEffort=True)
                    flood_area_ha = round(flood_stats.values().get(0).getInfo() / 10000, 2)

                    with col_res:
                        st.markdown('<div class="alert-card">', unsafe_allow_html=True)
                        st.markdown("### 🌊 Flood Report")
                        st.metric("Estimated Extent", f"{flood_area_ha} Ha")
                        st.markdown(f"""
                        <div class="date-badge">📅 Pre: {date_pre}</div>
                        <div class="date-badge">📅 Post: {date_post}</div>
                        """, unsafe_allow_html=True)
                        st.caption(f"Orbit: {p['orbit']} | Pol: VH")
                        st.markdown("</div>", unsafe_allow_html=True)

                else:
                    st.error(f"No images found for Orbit: {p['orbit']} in these dates.")

            except Exception as e:
                st.error(f"Error: {e}")

    # ==========================================
    # LOGIC E: WATER QUALITY (Sentinel-2)
    # ==========================================
    elif mode == "🧪 Water Quality":
        with st.spinner(f"Computing {p['param']} (Scientific Mode)..."):
            try:
                # 1. PRE-PROCESSING FUNCTION (Improved Masking)
                def mask_clouds_and_water(img):
                    # Cloud Masking (using S2_CLOUD_PROBABILITY)
                    cloud_prob = ee.Image(img.get('cloud_mask')).select('probability')
                    is_cloud = cloud_prob.gt(p['cloud'])

                    # Scale Bands to Reflectance (0 to 1)
                    bands = img.select(['B.*']).multiply(0.0001)

                    # Water Masking (NDWI > 0.0)
                    ndwi = bands.normalizedDifference(['B3', 'B8']).rename('ndwi')
                    is_water = ndwi.gt(0.0)

                    return bands.updateMask(is_cloud.Not()).updateMask(is_water).copyProperties(img, ['system:time_start'])

                # 2. LOAD COLLECTIONS
                s2_sr = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(p['start'], p['end']).filterBounds(roi)
                s2_cloud = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterDate(p['start'], p['end']).filterBounds(roi)

                # Join collections
                s2_joined = ee.Join.saveFirst('cloud_mask').apply(
                    primary=s2_sr, secondary=s2_cloud,
                    condition=ee.Filter.equals(leftField='system:index', rightField='system:index')
                )

                processed_col = ee.ImageCollection(s2_joined).map(mask_clouds_and_water)

                # 3. COMPUTE SCIENTIFIC INDICES
                viz_params = {}
                result_layer = None
                layer_name = ""

                if "Turbidity" in p['param']:
                    def calc_ndti(img):
                        ndti = img.normalizedDifference(['B4', 'B3']).rename('value')
                        return ndti.copyProperties(img, ['system:time_start'])

                    final_col = processed_col.map(calc_ndti)
                    result_layer = final_col.mean().clip(roi)
                    viz_params = {'min': -0.15, 'max': 0.15, 'palette': ['0000ff', '00ffff', 'ffff00', 'ff0000']}
                    layer_name = "Turbidity Index (NDTI)"

                elif "TSS" in p['param']:
                    def calc_tss(img):
                        tss = img.expression('2950 * (b4 ** 1.357)', {'b4': img.select('B4')}).rename('value')
                        return tss.copyProperties(img, ['system:time_start'])

                    final_col = processed_col.map(calc_tss)
                    result_layer = final_col.median().clip(roi)
                    viz_params = {'min': 0, 'max': 50, 'palette': ['0000ff', '00ffff', 'ffff00', 'ff0000', '5c0000']}
                    layer_name = "TSS (Est. mg/L)"

                elif "Cyanobacteria" in p['param']:
                    def calc_cyano(img):
                        cyano = img.expression('b5 / b4', {
                            'b5': img.select('B5'), 'b4': img.select('B4')
                        }).rename('value')
                        return cyano.copyProperties(img, ['system:time_start'])

                    final_col = processed_col.map(calc_cyano)
                    result_layer = final_col.max().clip(roi)
                    viz_params = {'min': 0.8, 'max': 1.5, 'palette': ['0000ff', '00ff00', 'ff0000']}
                    layer_name = "Cyano Risk (Ratio > 1)"

                elif "Chlorophyll" in p['param']:
                    def calc_ndci(img):
                        ndci = img.normalizedDifference(['B5', 'B4']).rename('value')
                        return ndci.copyProperties(img, ['system:time_start'])

                    final_col = processed_col.map(calc_ndci)
                    result_layer = final_col.mean().clip(roi)
                    viz_params = {'min': -0.1, 'max': 0.2, 'palette': ['0000ff', '00ffff', '00ff00', 'ff0000']}
                    layer_name = "Chlorophyll-a (NDCI)"

                elif "CDOM" in p['param']:
                    def calc_cdom(img):
                        cdom = img.expression('b3 / b2', {
                            'b3': img.select('B3'), 'b2': img.select('B2')
                        }).rename('value')
                        return cdom.copyProperties(img, ['system:time_start'])

                    final_col = processed_col.map(calc_cdom)
                    result_layer = final_col.median().clip(roi)
                    viz_params = {'min': 0.5, 'max': 2.0, 'palette': ['0000ff', 'yellow', 'brown']}
                    layer_name = "CDOM Proxy (Green/Blue)"

                # 4. VISUALIZATION
                if result_layer:
                    image_to_export = result_layer
                    vis_export = viz_params
                    m.addLayer(result_layer, viz_params, layer_name)
                    m.add_colorbar(viz_params, label=layer_name)

                    # 5. CHARTING
                    with col_res:
                        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                        st.markdown(f'<div class="card-label">📈 TREND ANALYSIS</div>', unsafe_allow_html=True)
                        try:
                            def get_stats(img):
                                date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
                                val = img.reduceRegion(
                                    reducer=ee.Reducer.median(),
                                    geometry=roi,
                                    scale=20,
                                    maxPixels=1e9
                                ).values().get(0)
                                return ee.Feature(None, {'date': date, 'value': val})

                            fc = final_col.map(get_stats).filter(ee.Filter.notNull(['value']))
                            data_list = fc.reduceColumns(ee.Reducer.toList(2), ['date', 'value']).get('list').getInfo()

                            if data_list:
                                df_chart = pd.DataFrame(data_list, columns=['Date', 'Value'])
                                df_chart['Date'] = pd.to_datetime(df_chart['Date'])
                                df_chart = df_chart.sort_values('Date').dropna()

                                st.area_chart(df_chart, x='Date', y='Value', color="#005792")
                                st.caption(f"Median {layer_name} over time")

                                # Export Data CSV
                                csv = df_chart.to_csv(index=False).encode('utf-8')
                                st.download_button("Download CSV", csv, "water_quality_ts.csv", "text/csv")
                            else:
                                st.warning("No clear water pixels found (Try reducing cloud threshold).")

                        except Exception as e:
                            st.warning(f"Chart Error: {e}")
                        st.markdown('</div>', unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Analysis Failed: {e}")

    # --- COMMON EXPORT TOOLS ---
    with col_res:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-label">📥 EXPORTS</div>', unsafe_allow_html=True)

        if st.button("Save to Drive (GeoTIFF)"):
            if image_to_export:
                desc = f"GeoSarovar_{mode.split(' ')[1]}_{datetime.now().strftime('%Y%m%d')}"
                ee.batch.Export.image.toDrive(
                    image=image_to_export, description=desc,
                    scale=30, region=roi, folder='GeoSarovar_Exports'
                ).start()
                st.toast("Export started! Check Google Drive.")
            else:
                st.warning("No result to export.")

        st.markdown("---")
        report_title = st.text_input("Report Title", f"Analysis: {mode}")
        if st.button("Generate Map Image"):
            with st.spinner("Rendering..."):
                if image_to_export:
                    # Determine visualization type
                    is_cat = False
                    c_names = None
                    cmap = None

                    if mode == "Flood Extent Mapping":
                        is_cat = True; c_names = ['Flood Extent']
                    elif mode == "⚠️ Encroachment (S1 SAR)":
                        is_cat = True; c_names = ['Stable Water', 'Encroachment', 'New Water']
                    elif 'palette' in vis_export:
                        cmap = vis_export['palette']

                    buf = generate_static_map_display(image_to_export, roi, vis_export, report_title, cmap_colors=cmap, is_categorical=is_cat, class_names=c_names)
                    if buf:
                        st.download_button("Download JPG", buf, "GeoSarovar_Map.jpg", "image/jpeg", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_map:
        m.to_streamlit()
