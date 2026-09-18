"""Data preparation and map/chart builders, independent of the Streamlit runtime."""

import os
from html import escape
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
from folium.plugins import MarkerCluster
from plotly.graph_objects import Figure

DATA_DIR = Path(__file__).resolve().parent / "data"
OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">'
    "OpenStreetMap</a> contributors"
)


def numeric(series: pd.Series) -> pd.Series:
    """Accept spreadsheet numbers and decimal-comma strings, preserving missing data."""
    return (
        pd.to_numeric(
            series.astype("string").str.replace(",", ".", regex=False), errors="coerce"
        )
        .astype(float)
        .replace([np.inf, -np.inf], np.nan)
    )


def prepare_regions(
    regions: gpd.GeoDataFrame, indicators: pd.DataFrame
) -> gpd.GeoDataFrame:
    regions = regions.copy()
    indicators = indicators.copy()
    regions["region_id"] = regions["province_id"].astype(str).str.zfill(2) + regions[
        "kabkot_id"
    ].astype(str).str.zfill(2)
    codes = pd.to_numeric(indicators["Kode.BPS"], errors="raise")
    if codes.isna().any() or (codes % 1 != 0).any():
        raise ValueError("Kode.BPS harus berisi kode wilayah bilangan bulat.")
    indicators["region_id"] = codes.astype(int).astype(str).str.zfill(4)
    indicators["korel"] = numeric(indicators["korel"])
    valid = indicators["korel"].dropna()
    if not valid.between(-1, 1).all():
        raise ValueError("Nilai korelasi harus berada di antara -1 dan 1.")
    merged = regions.merge(
        indicators[["region_id", "korel"]],
        on="region_id",
        how="left",
        validate="one_to_one",
    )
    merged["correlation_label"] = merged["korel"].map(
        lambda value: "Tidak tersedia" if pd.isna(value) else f"{value:.3f}"
    )
    return merged


def clean_earthquakes(data: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    data = data.copy()
    for column in ("Latitude", "Longitude"):
        data[column] = numeric(data[column])
    valid = data["Latitude"].between(-90, 90) & data["Longitude"].between(-180, 180)
    return data.loc[valid].reset_index(drop=True), int((~valid).sum())


def read_spatial(path: Path) -> gpd.GeoDataFrame:
    data = gpd.read_file(path)
    if data.crs is None:
        raise ValueError(f"Sistem koordinat tidak tersedia: {path.name}")
    data = data.loc[data.geometry.notna() & ~data.geometry.is_empty].copy()
    if data.empty:
        raise ValueError(f"Data spasial kosong: {path.name}")
    # Preserve polygon surfaces: default linework repair can create collections
    # that Folium cannot inspect for bounds or attach tooltips to.
    data.geometry = data.geometry.make_valid(method="structure", keep_collapsed=False)
    if (
        data.geometry.is_empty.any()
        or not data.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    ):
        raise ValueError(f"Geometri area tidak valid: {path.name}")
    return data.to_crs(4326)


def load_data(
    data_dir: Path = DATA_DIR,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame, pd.DataFrame, int]:
    indicators = pd.read_excel(
        data_dir / "Hasil2 OK - Order JSON1.xlsx", engine="openpyxl"
    )
    regions = prepare_regions(
        read_spatial(data_dir / "all_kabkota_ind.geojson"), indicators
    )
    water = read_spatial(data_dir / "RIVER" / "IDN_water_areas_dcw.shp")
    earthquakes, rejected = clean_earthquakes(
        pd.read_excel(data_dir / "Datagempa.xlsx", engine="openpyxl")
    )
    return regions, indicators, water, earthquakes, rejected


def nearest_centers(locations: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Find nearest centers by great-circle distance, in bounded NumPy batches."""
    if len(locations) == 0 or len(centers) == 0:
        return np.empty((0, 2))
    center_radians = np.radians(centers)
    selected = []
    for start in range(0, len(locations), 128):
        points = np.radians(locations[start : start + 128])
        delta = points[:, None, :] - center_radians[None, :, :]
        haversine = (
            np.sin(delta[:, :, 0] / 2) ** 2
            + np.cos(points[:, None, 0])
            * np.cos(center_radians[None, :, 0])
            * np.sin(delta[:, :, 1] / 2) ** 2
        )
        selected.append(centers[np.argmin(haversine, axis=1)])
    return np.concatenate(selected)


def add_water_layers(
    map_object: folium.Map,
    water: gpd.GeoDataFrame,
    earthquakes: pd.DataFrame,
    connections: bool,
) -> None:
    if water.empty:
        return
    folium.GeoJson(
        water[["geometry"]],
        name="Badan air",
        style_function=lambda _: {"color": "#2474b5", "weight": 1, "fillOpacity": 0.25},
    ).add_to(map_object)
    if not connections:
        return
    # Compute centroids in a projected CRS rather than averaging longitude/latitude.
    centroids = water.to_crs(6933).centroid.to_crs(4326)
    centers = np.column_stack((centroids.y, centroids.x))
    center_layer = folium.FeatureGroup(name="Pusat badan air").add_to(map_object)
    for center in centers:
        folium.CircleMarker(
            center.tolist(), radius=2, color="#c84545", fill=True, fill_opacity=0.8
        ).add_to(center_layer)
    locations = earthquakes[["Latitude", "Longitude"]].to_numpy(dtype=float)
    lines = folium.FeatureGroup(name="Koneksi ke pusat badan air").add_to(map_object)
    for location, center in zip(locations, nearest_centers(locations, centers)):
        folium.PolyLine(
            [location.tolist(), center.tolist()], color="grey", weight=1
        ).add_to(lines)


def add_correlation(map_object: folium.Map, regions: gpd.GeoDataFrame) -> None:
    layer = folium.Choropleth(
        geo_data=regions[
            ["region_id", "prov_name", "alt_name", "correlation_label", "geometry"]
        ],
        data=regions,
        columns=["region_id", "korel"],
        key_on="feature.properties.region_id",
        name="Korelasi",
        bins=[-1, -0.54, -0.18, 0.18, 0.54, 1],
        fill_color="RdYlBu",
        fill_opacity=0.8,
        line_opacity=0.3,
        nan_fill_color="#bdbdbd",
        nan_fill_opacity=0.8,
        legend_name="Koefisien korelasi (−1 hingga 1)",
        highlight=True,
    ).add_to(map_object)
    folium.GeoJsonTooltip(
        fields=["prov_name", "alt_name", "correlation_label"],
        aliases=["Provinsi:", "Kabupaten/kota:", "Korelasi:"],
    ).add_to(layer.geojson)


def build_map(
    regions: gpd.GeoDataFrame,
    water: gpd.GeoDataFrame,
    earthquakes: pd.DataFrame,
    correlation: bool = False,
    *,
    show_connections: bool = True,
    show_water: bool = True,
    show_legend: bool = True,
) -> folium.Map:
    map_object = folium.Map(
        location=[-2.5, 118], zoom_start=5, tiles=None, prefer_canvas=True
    )
    if not regions.empty:
        west, south, east, north = regions.total_bounds
        map_object.fit_bounds([[south, west], [north, east]])
    tiles = os.environ.get("SEISMO_TILE_URL", OSM_TILES)
    attribution = os.environ.get("SEISMO_TILE_ATTRIBUTION", OSM_ATTRIBUTION)
    if tiles != OSM_TILES and not os.environ.get("SEISMO_TILE_ATTRIBUTION"):
        raise ValueError(
            "SEISMO_TILE_ATTRIBUTION wajib diisi untuk penyedia peta kustom."
        )
    folium.TileLayer(
        tiles=tiles, attr=attribution, name="Peta dasar", max_zoom=19
    ).add_to(map_object)
    if correlation:
        add_correlation(map_object, regions)
        if not show_legend:
            layer = next(
                child
                for child in map_object._children.values()
                if isinstance(child, folium.Choropleth)
            )
            layer._children.pop(layer.color_scale.get_name(), None)
    if show_water or show_connections:
        add_water_layers(
            map_object,
            water,
            earthquakes,
            connections=show_connections and not correlation,
        )
        if not show_water:
            for key, child in list(map_object._children.items()):
                if (
                    isinstance(child, folium.GeoJson)
                    and child.layer_name == "Badan air"
                ):
                    map_object._children.pop(key)
    cluster = MarkerCluster(name="Titik gempa").add_to(map_object)
    for _, event in earthquakes.iterrows():
        # Vector markers avoid broken icon URLs inside the Streamlit component.
        folium.CircleMarker(
            [event["Latitude"], event["Longitude"]],
            radius=5,
            color="#145d91",
            fill=True,
            fill_color="#318ac6",
            fill_opacity=0.9,
            tooltip=escape(str(event.get("Location", "Gempa"))),
        ).add_to(cluster)
    folium.LayerControl(collapsed=True).add_to(map_object)
    return map_object


def quadrant_data(indicators: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=indicators.index)
    result["Wilayah"] = indicators["name"]
    for label, prefix in (("IRBI", "IRBI."), ("Y", "Y_")):
        columns = [column for column in indicators if str(column).startswith(prefix)]
        if not columns:
            raise ValueError(f"Kolom {prefix} tidak ditemukan.")
        result[label] = indicators[columns].apply(numeric).median(axis=1)
    return result.dropna(subset=["IRBI", "Y"])


def quadrant_figure(indicators: pd.DataFrame) -> Figure:
    data = quadrant_data(indicators)
    figure = px.scatter(
        data, x="IRBI", y="Y", hover_name="Wilayah", color_discrete_sequence=["#087f8c"]
    )
    figure.update_traces(
        marker={"size": 7, "opacity": 0.78, "line": {"width": 0.5, "color": "white"}}
    )
    if not data.empty:
        figure.add_vline(
            x=float(data["IRBI"].median()), line_dash="dash", line_color="#888888"
        )
        figure.add_hline(
            y=float(data["Y"].median()), line_dash="dash", line_color="#888888"
        )
    figure.update_layout(
        margin={"l": 48, "r": 16, "t": 20, "b": 44},
        height=390,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#425b64", "family": "Arial, sans-serif"},
        hoverlabel={"bgcolor": "#173b43", "font_color": "white"},
    )
    figure.update_xaxes(gridcolor="#e7eeeb", zeroline=False, automargin=True)
    figure.update_yaxes(gridcolor="#e7eeeb", zeroline=False, automargin=True)
    return figure


def filter_dashboard(
    regions: gpd.GeoDataFrame,
    indicators: pd.DataFrame,
    earthquakes: pd.DataFrame,
    province_id: str = "all",
    minimum_magnitude: float | None = None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]:
    """Province filters administrative areas; offshore events remain in national view."""
    selected_regions = regions
    selected_indicators = indicators
    events = earthquakes.copy()
    if province_id != "all":
        selected_regions = regions.loc[
            regions["province_id"].astype(str) == province_id
        ]
        codes = numeric(indicators["Kode.BPS"]).astype("Int64").astype(str).str.zfill(4)
        selected_indicators = indicators.loc[codes.isin(selected_regions["region_id"])]
        points = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(events.Longitude, events.Latitude),
            index=events.index,
            crs=4326,
        )
        matches = gpd.sjoin(
            points, selected_regions[["geometry"]], predicate="intersects"
        )
        events = events.loc[events.index.isin(matches.index)]
    if minimum_magnitude is not None:
        events = events.loc[numeric(events["Magnitude"]) >= minimum_magnitude]
    return selected_regions.copy(), selected_indicators.copy(), events.copy()
