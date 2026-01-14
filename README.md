# 💧 **GeoSarovar** – Intelligent Rainwater Harvesting Site Selection

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Geospatial](https://img.shields.io/badge/Geospatial-Water%20Conservation-cyan)](#)
[![Status: Active](https://img.shields.io/badge/Status-Active-success)](#)

---

## 📋 **Overview**

**GeoSarovar** is an advanced geospatial intelligence platform designed to identify optimal locations for constructing **Amrit Sarovar** rainwater harvesting structures. By integrating satellite imagery, topographic analysis, and hydrological data, GeoSarovar enables scientists and water resource managers to make evidence-based decisions for sustainable water conservation infrastructure.

### 🎯 **Core Mission**

Scientific planning of rainwater harvesting systems to ensure water conservation is implemented at strategically optimal locations, maximizing recharge rates and community benefit.

---

## ✨ **Key Features**

### **🌍 Multi-Source Geospatial Analysis**

- **Satellite Imagery Integration**: Sentinel-2, Landsat data for land cover analysis
- **DEM & Topographic Analysis**: Slope, aspect, curvature computation for optimal site selection
- **Hydrological Modeling**: Runoff estimation, infiltration analysis, groundwater potential mapping
- **Vector Analytics**: Water body mapping, drainage network extraction, watershed delineation

### **💧 Hydrological Assessment**

- **Runoff Calculation**: Rainfall-runoff modeling using soil properties and LULC data
- **Infiltration Analysis**: Soil permeability assessment and recharge potential evaluation
- **Groundwater Potential**: Integration of geological, pedological, and geomorphological parameters
- **Water Availability Index**: Composite scoring for site suitability

### **🔍 Spatial Multi-Criteria Analysis**

- **Weighted Overlay Analysis**: Combine multiple criteria with user-defined weights
- **Site Suitability Scoring**: 0-100 index for rainwater harvesting potential
- **Constraint Mapping**: Exclude unsuitable areas (protected zones, urban areas)
- **Priority Zoning**: Identify high, medium, low suitability zones

### **📊 Analytics & Reporting**

- **Site Ranking**: List potential locations by suitability score
- **Spatial Visualization**: Publication-ready maps with legends and scale bars
- **Hydrological Metrics**: Water yield potential, infiltration rates, storage capacity
- **Statistical Analysis**: Distribution analysis, hotspot identification

### **💾 Data Export**

- **GeoTIFF Rasters**: Cloud-optimized geospatial data for GIS analysis
- **Shapefile Vectors**: Point/polygon site recommendations
- **Report Generation**: Automated PDF reports with analysis methodology

---

## 🚀 **Quick Start**

### **Prerequisites**

- Python 3.8+
- GDAL/GEOS libraries
- Satellite imagery access (Sentinel-2, Landsat)
- DEM data (SRTM 30m recommended)

### **Installation**

```bash
# Clone repository
git clone https://github.com/nitesh4004/GeoSarovar.git
cd GeoSarovar

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run Streamlit application
streamlit run streamlit_app.py
```

### **Access Application**

Open browser to `http://localhost:8501`

---

## 📂 **Project Structure**

```
GeoSarovar/
├── streamlit_app.py          # Main Streamlit web interface
├── requirements.txt          # Python dependencies
├── README.md                 # Documentation
├── geosar ovar.png          # Project branding
├── packages.txt             # Package specifications
└── .devcontainer/           # Docker development environment
```

---

## 🧪 **Methodology**

### **1. Data Preparation**

| Data Type | Source | Resolution | Application |
|-----------|--------|------------|-------------|
| **DEM** | SRTM/ASTER | 30m | Slope, aspect, curvature |
| **Rainfall** | IMD/MERRA2 | 0.25°-5km | Runoff calculation |
| **Soil** | ISRIC/NBSS | 250m | Infiltration rate |
| **LULC** | Sentinel-2/Landsat | 10-30m | Land cover classification |
| **Geology** | GSI/Published maps | Vector | Permeability assessment |

### **2. Suitability Criteria**

| Criterion | Weight | Low | Medium | High |
|-----------|--------|-----|--------|------|
| **Slope** | 25% | >30° | 10-30° | <10° |
| **Rainfall** | 20% | <400mm | 400-800mm | >800mm |
| **Infiltration** | 20% | <5cm/hr | 5-10cm/hr | >10cm/hr |
| **LULC** | 20% | Urban/Water | Mix crops/trees | Barren/grass |
| **Distance to roads** | 15% | <500m | 500-1500m | >1500m |

### **3. Site Ranking**

Final suitability score calculated using:

**Suitability = Σ (Criterion Value × Weight)**

Range: 0-100 (Higher = Better)

---

## 💡 **Use Cases**

1. **District-Level Water Security Planning**
   - Multi-block rainwater harvesting infrastructure planning
   - Climate-adaptive water resource management

2. **Agricultural Water Management**
   - Irrigation pond placement for crop productivity
   - Aquifer recharge optimization

3. **Rural Development**
   - PMKSY-AIBP implementation planning
   - Community water security projects

4. **Environmental Assessment**
   - Drought mitigation strategy formulation
   - Hydrological balance restoration

5. **Urban-Rural Integration**
   - Integrated water management for peri-urban regions
   - Flood risk reduction through retention structures

---

## 📊 **Technical Stack**

| Component | Technology | Purpose |
|-----------|-----------|----------|
| **Frontend** | Streamlit | Interactive web interface |
| **Geospatial** | GeoPandas, Rasterio | Vector/raster operations |
| **Analysis** | GDAL/GEOS, NumPy, SciPy | Spatial algorithms |
| **Visualization** | Folium, Leaflet.js | Interactive mapping |
| **Data Processing** | Pandas | Tabular data handling |
| **Deployment** | Streamlit Cloud | Cloud hosting |

---

## 🤝 **Contributing**

Contributions welcome! To contribute:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/enhancement`
3. Commit changes: `git commit -m "Add feature"`
4. Push to branch: `git push origin feature/enhancement`
5. Open Pull Request

---

## 📜 **License**

MIT License – See LICENSE file for details.

---

## 📬 **Contact & Support**

**Author:** Nitesh Kumar  
**Role:** Geospatial Data Scientist  
**Email:** nitesh.gulzar@gmail.com  
**GitHub:** [@nitesh4004](https://github.com/nitesh4004)  
**Portfolio:** [nitesh4004.github.io](https://nitesh4004.github.io/)  

### **Support Channels**

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/nitesh4004/GeoSarovar/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/nitesh4004/GeoSarovar/discussions)
- 📧 **Email**: For custom implementations or consultancy

---

## 🎯 **Roadmap**

- [ ] Groundwater model integration (FEFLOW)
- [ ] Climate scenario planning (RCP 4.5/8.5)
- [ ] Real-time rainfall monitoring integration
- [ ] Mobile app for field verification
- [ ] API for programmatic access

---

## 📚 **References**

- [Amrit Sarovar Scheme - MoJWS](https://pib.gov.in/PressReleasePage.aspx?PRID=1696816)
- [SRTM DEM Data](https://earthexplorer.usgs.gov/)
- [Sentinel-2 Documentation](https://sentinel.esa.int/web/sentinel/missions/sentinel-2)
- [Hydrological Modeling - USGS](https://www.usgs.gov/faqs/what-difference-between-runoff-and-infiltration)

---

**Made with 💧 by Nitesh Kumar | GIS Engineer @ SWANSAT OPC Pvt. Ltd**
