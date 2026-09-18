from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box
from streamlit.testing.v1 import AppTest

from seismofoodnet import (
    build_map,
    clean_earthquakes,
    filter_dashboard,
    load_data,
    nearest_centers,
    prepare_regions,
    quadrant_data,
    quadrant_figure,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dataset():
    return load_data()


def test_region_keys_do_not_collide_across_provinces():
    regions = gpd.GeoDataFrame(
        {"province_id": ["11", "12", "13"], "kabkot_id": ["01"] * 3},
        geometry=[Point(95, 5), Point(99, 2), Point(100, -1)],
        crs=4326,
    )
    indicators = pd.DataFrame({"Kode.BPS": [1101, 1201], "korel": ["-0,8", "0,7"]})
    merged = prepare_regions(regions, indicators)
    assert merged.region_id.tolist() == ["1101", "1201", "1301"]
    assert merged.korel.iloc[:2].tolist() == [-0.8, 0.7]
    assert pd.isna(merged.korel.iloc[2])
    assert merged.correlation_label.iloc[2] == "Tidak tersedia"
    with pytest.raises(ValueError):
        prepare_regions(regions, pd.concat([indicators, indicators]))


def test_invalid_coordinates_are_excluded():
    data = pd.DataFrame(
        {
            "Latitude": ["-1,5", "text", 91, 0, np.inf, None],
            "Longitude": ["120,2", 120, 120, -181, 0, 0],
        }
    )
    cleaned, rejected = clean_earthquakes(data)
    assert rejected == 5
    assert cleaned[["Latitude", "Longitude"]].values.tolist() == [[-1.5, 120.2]]


def test_quadrant_uses_all_years_even_when_columns_are_reordered():
    frame = pd.DataFrame(
        {
            "Y_2022": [10],
            "IRBI.2022": [100],
            "name": ["Example"],
            "IRBI.2017": [0],
            "unrelated": [999],
            "Y_2017": ["2,0"],
        }
    )
    result = quadrant_data(frame)
    assert result.IRBI.iloc[0] == 50
    assert result.Y.iloc[0] == 6
    figure = quadrant_figure(frame)
    assert len(figure.layout.shapes) == 2


def test_nearest_centers_uses_spherical_distance_and_handles_empty_water():
    points = np.array([[0, 179.9], [80, 0]])
    centers = np.array([[0, -179.9], [0, 150], [80, 10], [75, 0]])
    np.testing.assert_array_equal(nearest_centers(points, centers), centers[[0, 2]])
    assert nearest_centers(points, np.empty((0, 2))).shape == (0, 2)
    assert nearest_centers(np.empty((0, 2)), centers).shape == (0, 2)


def test_repository_data_loads_from_any_working_directory(
    dataset, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    regions, indicators, water, earthquakes, rejected = load_data()
    assert len(regions) == len(indicators) == 514
    assert regions.region_id.is_unique
    assert regions.crs.to_epsg() == water.crs.to_epsg() == 4326
    assert regions.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    assert regions.is_valid.all()
    assert not earthquakes.empty
    assert rejected == 0
    assert regions.korel.isna().any()


@pytest.mark.parametrize("correlation", [False, True])
def test_map_renders_with_current_dependencies(dataset, correlation, monkeypatch):
    monkeypatch.delenv("SEISMO_TILE_URL", raising=False)
    monkeypatch.delenv("SEISMO_TILE_ATTRIBUTION", raising=False)
    regions, _, water, earthquakes, _ = dataset
    map_object = build_map(regions, water, earthquakes, correlation=correlation)
    html = map_object.get_root().render()
    assert np.isfinite(map_object.get_bounds()).all()
    assert "tile.openstreetmap.org" in html
    assert "cartocdn.com" not in html
    assert "OpenStreetMap" in html
    assert "L.control.layers" in html
    if correlation:
        layer = next(
            x for x in map_object._children.values() if isinstance(x, folium.Choropleth)
        )
        features = layer.geojson.data["features"]
        missing = regions.loc[regions.korel.isna(), "region_id"].iloc[0]
        feature = next(f for f in features if f["properties"]["region_id"] == missing)
        assert layer.geojson.style_function(feature)["fillColor"] == "#bdbdbd"


def test_no_water_or_earthquakes_does_not_crash(dataset):
    regions, _, water, earthquakes, _ = dataset
    assert build_map(regions, water.iloc[:0], earthquakes.iloc[:0]).get_root().render()


def test_custom_tiles_require_attribution(dataset, monkeypatch):
    regions, _, water, earthquakes, _ = dataset
    monkeypatch.setenv("SEISMO_TILE_URL", "https://example.com/{z}/{x}/{y}.png")
    monkeypatch.delenv("SEISMO_TILE_ATTRIBUTION", raising=False)
    with pytest.raises(ValueError, match="ATTRIBUTION"):
        build_map(regions, water, earthquakes)


def test_streamlit_both_map_views(monkeypatch):
    monkeypatch.delenv("SEISMO_TILE_URL", raising=False)
    app = AppTest.from_file(str(ROOT / "App.py"), default_timeout=60).run()
    assert not app.exception
    assert not app.error
    app.radio(key="map_type").set_value("Korelasi").run()
    assert not app.exception
    assert not app.error
    app.selectbox(key="province").select("31").run()
    assert not app.exception
    assert not app.error
    app.selectbox(key="magnitude").select("≥ 6").run()
    assert not app.exception
    assert len(app.info) == 1
    app.button[0].click().run()
    assert app.selectbox(key="province").value == "all"
    assert app.selectbox(key="magnitude").value == "Semua magnitudo"


def test_province_and_magnitude_filters_keep_views_consistent():
    regions = gpd.GeoDataFrame(
        {"province_id": ["11", "12"], "region_id": ["1101", "1201"]},
        geometry=[box(100, 0, 101, 1), box(101, 0, 102, 1)],
        crs=4326,
    )
    indicators = pd.DataFrame({"Kode.BPS": [1101, 1201]})
    events = pd.DataFrame(
        {
            "Latitude": [0.5, 0.5, 0.5, 0.5],
            "Longitude": [100.5, 101.5, 104, 100.2],
            "Magnitude": ["4,2", 6, 7, None],
        }
    )
    r, i, e = filter_dashboard(regions, indicators, events, "11", 4)
    assert r.region_id.tolist() == ["1101"]
    assert i["Kode.BPS"].tolist() == [1101]
    assert e.index.tolist() == [0]
    assert len(filter_dashboard(regions, indicators, events)[2]) == 4
    assert len(filter_dashboard(regions, indicators, events, "11")[2]) == 2
    assert filter_dashboard(regions, indicators, events, "11", 8)[2].empty


def test_layer_visibility_options(dataset):
    regions, _, water, earthquakes, _ = dataset
    m = build_map(regions, water, earthquakes, show_water=False, show_connections=False)
    names = [getattr(child, "layer_name", "") for child in m._children.values()]
    assert "Badan air" not in names
    assert "Koneksi ke pusat badan air" not in names
    assert "Titik gempa" in names
