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
import plotly.express as px

# --- 1. PAGE CONFIG ---
st.set_page_config(
    page_title="geoCO - Carbon Intelligence",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Inter:wght@400;600&display=swap');

    :root {
        --bg-color: #ffffff;
        --accent-primary: #2E7D32;  /* Forest Green */
        --accent-secondary: #43A047; /* Light Green */
        --text-primary: #1B5E20;    /* Dark Green */
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
        background-color: #f1f8e9;
        border-right: 1px solid #c5e1a5;
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
        box-shadow: 0 4px 12px rgba(46, 125, 50, 0.2);
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
        background: #e8f5e9;
        border: 1px solid #a5d6a7;
        padding: 15px;
        border-radius: 12px;
        margin-bottom: 15px;
        margin-top: 15px;
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
    st.stop()

# --- STATE MANAGEMENT ---
if 'calculated' not in st.session_state: st.session_state['calculated'] = False
if 'roi' not in st.session_state: st.session_state['roi'] = None
if 'mode' not in st.session_state: st.session_state['mode'] = "🌿 Vegetation Health"
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
        ax.set_title(title, fontsize=18, fontweight='bold', pad=20, color='#1B5E20')

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
    # --- LOGO SIZE FIX ---
    # Added width=150 to reduce size
    st.image("https://github.com/nitesh4004/geoCO/blob/63c8210e57ec3ee0f21ffb6de948ae979b4ccf18/logo.png?raw=true", width=150)
    
    st.markdown("### 1. Select Module")
    app_mode = st.radio("Choose Functionality:",
                        ["🌿 Vegetation Health",
                         "💨 Carbon Stock & Credits",
                         "🌍 LULC & MRV"],
                        label_visibility="collapsed")
    st.markdown("---")

    # --- LOCATION LOGIC ---
    st.markdown("### 2. Location (ROI)")
    roi_method = st.radio("Selection Mode", ["Upload KML", "Point & Buffer", "Draw on Map"], label_visibility="collapsed")
    new_roi = None
    
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
        rad = st.number_input("Radius (m)", value=1000)
        new_roi = ee.Geometry.Point([lon, lat]).buffer(rad).bounds()
        if new_roi:
            st.session_state['roi'] = new_roi
            
    elif roi_method == "Draw on Map":
        if st.session_state['roi'] is not None:
             st.info(f"📍 ROI Set: {st.session_state.get('detected_state', 'Custom Area')}")
             if st.button("🗑️ Reset / Draw New"):
                st.session_state['roi'] = None
                st.session_state['calculated'] = False
                st.session_state['detected_state'] = None
                st.rerun()

    # --- ROI LOCKING ---
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
    
    # --- MODULE PARAMETERS ---
    if app_mode == "🌿 Vegetation Health":
        st.markdown("### 3. Analysis Parameters")
        st.markdown("**Time Range**")
        c1, c2 = st.columns(2)
        start_date = c1.date_input("Start", datetime(2023, 1, 1))
        end_date = c2.date_input("End", datetime(2023, 12, 31))
        cloud_thresh = st.slider("Cloud Tolerance (%)", 5, 50, 20)
        index_type = st.selectbox("Index", ["NDVI", "EVI", "SAVI", "NDWI"])
        
        params = {
            'start': start_date.strftime("%Y-%m-%d"),
            'end': end_date.strftime("%Y-%m-%d"),
            'cloud': cloud_thresh,
            'index': index_type
        }

    elif app_mode == "💨 Carbon Stock & Credits":
        st.markdown("### 3. Biomass Config")
        biomass_src = st.selectbox("Data Source", ["ESA CCI Biomass (Global)", "Empirical Model (NDVI-based)"])
        carbon_price = st.number_input("Carbon Price ($/Credit)", value=15.0)
        
        params = {
            'source': biomass_src,
            'price': carbon_price,
            'year': 2020 
        }

    elif app_mode == "🌍 LULC & MRV":
        st.markdown("### 3. Classification")
        st.markdown("**Monitoring Period**")
        c1, c2 = st.columns(2)
        mrv_start = c1.date_input("Start", datetime(2023, 1, 1))
        mrv_end = c2.date_input("End", datetime(2023, 6, 30))
        
        params = {
            'start': mrv_start.strftime("%Y-%m-%d"),
            'end': mrv_end.strftime("%Y-%m-%d")
        }

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
        <div class="hud-title">geoCO</div>
        <div style="color:#2E7D32; font-size:0.9rem; font-weight:600;">MODULE: {app_mode.upper()}</div>
    </div>
    <div style="text-align:right;">
        <span style="background:#e8f5e9; color:#1b5e20; padding:5px 12px; border-radius:20px; font-weight:bold; font-size:0.8rem;">CARBON OS v1.0</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Helper for Safe Map Loading
def get_safe_map(height=500):
    m = geemap.Map(height=height, basemap="HYBRID")
    return m

# --- CASE 1: DRAW MODE ACTIVE, ROI NOT SET ---
if roi_method == "Draw on Map" and st.session_state['roi'] is None:
    st.info("🗺️ **Instructions:**\n1. Select the **Polygon tool** (pentagon icon) on the map.\n2. Draw your area.\n3. Click **'✅ Set as ROI'** below.")
    
    # --- DRAW MAP FIX ---
    # We initialize the map specifically for drawing with draw_export=True
    m_draw = geemap.Map(height=550, basemap="HYBRID", center=[20.59, 78.96], zoom=5)
    
    # --- SAFETY CHECK FOR DRAW CONTROL ---
    # The AttributeError happens because some geemap versions add this by default
    # or expose it differently. We use try-except to prevent app crash.
    try:
        m_draw.add_draw_control() 
    except Exception as e:
        # If the method doesn't exist or control is already there, we pass
        pass 
    
    # Capture map output
    map_output = m_draw.to_streamlit(width=None, height=550)

    if st.button("✅ Set as ROI", type="primary"):
        # ROBUST DRAWING CHECK
        drawing_found = False
        drawn_geom = None

        if map_output and isinstance(map_output, dict):
            # Check for last_active_drawing (standard geemap return)
            if map_output.get('last_active_drawing'):
                drawn_geom = map_output['last_active_drawing']['geometry']
                drawing_found = True
            # Fallback: Check for all_drawings if last_active is missing
            elif map_output.get('all_drawings'):
                drawings = map_output['all_drawings']
                if len(drawings) > 0:
                    drawn_geom = drawings[-1]['geometry'] # Get the last one drawn
                    drawing_found = True

        if drawing_found and drawn_geom:
            ee_geom = geojson_to_ee(drawn_geom)
            
            if ee_geom:
                st.session_state['roi'] = ee_geom
                with st.spinner("Locking Region & Detecting State..."):
                    detected = detect_state_from_geometry(ee_geom)
                    if detected:
                        st.session_state['detected_state'] = detected
                    else:
                        st.session_state['detected_state'] = "Custom Area"
                
                st.success("ROI Locked! Please click 'RUN ANALYSIS' in the sidebar.")
                st.rerun()
        else:
            st.warning("⚠️ No drawing detected! Please use the Polygon tool to draw a shape first.")

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
    m.centerObject(roi, 14)
    image_to_export = None
    vis_export = {}

    # ==========================================
    # LOGIC A: VEGETATION HEALTH
    # ==========================================
    if mode == "🌿 Vegetation Health":
        with st.spinner("Processing Sentinel-2 Imagery..."):
            try:
                # 1. Cloud Masking Function
                def mask_s2_clouds(image):
                    qa = image.select('QA60')
                    cloud_bit_mask = 1 << 10
                    cirrus_bit_mask = 1 << 11
                    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
                    return image.updateMask(mask).divide(10000)

                dataset = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
                          .filterDate(p['start'], p['end'])\
                          .filterBounds(roi)\
                          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', p['cloud']))\
                          .map(mask_s2_clouds)

                if dataset.size().getInfo() == 0:
                    st.error("No clear imagery found for this period/cloud threshold.")
                else:
                    median_img = dataset.median().clip(roi)
                    
                    # 2. Index Calculation
                    computed_img = None
                    vis_params = {}
                    
                    if p['index'] == "NDVI":
                        computed_img = median_img.normalizedDifference(['B8', 'B4']).rename('NDVI')
                        vis_params = {'min': 0, 'max': 0.8, 'palette': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850']}
                    elif p['index'] == "EVI":
                        computed_img = median_img.expression(
                            '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
                                'NIR': median_img.select('B8'),
                                'RED': median_img.select('B4'),
                                'BLUE': median_img.select('B2')
                            }).rename('EVI')
                        vis_params = {'min': 0, 'max': 1, 'palette': ['white', 'green']}
                    
                    m.addLayer(median_img, {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.3}, 'RGB True Color')
                    m.addLayer(computed_img, vis_params, p['index'])
                    m.add_colorbar(vis_params, label=p['index'])

                    image_to_export = computed_img
                    vis_export = vis_params

                    # 3. Stats & Charts
                    with col_res:
                        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                        st.markdown(f'<div class="card-label">📊 {p["index"]} STATS</div>', unsafe_allow_html=True)
                        
                        stats = computed_img.reduceRegion(ee.Reducer.mean().combine(ee.Reducer.stdDev(), '', True), roi, 20).getInfo()
                        mean_val = stats.get(f'{p["index"]}_mean', 0)
                        
                        st.metric("Mean Value", f"{mean_val:.2f}")
                        
                        # Classification logic
                        if p['index'] == "NDVI":
                            status = "Healthy 🟢" if mean_val > 0.4 else "Moderate 🟡" if mean_val > 0.2 else "Poor 🔴"
                            st.metric("Veg. Condition", status)
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # Time Series
                        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                        st.markdown('<div class="card-label">📈 TREND</div>', unsafe_allow_html=True)
                        
                        ts_fc = dataset.map(lambda img: ee.Feature(None, {
                            'date': ee.Date(img.get('system:time_start')).format('YYYY-MM-dd'),
                            'value': img.normalizedDifference(['B8', 'B4']).reduceRegion(ee.Reducer.mean(), roi, 100).get('nd')
                        })).filter(ee.Filter.notNull(['value']))
                        
                        ts_data = ts_fc.reduceColumns(ee.Reducer.toList(2), ['date', 'value']).values().get(0).getInfo()
                        
                        if ts_data:
                            df = pd.DataFrame(ts_data, columns=['date', 'value'])
                            df['date'] = pd.to_datetime(df['date'])
                            st.area_chart(df.set_index('date'))
                        
                        st.markdown("</div>", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Analysis Error: {e}")

    # ==========================================
    # LOGIC B: CARBON STOCK & CREDITS
    # ==========================================
    elif mode == "💨 Carbon Stock & Credits":
        with st.spinner("Estimating Biomass & Carbon..."):
            try:
                agb_image = None
                
                if "ESA CCI" in p['source']:
                    # Use ESA CCI Biomass (Dataset year 2020)
                    dataset = ee.ImageCollection("ESA/CCI/BIOMASS/v4").filterDate('2020-01-01', '2020-12-31').first()
                    agb_image = dataset.select('agb').clip(roi)
                else:
                    # Empirical Model (Simple Sentinel-2 Proxy)
                    s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(roi).filterDate('2023-01-01', '2023-06-01').median().clip(roi)
                    ndvi = s2.normalizedDifference(['B8', 'B4'])
                    agb_image = ndvi.pow(2).multiply(100).rename('agb')

                # Carbon Calculation Logic
                carbon_density = agb_image.multiply(0.47).rename('carbon_density')
                co2e_density = carbon_density.multiply(3.67).rename('co2e_density')
                
                # Stats
                stats_agb = agb_image.multiply(ee.Image.pixelArea().divide(10000))\
                            .reduceRegion(ee.Reducer.sum(), roi, scale=100, maxPixels=1e9).get('agb').getInfo()
                
                stats_co2 = co2e_density.multiply(ee.Image.pixelArea().divide(10000))\
                            .reduceRegion(ee.Reducer.sum(), roi, scale=100, maxPixels=1e9).get('co2e_density').getInfo()

                vis_agb = {'min': 0, 'max': 300, 'palette': ['#ffffcc', '#c2e699', '#78c679', '#31a354', '#006837']}
                m.addLayer(agb_image, vis_agb, 'AGB (Mg/ha)')
                m.add_colorbar(vis_agb, label="Biomass (Mg/ha)")
                
                image_to_export = agb_image
                vis_export = vis_agb

                with col_res:
                    st.markdown('<div class="alert-card">', unsafe_allow_html=True)
                    st.markdown(f'<div class="card-label">💰 CARBON LEDGER</div>', unsafe_allow_html=True)
                    
                    total_agb = stats_agb if stats_agb else 0
                    total_co2 = stats_co2 if stats_co2 else 0
                    potential_credits = total_co2 
                    total_value = potential_credits * p['price']
                    
                    st.metric("Total Biomass (AGB)", f"{total_agb:,.1f} tons")
                    st.metric("Est. Carbon Credits", f"{potential_credits:,.1f}", delta="Credits")
                    st.metric("Potential Value", f"${total_value:,.2f}")
                    
                    st.caption("Assumption: 1 Credit = 1 Ton CO2e.")
                    st.markdown("</div>", unsafe_allow_html=True)
            
            except Exception as e:
                st.error(f"Carbon Calculation Error: {e}")

    # ==========================================
    # LOGIC C: MRV & LULC
    # ==========================================
    elif mode == "🌍 LULC & MRV":
        with st.spinner("Classifying Land Cover (Dynamic World)..."):
            try:
                dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')\
                     .filterDate(p['start'], p['end'])\
                     .filterBounds(roi)
                
                classification = dw.select('label').reduce(ee.Reducer.mode()).clip(roi)
                
                dw_vis = {
                    'min': 0, 'max': 8,
                    'palette': ['#419BDF', '#397D49', '#88B053', '#7A87C6', '#E49635', '#DFC35A', '#C4281B', '#A59B8F', '#B39FE1']
                }
                labels = ['Water', 'Trees', 'Grass', 'Flooded Veg', 'Crops', 'Shrub/Scrub', 'Built', 'Bare', 'Snow']
                
                m.addLayer(classification, dw_vis, 'Land Cover')
                m.add_legend(title="LULC Classes", labels=labels, colors=dw_vis['palette'])
                
                image_to_export = classification
                vis_export = dw_vis
                
                with col_res:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.markdown(f'<div class="card-label">🏗️ LULC BREAKDOWN</div>', unsafe_allow_html=True)
                    
                    area_image = ee.Image.pixelArea().divide(10000).addBands(classification)
                    class_areas = area_image.reduceRegion(
                        reducer=ee.Reducer.sum().group(groupField=1, groupName='class_index'),
                        geometry=roi, scale=10, maxPixels=1e9
                    ).get('groups').getInfo()
                    
                    data = []
                    for item in class_areas:
                        idx = int(item['class_index'])
                        area = item['sum']
                        if idx < len(labels):
                            data.append({'Class': labels[idx], 'Hectares': area})
                    
                    df_lulc = pd.DataFrame(data)
                    if not df_lulc.empty:
                        fig = px.pie(df_lulc, values='Hectares', names='Class', hole=0.4, color_discrete_sequence=px.colors.qualitative.Prism)
                        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=200, paper_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig, use_container_width=True)
                        st.dataframe(df_lulc.set_index('Class').style.format("{:.2f}"))
                    
                    st.markdown("</div>", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"MRV Error: {e}")

    # --- COMMON EXPORT TOOLS ---
    with col_res:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-label">📥 EXPORTS</div>', unsafe_allow_html=True)

        if st.button("Save to Drive (GeoTIFF)"):
            if image_to_export:
                desc = f"geoCO_{mode.split(' ')[1]}_{datetime.now().strftime('%Y%m%d')}"
                ee.batch.Export.image.toDrive(
                    image=image_to_export, description=desc,
                    scale=10, region=roi, folder='geoCO_Exports'
                ).start()
                st.toast("Export started! Check Google Drive.")
            else:
                st.warning("No result to export.")

        st.markdown("---")
        report_title = st.text_input("Report Title", f"Analysis: {mode}")
        if st.button("Generate Map Image"):
            with st.spinner("Rendering..."):
                if image_to_export:
                    is_cat = False
                    c_names = None
                    cmap = None
                    
                    if mode == "🌍 LULC & MRV":
                        is_cat = True; c_names = ['Water', 'Trees', 'Grass', 'FloodVeg', 'Crops', 'Shrub', 'Built', 'Bare', 'Snow']
                    elif 'palette' in vis_export:
                        cmap = vis_export['palette']

                    buf = generate_static_map_display(image_to_export, roi, vis_export, report_title, cmap_colors=cmap, is_categorical=is_cat, class_names=c_names)
                    if buf:
                        st.download_button("Download JPG", buf, "geoCO_Map.jpg", "image/jpeg", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_map:
        m.to_streamlit()
