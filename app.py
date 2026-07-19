import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# Konfigurasi Halaman Web
st.set_page_config(layout="wide", page_title="Sistem Absensi Multi-Kelas")

# Definisi Parameter Utama
classes = ['7A', '7B', '7C', '7D', '7E', '7F']
months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER', 'JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']
date_cols = [f"Tgl {i}" for i in range(1, 32)]

initial_students = [
    'ACHMAD FAIRUZ', 'ADARA DWI NOVITA', 'ADELAMULIA PUTRI FAJARINO', 
    'AHMAD DENIS RUBIANSYAH', 'AZZAM MAULANA', 'BERNADET SONDANG SIMORANGKIR*', 
    'BIONIC ALEXANDER WONG*', 'CAHAYA MAYCA ADI SAVIRA', 'CARLITA AMARA'
] # Contoh beberapa nama awal (Bisa ditambah/hapus bebas di web)

# --- 1. KONEKSI GOOGLE SHEETS ---
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
    st.stop()

# --- 2. FUNGSI DATABASE PASSWORD (CONFIG) ---
def get_config_passwords():
    try:
        ws = sh.worksheet("CONFIG")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return dict(zip(df['Key'], df['Password']))
    except gspread.exceptions.WorksheetNotFound:
        # Jika tab CONFIG belum ada di Google Sheets, otomatis buat dengan password default
        ws = sh.add_worksheet(title="CONFIG", rows="20", cols="5")
        default_data = {
            'Key': ['Admin'] + classes,
            'Password': ['admin123', '7a123', '7b123', '7c123', '7d123', '7e123', '7f123']
        }
        df = pd.DataFrame(default_data)
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
        return dict(zip(df['Key'], df['Password']))

def save_config_passwords(password_dict):
    ws = sh.worksheet("CONFIG")
    ws.clear()
    df = pd.DataFrame(list(password_dict.items()), columns=['Key', 'Password'])
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())

# --- 3. FUNGSI DATABASE ABSENSI ---
def get_attendance_data(kelas, month):
    sheet_name = f"{kelas}_{month}"
    try:
        ws = sh.worksheet(sheet_name)
        data = ws.get_all_records()
        if not data:
            raise gspread.exceptions.WorksheetNotFound
        df = pd.DataFrame(data)
        for col in date_cols:
            if col not in df.columns:
                df[col] = '' # Menggunakan KOSONG/BLANK sebagai default bawaan
        return df[['Nama Siswa'] + date_cols]
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows="100", cols="40")
        df = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        df['Nama Siswa'] = initial_students
        df[date_cols] = '' # Menggunakan KOSONG/BLANK sebagai default bawaan
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
        return df

def save_attendance_data(kelas, month, df):
    sheet_name = f"{kelas}_{month}"
    ws = sh.worksheet(sheet_name)
    ws.clear()
    df = df.fillna('')
    df = df.astype(str)
    data_to_write = [df.columns.values.tolist()] + df.values.tolist()
    ws.update(range_name='A1', values=data_to_write)

# --- 4. KONTROL MANAJEMEN LOGIN ---
passwords = get_config_passwords()

if 'auth_role' not in st.session_state:
    st.session_state.auth_role = None
if 'auth_class' not in st.session_state:
    st.session_state.auth_class = None

# Sidebar Menu Utama
st.sidebar.title("🔐 Akses Gerbang Utama")
role_selection = st.sidebar.radio("Pilih Hak Akses:", ["Guru Kelas", "Administrator System"])

# --- HALAMAN GURU KELAS ---
if role_selection == "Guru Kelas":
    st.title("📊 Aplikasi Absensi Digital Berbasis Cloud")
    
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        selected_class = st.selectbox("🏫 Pilih Kelas", classes)
    with col_sel2:
        selected_month = st.selectbox("📅 Pilih Bulan", months)
        
    input_password = st.text_input(f"🔑 Masukkan Password Akses Kelas {selected_class}:", type="password")
    
    # Cek Validasi Password Kelas
    if input_password == passwords.get(selected_class):
        st.success(f"🔓 Akses Terbuka untuk Kelas {selected_class} - Bulan {selected_month}")
        
        # Load Data
        sheet_key = f"{selected_class}_{selected_month}"
        if 'current_data' not in st.session_state or st.session_state.get('current_key') != sheet_key:
            st.session_state.current_data = get_attendance_data(selected_class, selected_month)
            st.session_state.current_key = sheet_key
            
        # Papan Ketik Absen
        st.write("---")
        st.subheader("📝 Papan Input Absensi")
        st.caption("Default adalah KOSONG (dihitung Hadir). Ketik S (Sakit), I (Izin), atau A (Alpha) untuk merubah.")
        
        edited_df = st.data_editor(
            st.session_state.current_data,
            num_rows="dynamic",
            use_container_width=True,
            key=f"editor_{sheet_key}"
        )
        st.session_state.current_data = edited_df
        
        # Tombol Simpan
        if st.button("💾 Simpan Permanen ke Cloud", type="primary"):
            with st.spinner("Menyimpan ke Google Sheets..."):
                save_attendance_data(selected_class, selected_month, edited_df)
            st.success("✅ Perubahan berhasil dikunci di Google Sheets!")

        # Fungsi Hitung Rekapitulasi Otomatis (Menganggap Blank/Kosong = Hadir)
        def generate_full_report(df):
            df_report = df.copy()
            df_report[date_cols] = df_report[date_cols].fillna('')
            s_list, i_list, a_list, h_list, pct_list = [], [], [], [], []
            
            for _, row in df_report.iterrows():
                if pd.isna(row['Nama Siswa']) or str(row['Nama Siswa']).strip() == "":
                    s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0); pct_list.append("0%")
                    continue
                
                # Normalisasi string input
                vals = [str(v).strip().upper() for v in row[date_cols].values]
                s = vals.count('S') + vals.count('SAKIT')
                i = vals.count('I') + vals.count('IJIN') + vals.count('IZIN')
                a = vals.count('A') + vals.count('ALPHA') + vals.count('ALPA')
                
                # Hadir dihitung jika sel KOSONG (''), bertanda titik ('.'), atau kata 'HADIR'
                h = vals.count('') + vals.count('.') + vals.count('HADIR')
                
                total = s + i + a + h
                pct = (h / total * 100) if total > 0 else 0.0
                
                s_list.append(s); i_list.append(i); a_list.append(a); h_list.append(h)
                pct_list.append(f"{pct:.0f}%")
                
            df_report['S'] = s_list; df_report['I'] = i_list; df_report['A'] = a_list; df_report['Hadir'] = h_list; df_report['%'] = pct_list
            return df_report

        # Tampilkan Live Rekap
        st.write("---")
        st.subheader("📋 Live Rekapitulasi Kehadiran Siswa")
        full_report = generate_full_report(edited_df)
        st.dataframe(full_report[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '%']], use_container_width=True)
        
        # Ekspor Excel Satu Kelas Penuh (12 Bulan)
        st.write("---")
        st.subheader("📥 Unduh Laporan Tahunan Kelas")
        if st.button(f"Generate Excel untuk Seluruh Bulan di Kelas {selected_class}"):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                for m in months:
                    data_m = get_attendance_data(selected_class, m)
                    monthly_report = generate_full_report(data_m)
                    monthly_report.to_excel(writer, sheet_name=m, index=False)
            st.download_button(
                label="Klik untuk Mendownload (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"ABSENSI_KELAS_{selected_class}_LENGKAP.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    elif input_password != "":
        st.error("❌ Password salah! Anda tidak memiliki izin untuk membuka lembar absensi kelas ini.")

# --- HALAMAN ADMINISTRATOR ---
elif role_selection == "Administrator System":
    st.title("🛠️ Panel Kontrol Admin — Pengaturan Keamanan")
    
    admin_password = st.text_input("🔑 Masukkan Password Admin:", type="password")
    
    if admin_password == passwords.get("Admin"):
        st.success("🔓 Selamat Datang Admin. Anda memiliki hak penuh mengubah konfigurasi password.")
        
        st.write("---")
        st.subheader("✏️ Kelola Password Kelas")
        st.caption("Ubah password langsung pada tabel di bawah ini, lalu klik tombol simpan.")
        
        # Membuat Dataframe untuk Data Editor Admin
        config_df = pd.DataFrame(list(passwords.items()), columns=['Nama Akun / Kelas', 'Password'])
        
        edited_config_df = st.data_editor(
            config_df,
            disabled=['Nama Akun / Kelas'], # Kunci nama agar tidak diubah sembarangan
            use_container_width=True,
            key="admin_password_editor"
        )
        
        if st.button("💾 Simpan Perubahan Password", type="primary"):
            new_passwords = dict(zip(edited_config_df['Nama Akun / Kelas'], edited_config_df['Password']))
            with st.spinner("Memperbarui enkripsi di cloud..."):
                save_config_passwords(new_passwords)
            st.success("🎉 Password berhasil diperbarui secara permanen ke cloud storage!")
            st.cache_resource.clear() # Clear cache agar data langsung segar kembali
            
    elif admin_password != "":
        st.error("❌ Password Admin salah!")
