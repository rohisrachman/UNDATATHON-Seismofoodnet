import ft2font
import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import folium_static
from folium.plugins import MarkerCluster
from shapely.geometry import shape
from folium.features import Choropleth, GeoJson
import json
from geopy.distance import great_circle
import matplotlib.pyplot as plt
import plotly.express as px
import openpyxl

# Title of the Streamlit app
st.set_page_config(layout="wide", page_title="Seismofoodnet", initial_sidebar_state="collapsed")

st.markdown('<h1 style="color: lightblue;">Seismofoodnet</h1>', unsafe_allow_html=True)

# Load your spatial data
spasialdata = gpd.read_file("data/all_kabkota_ind.geojson")
hasil1 = pd.read_excel("data/Hasil2 OK - Order JSON1.xlsx", engine='openpyxl')
datasungai = gpd.read_file("data/RIVER/IDN_water_areas_dcw.shp")
datagempa = pd.read_excel("data/Datagempa.xlsx", engine='openpyxl')

#join data
hasilspasial = pd.merge(spasialdata, hasil1, on=['name'], how='inner')
hasilspasial['korel'] = hasilspasial['korel'].fillna(0)

hasilspasialsungai = gpd.overlay(datasungai, hasilspasial, how='intersection')
sungai_layer = folium.FeatureGroup(name='Rivers')

x_map=hasilspasial.centroid.x.mean()
y_map=hasilspasial.centroid.y.mean()

def create_map(datagempa, datasungai, y_map, x_map):
    my_map2 = folium.Map(location=[y_map, x_map], zoom_start=5, tiles=None)
    folium.TileLayer('CartoDB positron', name="Light Map", control=False).add_to(my_map2)

    locations = list(zip(datagempa['Latitude'], datagempa['Longitude']))
    marker_cluster = MarkerCluster(locations).add_to(my_map2)

    rivers_layer = folium.FeatureGroup(name='Rivers').add_to(my_map2)
    rivers_geojson = datasungai.to_json()
    parsed_geojson = json.loads(rivers_geojson)

    river_centroids = []  # List to store the centroids
    for feature in parsed_geojson['features']:
        geom = shape(feature['geometry'])
        centroid = geom.centroid
        river_centroids.append((centroid.y, centroid.x))  # Append the centroid coordinates to the list
        folium.CircleMarker(
            location=(centroid.y, centroid.x),  # (Latitude, Longitude)
            radius=2,
            color='red',
            fill=True,
            fill_color='red'
        ).add_to(my_map2)
        
    for location in locations:
        nearest_centroid = min(river_centroids, key=lambda centroid: great_circle(centroid, location).km)
        folium.PolyLine([location, nearest_centroid], color='grey', weight=1).add_to(my_map2)

    folium.GeoJson(
        rivers_geojson,
        name='Rivers',
        style_function=lambda feature: {
            'color': 'blue',
            'weight': 0.3,
            'fillOpacity': 0,
        }
    ).add_to(rivers_layer)

    return my_map2

#korelasi dan sungai
def create_choropleth_map(hasilspasial, datasungai, datagempa, y_map, x_map):
    mymap = folium.Map(location=[y_map, x_map], zoom_start=5,tiles=None)
    folium.TileLayer('CartoDB positron',name="Light Map",control=False).add_to(mymap)

    # Your scale for choropleth
    quantiles = hasilspasial['korel'].quantile([0, 0.2, 0.4, 0.6, 0.8, 1]).tolist()
    myscale = [-1, -0.54, -0.18, 0.18, 0.54, 1]

    Choropleth(
        geo_data=hasilspasial,
        name='Choropleth',
        data=hasilspasial,
        columns=['kabkot_id', 'korel'],
        key_on="feature.properties.kabkot_id",
        fill_color='YlGnBu',
        threshold_scale=myscale,
        fill_opacity=1,
        line_opacity=0.2,
        legend_name='Resident foreign population in %',
        smooth_factor=0
    ).add_to(mymap)

    # Styling function for the interactive elements
    style_function = lambda x: {'fillColor': '#ffffff', 'color':'#000000', 'fillOpacity': 0.1, 'weight': 0.1}
    highlight_function = lambda x: {'fillColor': '#000000', 'color':'#000000', 'fillOpacity': 0.50, 'weight': 0.1}

    # GeoJson for interactivity
    NIL = folium.features.GeoJson(
        hasilspasial,
        style_function=style_function,
        control=False,
        highlight_function=highlight_function,
        tooltip=folium.features.GeoJsonTooltip(
            fields=['prov_name','alt_name','korel'],
            aliases=['Provinsi :','Kabupaten : ','Korelasi :'],
            style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
        )
    )
    
    # Create a list of coordinate pairs
    locations = list(zip(datagempa['Latitude'],datagempa['Longitude']))
    # Create a folium marker cluster
    marker_cluster = MarkerCluster(locations)

    # Convert your 'datasungai' GeoDataFrame to GeoJSON
    rivers_geojson = datasungai.to_json()

    # Create a folium feature group for the rivers
    rivers_layer = folium.FeatureGroup(name='Rivers')
    # Add rivers layer
    rivers_layer = folium.FeatureGroup(name='Rivers')

    folium.GeoJson(
        datasungai.to_json(),
        name='Rivers',
        style_function=lambda feature: {
            'color': 'blue',
            'weight': 2,
            'fillOpacity': 0,
        }
    ).add_to(rivers_layer)
    
    # Combine all layers
    rivers_layer.add_to(mymap)
    marker_cluster.add_to(mymap)
    mymap.add_child(NIL)
    mymap.keep_in_front(NIL)
    folium.LayerControl().add_to(mymap)

    return mymap

def quadrant_chart(x, y, xtick_labels=None, ytick_labels=None, ax=None):

    # make the data easier to work with by putting it in a dataframe
    data = pd.DataFrame({'x': x, 'y': y})

    # let the user specify their own axes
    ax = ax if ax else plt.axes()

    # calculate averages up front to avoid repeated calculations
    y_avg = data['y'].median()
    x_avg = data['x'].median()

    # set x limits
    adj_x = max((data['x'].max() - x_avg), (x_avg - data['x'].min())) * 1.1
    lb_x, ub_x = (x_avg - adj_x, x_avg + adj_x)
    ax.set_xlim(lb_x, ub_x)

    # set y limits
    adj_y = max((data['y'].max() - y_avg), (y_avg - data['y'].min())) * 1.1
    lb_y, ub_y = (y_avg - adj_y, y_avg + adj_y)
    ax.set_ylim(lb_y, ub_y)

    # set x tick labels
    if xtick_labels:
        ax.set_xticks([(x_avg - adj_x / 2), (x_avg + adj_x / 2)])
        ax.set_xticklabels(xtick_labels)

    # set y tick labels
    if ytick_labels:
        ax.set_yticks([(y_avg - adj_y / 2), (y_avg + adj_y / 2)])
        ax.set_yticklabels(ytick_labels, rotation='vertical', va='center')

    # plot points and quadrant lines
    ax.scatter(x=data['x'], y=data['y'], c='lightblue', edgecolor='darkblue',
    zorder=99)
    ax.axvline(x_avg, c='k', lw=1)
    ax.axhline(y_avg, c='k', lw=1)

x=hasil1.iloc[:,8:13].median(axis=1)
y=hasil1.iloc[:,14:19].median(axis=1)

def set_theme():
    # Use the Streamlit theme customization to set to dark mode
    st.markdown("""
        <style>
            .main { background-color: #0E1117; }
            .reportview-container .markdown-text-container { font-family: monospace; }
            .sidebar .sidebar-content { background-color: #00172B; }
            .Widget>label { color: white; font-family: monospace; }
            .st-bb { background-color: transparent; }
            .st-at { background-color: #0E1117; }
            .st-cj { background-color: #00172B; }
            header { background-color: #00172B; }
            .css-1d391kg { padding-top: 0rem; }
        </style>
        """, unsafe_allow_html=True)

set_theme()

col1, col2 = st.columns([7,3])
with col1 :
    st.write('<span style="color: lightblue;">Choose the map type:</span>', unsafe_allow_html=True)
    map_type = st.selectbox(
        "",
        ['earthquake point', 'correlation map'],
        key='map_type_select',
    )

with col2 :
    st.markdown('<span style="color: lightblue;"> Kuadran Scatterplot</span>', unsafe_allow_html=True)

if map_type == 'earthquake point':
    # Assume create_map returns a Folium map object for mymap2
    map_result = create_map(datagempa, datasungai, y_map, x_map)
else:
    # Assume create_choropleth_map returns a Folium choropleth map object for mymap
    map_result = create_choropleth_map(hasilspasial, datasungai, datagempa, y_map, x_map)

if __name__ == '__main__':
    col1, col2 = st.columns([7,3])

    with col1 :
        if map_result is not None:
            folium_static(map_result, width=830, height=445)
    with col2:
        # Call the main function to determine and render the appropriate map
        quadrant_df = pd.DataFrame({
            'IRBI': hasil1.iloc[:, 8:13].median(axis=1),
            'Y': hasil1.iloc[:, 14:19].median(axis=1),
        })

        # Buat plot quadrant_chart dengan Plotly Express
        fig = px.scatter(quadrant_df, x='IRBI', y='Y', labels={'IRBI': 'IRBI', 'Y': 'Y'})
        fig.update_xaxes(tickvals=[quadrant_df['IRBI'].min(), quadrant_df['IRBI'].max()],
                         ticktext=['Low', 'High'], title='IRBI', tickfont=dict(size=14))
        fig.update_yaxes(title='Y', tickfont=dict(size=14))
        st.plotly_chart(fig, use_container_width=True)
