import streamlit as st
import requests
import time
import pandas as pd
import re
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== KEYWORDS & CONFIG =====================================
KEYWORDS = [
    "iklan", "surat kabar", "suratkabar", "koran", "media cetak", "majalah",
    "publikasi", "radio", "televisi", "tv", "media online", "siber", "talk show",
    "talkshow", "adlibs", "pariwara", "advertorial", "advertising", "ads", "adv",
    "advertiser", "kampanye", "campaign", "promosi", "diseminasi", "podcast",
    "media elektronik", "media lokal", "media nasional", "pemasaran", "advertisement",
    "media digital", "newspaper", "media tradisional", "media massa", "media",
    "media internasional", "press", "pers", "placement", "news paper", "penayangan",
    "pemuatan", "tabloid", "sponsorship", "sponsor", "media daring"
]
KEYWORD_PATTERN = r'\b(' + '|'.join(re.escape(k) for k in KEYWORDS) + r')\b'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# =========================== FUNGSI UTILITY ==================================
@st.cache_resource
def requests_retry_session(
    retries=5, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504), session=None
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(['GET', 'POST']),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

s = requests_retry_session()

def get_detail_paket(id_paket):
    url_detail = f"https://sirup.lkpp.go.id/sirup/home/detailPaketPenyediaPublic2017/{id_paket}"
    try:
        resp = s.get(url_detail, headers=HEADERS)
        resp.raise_for_status()
        html = resp.text
        start = html.find("Uraian Pekerjaan")
        if start == -1:
            return ""
        start = html.find("<td>", start) + 4
        end = html.find("</td>", start)
        return html[start:end].strip()
    except Exception:
        return ""

def process_satker(satker, idx, total, tahun, progress_placeholder, status_placeholder):
    id_satker, nama_satker = satker[0], satker[1]
    filtered_data = []

    try:
        url_paket = "https://sirup.lkpp.go.id/sirup/datatablectr/dataruppenyediasatker"
        params = {
            'tahun': tahun,
            'idSatker': id_satker,
            'sEcho': '1',
            'iColumns': '7',
            'iDisplayStart': '0',
            'iDisplayLength': '100000'
        }
        res = s.get(url_paket, params=params, headers=HEADERS)
        res.raise_for_status()
        paket_list = res.json().get("aaData", [])

        if not paket_list:
            status_placeholder.write(f"[{idx}/{total}] ❕ {nama_satker} (0 paket)")
            return nama_satker, []

        with ThreadPoolExecutor(max_workers=st.session_state.max_detail_workers) as executor:
            futures = {executor.submit(get_detail_paket, p[0]): p for p in paket_list}
            for future in as_completed(futures):
                p = futures[future]
                try:
                    uraian = future.result()
                except:
                    uraian = ""

                combined = f"{p[1]} {uraian}".lower()
                if re.search(KEYWORD_PATTERN, combined, re.IGNORECASE):
                    filtered_data.append({
                        'satuanKerja': nama_satker,
                        'namaPaket': p[1],
                        'uraianPekerjaan': uraian,
                        'metodePemilihan': p[3],
                        'pagu': p[2]
                    })
        
        progress = (idx) / total
        progress_placeholder.progress(progress)
        status_placeholder.write(f"[{idx}/{total}] ✔️ {nama_satker} ({len(filtered_data)} cocok)")

        return nama_satker, filtered_data
    
    except Exception as e:
        status_placeholder.write(f"[{idx}/{total}] ❌ ERROR di {nama_satker}: {e}")
        return nama_satker, []

# ========================== FUNGSI UTAMA STREAMLIT ===========================
def main():
    st.set_page_config(page_title="Scraper Belanja Iklan LKPP")
    st.title("Scraper Belanja Iklan LKPP")
    st.write("Aplikasi ini akan mencari paket pengadaan dengan kata kunci yang relevan dengan **belanja iklan, media, dan publikasi** di SIRUP LKPP.")

    st.sidebar.header("Konfigurasi Scraping")
    id_kldi = st.sidebar.text_input("ID KLDI", "D1005")
    tahun = st.sidebar.text_input("Tahun Anggaran", "2025")
    max_satker_workers = st.sidebar.slider("Jumlah Worker Satker", 1, 20, 10)
    max_detail_workers = st.sidebar.slider("Jumlah Worker Detail Paket", 1, 50, 20)

    # Simpan worker count ke session state agar bisa diakses oleh fungsi lain
    if 'max_satker_workers' not in st.session_state:
        st.session_state.max_satker_workers = max_satker_workers
        st.session_state.max_detail_workers = max_detail_workers

    st.write("---")

    if st.button("Mulai Scraping"):
        st.session_state.scraping_started = True
        st.session_state.all_data = []
        
        start_time = time.time()
        st.info("📦 Mulai scraping data...")

        # Persiapan UI untuk output
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        data_placeholder = st.empty()
        
        # --- Ambil daftar Satuan Kerja ---
        try:
            url_satker = "https://sirup.lkpp.go.id/sirup/datatablectr/datatableruprekapkldi"
            params = {'idKldi': id_kldi, 'tahun': tahun, 'sEcho': '1', 'iColumns': '10', 'iDisplayStart': '0', 'iDisplayLength': '100000'}
            res = s.get(url_satker, params=params, headers=HEADERS)
            res.raise_for_status()
            satkers = res.json().get("aaData", [])
            st.success(f"📋 Total satuan kerja ditemukan: {len(satkers)}")
        except Exception as e:
            st.error(f"❌ Gagal ambil data satuan kerja: {e}")
            st.stop()

        # --- Proses data dengan multithreading ---
        all_data = []
        with ThreadPoolExecutor(max_workers=st.session_state.max_satker_workers) as executor:
            futures = {
                executor.submit(
                    process_satker, s, i + 1, len(satkers), tahun, progress_bar, status_placeholder
                ): s for i, s in enumerate(satkers)
            }
            for future in as_completed(futures):
                try:
                    _, data = future.result()
                    all_data.extend(data)
                except Exception as e:
                    st.error(f"❌ ERROR saat memproses satker: {e}")
        
        progress_bar.progress(1.0)
        status_placeholder.success("✅ Scraping selesai!")
        st.write(f"🟢 Program selesai dalam **{time.time() - start_time:.2f}** detik.")
        
        # --- Tampilkan dan simpan data ---
        if all_data:
            df = pd.DataFrame(all_data, columns=['satuanKerja', 'namaPaket', 'uraianPekerjaan', 'metodePemilihan', 'pagu'])
            df.drop_duplicates(subset=['satuanKerja', 'namaPaket', 'uraianPekerjaan'], inplace=True)
            df.index += 1
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'No'}, inplace=True)
            
            data_placeholder.dataframe(df)

            # Sediakan tombol download
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Unduh data sebagai CSV",
                data=csv,
                file_name=f'belanja_iklan_{id_kldi}_{tahun}.csv',
                mime='text/csv',
            )

            # Buat file excel di folder sementara untuk diunduh
            excel_path = f'belanja_iklan_{id_kldi}_{tahun}.xlsx'
            try:
                df.to_excel(excel_path, index=False)
                with open(excel_path, "rb") as file:
                    st.download_button(
                        label="Unduh data sebagai XLSX",
                        data=file,
                        file_name=excel_path,
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
            except Exception as e:
                st.error(f"❌ Gagal membuat file Excel: {e}")

        else:
            data_placeholder.info("⚠️ Tidak ada data yang cocok ditemukan.")

if __name__ == "__main__":
    main()