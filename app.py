import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# Konfigurasi Halaman Web
st.set_page_config(layout="wide", page_title="Absensi Kelas 7A Cloud")

months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER', 'JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']
date_cols = [f"Tgl {i}" for i in range(1, 32)]

# Database Nama Siswa Awal (Untuk inisialisasi otomatis jika tab kosong)
initial_students = [
    'ACHMAD FAIRUZ', 'ADARA DWI NOVITA', 'ADELAMULIA PUTRI FAJARINO', 
    'AHMAD DENIS RUBIANSYAH', 'AZZAM MAULANA', 'BERNADET SONDANG SIMORANGKIR*', 
    'BIONIC ALEXANDER WONG*', 'CAHAYA MAYCA ADI SAVIRA', 'CARLITA AMARA', 
    'FARIEDZ TAUFIQURRAHMAN PUTRA', 'FINO DWI INDRASTA', 'GENDIS CETTA WIGNYA', 
    'HANSEN KENTARO HASIBUAN*', 'JIHAN JUNIAN SARI', 'JONATHAN MEI CARDO PASARIBU*', 
    'LAIQA NUR SASABILLA', 'MUHAMMAD ABHINAYA GHAISAN', 'MUHAMMAD CHOIRUL AKBAR', 
    'MUHAMMAD FATHIR ARSYAD', 'MUHAMMAD FEBRIANSAH SAPUTRA', 'MUTIARA NAFISAH KHAIRIDHA', 
    'NATHANAEL RICARD HUTAJULU*', 'NAZWA AULIA SAFITRI', 'RAMA FADILLAH ARLIANSYAH', 
    'RAVENA MAY ARYANTI HADI PRIATNO', 'RISKY ADI SAPUTRA', 'ROSTINA AR RIFA', 
    'SANDRA DWI AVRILIA', 'SHAFIYAH SALSABILA', 'SINTA MAHARANI', 
    'SYAIFUL ARIF', 'SYAKIRA RYANDINY', 'SYAQILLA VEDDARA RIESRIE', 
    'VIOLA LESSYAH', 'VICKY ADRYAN FASYA', 'ZEFANA NURIZKYA SAPUTRA'
]

# --- KONEKSI GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

try:
    client = get_gspread_client()
    sh = client.open_by_key(st.secrets["spreadsheet_id"])
except Exception as e:
    st.error(f"❌ Gagal terhubung ke Google Sheets: {e}")
    st.info("Pastikan file secrets.toml sudah diatur dengan benar di dashboard hosting Anda.")
    st.stop()

# --- FUNGSI READ & WRITE CLOUD ---
def get_month_data(month):
    try:
        ws = sh.worksheet(month)
        data = ws.get_all_records()
        if not data:
            raise gspread.exceptions.WorksheetNotFound
        df = pd.DataFrame(data)
        for col in date_cols:
            if col not in df.columns:
                df[col] = '.'
        return df[['Nama Siswa'] + date_cols]
    except gspread.exceptions.WorksheetNotFound:
        # Jika tab bulan tidak ditemukan, otomatis buat baru di Google Sheets Anda
        ws = sh.add_worksheet(title=month, rows="100", cols="40")
        df = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        df['Nama Siswa'] = initial_students
        df[date_cols] = '.'
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
        return df

def save_month_data(month, df):
    ws = sh.worksheet(month)
    ws.clear()
    df = df.fillna('.')
    df = df.astype(str)
    data_to_write = [df.columns.values.tolist()] + df.values.tolist()
    ws.update(range_name='A1', values=data_to_write)

# --- MANAJEMEN SESSION STATE (ANTI-RESET LOOP) ---
if 'data_cache' not in st.session_state:
    st.session_state.data_cache = {}

# --- TAMPILAN UTAMA ---
st.title("📊 Aplikasi Absensi Cloud Kelas 7A (Anti-Reset)")
selected_month = st.sidebar.selectbox("📅 Pilih Bulan Absensi", months)

# Tombol Sinkronisasi Ulang manual dari Cloud jika dibutuhkan
if st.sidebar.button("🔄 Segarkan Data dari Cloud"):
    st.session_state.data_cache.pop(selected_month, None)
    st.rerun()

# Memuat data ke memori lokal aplikasi web
if selected_month not in st.session_state.data_cache:
    st.session_state.data_cache[selected_month] = get_month_data(selected_month)

current_df = st.session_state.data_cache[selected_month]

st.write("---")
st.subheader(f"📝 Papan Input Absensi — Bulan {selected_month}")
st.caption("Ubah kehadiran secara manual ( . = Hadir, S = Sakit, I = Izin, A = Alpha ).")

# Tabel editor interaktif
edited_df = st.data_editor(
    current_df,
    num_rows="dynamic",
    use_container_width=True,
    key=f"editor_{selected_month}"
)

# Simpan perubahan ke memori lokal web secara instan sewaktu diketik
st.session_state.data_cache[selected_month] = edited_df

# TOMBOL UTAMA UNTUK SIMPAN PERMANEN
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("💾 Simpan ke Google Sheets", type="primary"):
        with st.spinner("Menyimpan perubahan ke cloud..."):
            save_month_data(selected_month, edited_df)
        st.success("✅ Data berhasil disimpan permanen di Google Sheets Anda!")

# --- RINGKASAN REKAP LANGSUNG ---
def generate_full_report(df):
    df_report = df.copy()
    df_report[date_cols] = df_report[date_cols].fillna('.')
    s_list, i_list, a_list, h_list, pct_list = [], [], [], [], []
    
    for _, row in df_report.iterrows():
        if pd.isna(row['Nama Siswa']) or str(row['Nama Siswa']).strip() == "":
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0); pct_list.append("0%")
            continue
        vals = [str(v).strip().upper() for v in row[date_cols].values]
        s = vals.count('S') + vals.count('SAKIT')
        i = vals.count('I') + vals.count('IJIN') + vals.count('IZIN')
        a = vals.count('A') + vals.count('ALPHA') + vals.count('ALPA')
        h = vals.count('.') + vals.count('HADIR')
        
        total = s + i + a + h
        pct = (h / total * 100) if total > 0 else 0.0
        
        s_list.append(s); i_list.append(i); a_list.append(a); h_list.append(h)
        pct_list.append(f"{pct:.0f}%")
        
    df_report['S'] = s_list; df_report['I'] = i_list; df_report['A'] = a_list; df_report['Hadir'] = h_list; df_report['%'] = pct_list
    return df_report

st.write("---")
st.subheader("📋 Live Rekapitulasi Kehadiran Siswa")
full_calculated_df = generate_full_report(edited_df)
st.dataframe(full_calculated_df[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '%']], use_container_width=True)

# --- DOWNLOAD EXCEL ---
st.write("---")
st.subheader("📥 Unduh Laporan Excel")
if st.button("Generate File Excel Terupdate"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        for m in months:
            # Mengambil data paling mutakhir tiap bulan untuk dibundel ke Excel
            data_m = st.session_state.data_cache[m] if m in st.session_state.data_cache else get_month_data(m)
            monthly_report = generate_full_report(data_m)
            monthly_report.to_excel(writer, sheet_name=m, index=False)
            
    st.download_button(
        label="Klik di Sini untuk Mengunduh (.xlsx)",
        data=buffer.getvalue(),
        file_name="ABSENSI_7A_CLOUD_FINAL.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
