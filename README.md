# UNDATATHON-Seismofoodnet

Dashboard Streamlit untuk eksplorasi gempa, badan air, dan korelasi indikator
kabupaten/kota Indonesia. Data berasal dari berkas historis di `data/`; aplikasi
tidak mengambil data gempa real-time.

## Menjalankan

Gunakan Python 3.10 atau yang lebih baru. Streamlit Community Cloud memakai
Python 3.10 melalui `runtime.txt`. Dari folder proyek:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run App.py
```

Buka `http://localhost:8501`. Lokasi dataset mengikuti lokasi modul, sehingga
aplikasi juga dapat dijalankan menggunakan path absolut dari folder lain.
Tema berada di `.streamlit/config.toml`. Dev Container memasang dependensi dan
menjalankan Streamlit dengan proteksi CORS/XSRF bawaan tetap aktif.

## Peta dasar

Peta memakai OpenStreetMap tanpa API key. Integrasi CARTO lama dihapus karena
[CARTO kini mewajibkan API key](https://carto.com/basemaps/apikey/).
Tile dimuat langsung oleh browser melalui HTTPS, dengan atribusi terlihat.
Internet tetap diperlukan untuk tile dan aset JavaScript peta.

Untuk penyedia tile lain, atur kedua environment variable berikut sebelum menjalankan:

```sh
export SEISMO_TILE_URL='https://your-provider.example/{z}/{x}/{y}.png'
export SEISMO_TILE_ATTRIBUTION='Attribution required by your provider'
```

URL tile diteruskan ke browser; token di URL bukan rahasia server. Gunakan token
publik dengan pembatasan domain jika penyedia memerlukannya.
Server tile OSM bersifat best-effort; ikuti
[kebijakan penggunaan tile](https://operations.osmfoundation.org/policies/tiles/)
dan gunakan penyedia yang sesuai untuk trafik besar. Aplikasi tidak mengunduh
tile massal atau menyediakan fitur offline.

## Antarmuka dan penggunaan

Dashboard memakai tema terang dengan aksen teal. HTML untuk header, kartu
ringkasan, dan legenda dipisahkan dari kontrol interaktif Streamlit; CSS berada
di `assets/dashboard.css` dengan layout responsif dan indikator fokus keyboard.

- **Cakupan wilayah** menyelaraskan peta, ringkasan, grafik, tabel, dan CSV.
  Gempa dalam provinsi dipilih berdasarkan lokasi di dalam batas geografis;
  pilih **Seluruh Indonesia** untuk menyertakan kejadian lepas pantai.
- **Magnitudo gempa** hanya menyaring kejadian gempa, tidak mengubah IRBI atau
  korelasi. Magnitudo kosong disertakan pada Semua magnitudo, tetapi tidak pada
  filter ambang. **Reset filter** mengembalikan cakupan nasional tanpa ambang.
- Tab **Eksplorasi** menampilkan peta dan kuadran. Garis ke pusat badan air
  dinonaktifkan secara default; aktifkan melalui **Pengaturan layer**.
- Tab **Data terpilih** menyediakan tabel dan unduhan CSV sesuai filter aktif.
- Tab **Panduan** menjelaskan interaksi, sumber, dan batasan interpretasi.
- Kondisi tanpa hasil ditampilkan sebagai pesan dengan langkah pemulihan.
  Korelasi kosong tetap dibedakan dari nol pada kartu dan legenda.

Warna korelasi menunjukkan koefisien, bukan klasifikasi risiko. Nilai IRBI pada
kartu merupakan median antardaerah dari median tahunan masing-masing daerah.

## Perbaikan utama

- `st_folium` menggantikan `folium_static`; peta dan grafik mengikuti lebar kolom.
- Marker gempa memakai titik vektor tanpa gambar ikon eksternal. Tampilan awal
  mencakup batas Indonesia dan kedua tampilan menyediakan kontrol layer.
- Kunci wilayah adalah gabungan kode provinsi dan kabupaten/kota (kode BPS),
  sehingga kode kabupaten yang berulang antarprovinsi tidak menimpa korelasi.
- Korelasi kosong tetap kosong dan berwarna abu-abu; legenda menunjukkan
  koefisien korelasi, bukan persentase populasi.
- Median IRBI/Y memakai semua kolom tahunan, termasuk 2022. Grafik mempunyai
  garis kuadran median dan nama wilayah pada hover. Arti Y tidak ditebak karena
  kamus variabel belum tersedia dalam repository.
- Pembacaan data dicache selama satu jam; overlay spasial yang tidak digunakan
  dihapus. Pencarian pusat badan air terdekat memakai perhitungan spherical
  berbasis NumPy. Pusat geometri dihitung dalam CRS proyeksi EPSG:6933.
- Koordinat gempa tidak valid dilewati dengan pemberitahuan; data hilang tidak
  diisi nol. Path data tidak lagi bergantung pada working directory.
- Geometri diperbaiki sebagai Polygon/MultiPolygon agar perhitungan batas dan
  tooltip Folium tidak crash akibat GeometryCollection.
- Dependensi diperbarui, duplikasi `streamlit-folium` dihapus, dan dependensi
  langsung Streamlit/Pandas/NumPy dinyatakan eksplisit.

Layer sumber `IDN_water_areas_dcw.shp` adalah **area badan air**. Garis dari gempa
ke pusat area terdekat mempertahankan visualisasi aplikasi sebelumnya; ini
bukan jarak ke tepi sungai atau model dampak gempa. Nilai korelasi berasal dari
spreadsheet dan tidak dihitung ulang oleh aplikasi.

## Validasi

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Pengujian mencakup benturan kode wilayah, nilai kosong, koordinat tidak valid,
median seluruh tahun, pencarian pusat terdekat, rendering kedua jenis peta,
dan perpindahan tampilan melalui Streamlit AppTest. AppTest tidak menjalankan
JavaScript browser atau menjamin ketersediaan layanan tile eksternal.
