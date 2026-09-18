"""Seismofoodnet dashboard. Run with `streamlit run App.py`."""

import logging
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from seismofoodnet import (
    build_map,
    filter_dashboard,
    load_data,
    quadrant_data,
    quadrant_figure,
)

ROOT = Path(__file__).resolve().parent
MAGNITUDES = {"Semua magnitudo": None, "≥ 3": 3.0, "≥ 4": 4.0, "≥ 5": 5.0, "≥ 6": 6.0}


@st.cache_data(show_spinner="Menyiapkan peta dan data…", ttl=3600)
def cached_data():
    return load_data()


def reset_filters() -> None:
    st.session_state["province"] = "all"
    st.session_state["magnitude"] = "Semua magnitudo"


def section_heading(title: str, subtitle: str) -> None:
    st.html(
        f'<div class="sf-section-head"><h2>{escape(title)}</h2><p>{escape(subtitle)}</p></div>'
    )


def render_header() -> None:
    st.html(f"<style>{(ROOT / 'assets' / 'dashboard.css').read_text()}</style>")
    st.html("""
        <div class="sf-topbar">
          <div class="sf-brand"><span class="sf-brandmark" aria-hidden="true">∿</span>seismofoodnet<span style="color:#8ee79e">.</span></div>
          <span class="sf-topnote">Indonesia · Geospatial explorer</span>
        </div>
    """)


def render_stats(regions, indicators, earthquakes) -> None:
    cards = [
        (
            "GEMPA TERPILIH",
            f"{len(earthquakes):,}".replace(",", "."),
            "Sesuai wilayah & magnitudo",
        ),
        ("KABUPATEN / KOTA", str(len(regions)), "Dalam cakupan wilayah terpilih"),
    ]
    html = '<div class="sf-stats" aria-label="Ringkasan data terpilih">'
    for label, value, detail in cards:
        html += (
            f'<div class="sf-stat"><div class="sf-stat-label">{escape(label)}</div>'
            f'<div class="sf-stat-value">{escape(value)}</div>'
            f'<div class="sf-stat-detail">{escape(detail)}</div></div>'
        )
    st.html(html + "</div>")


def render_filters(regions) -> tuple[str, str]:
    provinces = (
        regions.groupby("province_id")["prov_name"].first().str.title().to_dict()
    )
    with st.container(key="filters"):
        left, middle, right = st.columns([2.5, 2, 1], vertical_alignment="bottom")
        with left:
            province = st.selectbox(
                "Cakupan wilayah",
                ["all", *sorted(provinces, key=provinces.get)],
                format_func=lambda value: (
                    "Seluruh Indonesia" if value == "all" else provinces[value]
                ),
                key="province",
                help="Memperbarui peta, grafik, ringkasan, dan tabel.",
            )
        with middle:
            magnitude = st.selectbox(
                "Magnitudo gempa",
                list(MAGNITUDES),
                key="magnitude",
                help="Hanya memfilter gempa. Nilai IRBI dan korelasi tidak berubah.",
            )
        with right:
            st.button("Reset filter", on_click=reset_filters, width="stretch")
    return province, magnitude


def render_explorer(
    regions, indicators, water, earthquakes, province, magnitude
) -> None:
    left, right = st.columns([1.9, 1], gap="medium")
    with left, st.container(key="map_panel"):
        section_heading(
            "Eksplorasi wilayah",
            "Pilih tampilan, lalu zoom atau arahkan kursor untuk melihat detail.",
        )
        map_type = st.radio(
            "Jenis peta", ["Titik gempa", "Korelasi"], horizontal=True, key="map_type"
        )
        with st.expander("Pengaturan layer", expanded=False):
            show_water = st.checkbox("Tampilkan badan air", value=True)
            connections = st.checkbox(
                "Hubungkan gempa ke pusat badan air",
                value=False,
                disabled=map_type == "Korelasi",
                help="Garis ke pusat area terdekat, bukan jarak ke tepi sungai.",
            )
        if earthquakes.empty:
            st.info(
                "Tidak ada gempa untuk filter ini. Coba magnitudo lebih rendah atau reset filter."
            )
        st_folium(
            build_map(
                regions,
                water,
                earthquakes,
                correlation=map_type == "Korelasi",
                show_water=show_water,
                show_connections=connections and map_type != "Korelasi",
                show_legend=False,
            ),
            height=470,
            use_container_width=True,
            returned_objects=[],
            key=f"map-{map_type}-{province}-{magnitude}-{show_water}-{connections}",
        )
        if map_type == "Korelasi":
            st.html(
                """<div class="sf-legend"><div class="sf-scale" aria-label="Skala korelasi dari minus satu hingga satu"><span>−1</span><div class="sf-scale-bar"></div><span>+1</span></div><span>Koefisien korelasi</span><span><i class="sf-dot missing"></i>Tidak tersedia</span></div>"""
            )
        else:
            st.html(
                """<div class="sf-legend"><span><i class="sf-dot"></i>Lokasi gempa</span><span>Angka pada kelompok = jumlah gempa</span></div>"""
            )
        if province != "all":
            st.caption(
                "Gempa disaring di dalam batas daratan provinsi. Pilih Seluruh Indonesia untuk menyertakan gempa lepas pantai."
            )
    with right, st.container(key="chart_panel"):
        section_heading("Pola antardaerah", "Perbandingan median IRBI dan indikator Y.")
        st.plotly_chart(
            quadrant_figure(indicators),
            width="stretch",
            theme=None,
            config={"displayModeBar": False, "scrollZoom": False},
        )
        st.html(
            """<div class="sf-insight"><strong>Cara membaca kuadran</strong><br>Garis putus-putus membagi nilai median daerah terpilih. Titik di kanan memiliki IRBI lebih tinggi; titik di atas memiliki Y lebih tinggi.</div>"""
        )
        missing = int(regions.korel.isna().sum())
        st.caption(
            f"{missing} dari {len(regions)} wilayah tidak memiliki nilai korelasi. Data kosong tidak dianggap nol."
        )
        st.caption(
            "Arahkan kursor ke titik untuk melihat nama kabupaten/kota. Filter magnitudo tidak mengubah grafik ini."
        )


def render_tables(regions, indicators, earthquakes) -> None:
    section_heading(
        "Data di balik peta",
        "Tabel dan unduhan mengikuti filter wilayah dan magnitudo di atas.",
    )
    summary = quadrant_data(indicators).rename(columns={"Wilayah": "name"})
    table = regions[["name", "prov_name", "korel"]].merge(
        summary, on="name", how="left"
    )
    table = pd.DataFrame(table).rename(
        columns={
            "name": "Kabupaten/kota",
            "prov_name": "Provinsi",
            "korel": "Korelasi",
            "IRBI": "Median IRBI",
            "Y": "Median Y",
        }
    )
    st.subheader("Indikator wilayah")
    st.dataframe(table, hide_index=True, width="stretch", height=340)
    st.download_button(
        "Unduh indikator · CSV",
        table.to_csv(index=False).encode("utf-8-sig"),
        "seismofoodnet-wilayah.csv",
        "text/csv",
        on_click="ignore",
    )
    st.subheader("Katalog gempa")
    columns = [
        column
        for column in [
            "Date time",
            "Location",
            "Magnitude",
            "Mag Type",
            "Depth (km)",
            "Latitude",
            "Longitude",
        ]
        if column in earthquakes
    ]
    events = earthquakes[columns]
    st.dataframe(events, hide_index=True, width="stretch", height=340)
    st.download_button(
        "Unduh gempa · CSV",
        events.to_csv(index=False).encode("utf-8-sig"),
        "seismofoodnet-gempa.csv",
        "text/csv",
        on_click="ignore",
    )


def render_guide() -> None:
    section_heading(
        "Mulai dari sebuah wilayah", "Tiga langkah untuk membaca dashboard."
    )
    for title, text in [
        (
            "1. Tentukan cakupan",
            "Pilih provinsi untuk memfokuskan seluruh analisis. Batas magnitudo hanya menyaring gempa; gunakan Reset filter untuk kembali ke cakupan nasional.",
        ),
        (
            "2. Jelajahi peta",
            "Pilih Titik gempa untuk sebaran kejadian atau Korelasi untuk membandingkan daerah. Klik kelompok titik untuk memperbesar peta. Layer tambahan tersedia pada Pengaturan layer.",
        ),
        (
            "3. Bandingkan dan unduh",
            "Grafik menggunakan median seluruh tahun yang tersedia. Buka Data terpilih untuk melihat angka sumber dan mengunduh CSV sesuai filter.",
        ),
    ]:
        st.subheader(title)
        st.write(text)
    with st.expander("Sumber dan batasan interpretasi", expanded=True):
        st.write(
            "Data berasal dari berkas historis repository: Datagempa.xlsx, Hasil2 OK - Order JSON1.xlsx, batas kabupaten/kota, dan shapefile area badan air. Dashboard bukan pemantauan gempa real-time."
        )
        st.write(
            "IRBI mengikuti kolom pada spreadsheet. Y tetap menggunakan nama variabel sumber karena kamus datanya belum tersedia. Nilai korelasi disajikan dari spreadsheet, bukan dihitung ulang atau bukti sebab-akibat."
        )
        st.write(
            "Pemilihan provinsi menggunakan batas geografis dalam dataset. Kejadian lepas pantai tetap muncul pada cakupan nasional. Garis badan air menunjukkan koneksi ke pusat area, bukan estimasi dampak gempa."
        )
        st.caption(
            "Peta dasar © OpenStreetMap contributors. Data dan batas wilayah mengikuti arsip penelitian, bukan pembaruan administratif terkini."
        )


def main() -> None:
    st.set_page_config(
        page_title="Seismofoodnet · Eksplorasi Indonesia", page_icon="🌏", layout="wide"
    )
    render_header()
    try:
        regions, indicators, water, earthquakes, rejected = cached_data()
    except (OSError, ValueError, KeyError) as exc:
        logging.getLogger(__name__).exception("Gagal memuat dataset")
        st.error(f"Data tidak dapat dimuat: {exc}")
        st.stop()
    if rejected:
        st.warning(f"{rejected} baris gempa dilewati karena koordinat tidak valid.")
    province, magnitude = render_filters(regions)
    regions, indicators, earthquakes = filter_dashboard(
        regions, indicators, earthquakes, province, MAGNITUDES[magnitude]
    )
    render_stats(regions, indicators, earthquakes)
    explorer, data, guide = st.tabs(["Eksplorasi", "Data terpilih", "Panduan"])
    with explorer:
        render_explorer(regions, indicators, water, earthquakes, province, magnitude)
    with data:
        render_tables(regions, indicators, earthquakes)
    with guide:
        render_guide()


if __name__ == "__main__":
    main()
