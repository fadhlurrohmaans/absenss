import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# Konfigurasi Halaman Web agar Responsif
st.set_page_config(layout="wide", page_title="Sistem Absensi Sekolah Digital")

# Mengatur CSS Khusus agar Tampilan Tabel Lebih Nyaman Digeser di Layar HP
st.markdown("""
    <style>
    div[data-testid="stDataFrame"] > div {
        overflow-x: auto;
    }
    .stButton>button {
        width: 100%;
        margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# Parameter Utama Aplikasi
classes = [f"{grade}{letter}" for grade in [7, 8, 9] for letter in ['A', 'B', 'C', 'D', 'E', 'F']]
months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER', 'JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']
date_cols = [f"Tgl {i}" for i in range(1, 32)]

# Contoh daftar nama awal untuk pengisian otomatis lembar baru
initial_students = ['ACHMAD FAIRUZ', 'ADARA DWI NOVITA', 'ADELAMULIA PUTRI FAJARINO', 'AHMAD DENIS RUBIANSYAH']

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

# --- 2. MANAGEMENT PASSWORD DATABASE (CONFIG) ---
def get_config_passwords():
    try:
        ws = sh.worksheet("CONFIG")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return dict(zip(df['Key'], df['Password']))
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="CONFIG", rows="30", cols="5")
        keys = ['Admin', 'Guru Piket'] + classes
        default_passwords = ['admin123', 'piket123'] + [f"{c.lower()}123" for c in classes]
        df = pd.DataFrame({'Key': keys, 'Password': default_passwords})
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
        return dict(zip(df['Key'], df['Password']))

def save_config_passwords(password_dict):
    ws = sh.worksheet("CONFIG")
    ws.clear()
    df = pd.DataFrame(list(password_dict.items()), columns=['Key', 'Password'])
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())

# --- 3. MANAGEMENT DATA ABSENSI ---
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
                df[col] = ''
        return df[['Nama Siswa'] + date_cols]
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows="100", cols="40")
        df = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        df['Nama Siswa'] = initial_students
        df[date_cols] = ''
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

def generate_full_report(df):
    df_report = df.copy()
    df_report[date_cols] = df_report[date_cols].fillna('')
    s_list, i_list, a_list, h_list, pct_list = [], [], [], [], []
    
    for _, row in df_report.iterrows():
        if pd.isna(row['Nama Siswa']) or str(row['Nama Siswa']).strip() == "":
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0); pct_list.append("0%")
            continue
        vals = [str(v).strip().upper() for v in row[date_cols].values]
        s = vals.count('S') + vals.count('SAKIT')
        i = vals.count('I') + vals.count('IJIN') + vals.count('IZIN')
        a = vals.count('A') + vals.count('ALPHA') + vals.count('ALPA')
        h = vals.count('') + vals.count('.') + vals.count('HADIR')
        
        total = s + i + a + h
        pct = (h / total * 100) if total > 0 else 0.0
        s_list.append(s); i_list.append(i); a_list.append(a); h_list.append(h); pct_list.append(f"{pct:.0f}%")
        
    df_report['S'] = s_list; df_report['I'] = i_list; df_report['A'] = a_list; df_report['Hadir'] = h_list; df_report['%'] = pct_list
    return df_report

# --- 4. SISTEM OTENTIKASI & LOGIN (PERSISTENT STATE) ---
passwords = get_config_passwords()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'assigned_class' not in st.session_state:
    st.session_state.assigned_class = None

# Tampilan Kontrol di Sidebar
st.sidebar.title("🏢 Menu Utama Sekolah")

if st.session_state.logged_in:
    st.sidebar.success(f"Masuk sebagai:\n{st.session_state.user_role} " + (f"({st.session_state.assigned_class})" if st.session_state.assigned_class else ""))
    if st.sidebar.button("🚪 Keluar / Logout"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.assigned_class = None
        st.rerun()

# --- LOGIKA TAMPILAN JIKA BELUM LOGIN ---
if not st.session_state.logged_in:
    st.title("🔐 Sistem Keamanan Absensi Digital")
    st.write("Silakan pilih peran dan masukkan password untuk mengakses dashboard.")
    
    # Gunakan Form agar Keyboard HP tidak memicu refresh aplikasi secara konstan
    with st.form(key="login_form_mobile"):
        role = st.selectbox("Pilih Hak Akses Peran:", ["Guru Kelas", "Guru Piket", "Administrator System"])
        
        # Pilihan dinamis kelas muncul hanya jika memilih Guru Kelas
        target_class = None
        if role == "Guru Kelas":
            target_class = st.selectbox("Pilih Kelas Anda:", classes)
            
        password_input = st.text_input("Masukkan Password Akun:", type="password")
        submit_button = st.form_submit_button(label="🔑 Masuk / Buka Akses")
        
        if submit_button:
            if role == "Guru Kelas":
                if password_input == passwords.get(target_class):
                    st.session_state.logged_in = True
                    st.session_state.user_role = "Guru Kelas"
                    st.session_state.assigned_class = target_class
                    st.rerun()
                else:
                    st.error("❌ Password Akses Kelas Salah!")
            elif role == "Guru Piket":
                if password_input == passwords.get("Guru Piket"):
                    st.session_state.logged_in = True
                    st.session_state.user_role = "Guru Piket"
                    st.rerun()
                else:
                    st.error("❌ Password Akun Guru Piket Salah!")
            elif role == "Administrator System":
                if password_input == passwords.get("Admin"):
                    st.session_state.logged_in = True
                    st.session_state.user_role = "Admin"
                    st.rerun()
                else:
                    st.error("❌ Password Administrator Salah!")

# --- LOGIKA DATA TAMPILAN JIKA SUDAH BERHASIL LOGIN ---
else:
    # A. DASHBOARD HALAMAN GURU KELAS (CRUD AKTIF)
    if st.session_state.user_role == "Guru Kelas":
        my_class = st.session_state.assigned_class
        st.title(f"🏫 Ruang Kerja Kelas {my_class}")
        
        selected_month = st.selectbox("📅 Pilih Bulan Absensi:", months)
        
        # Memuat Data
        current_data = get_attendance_data(my_class, selected_month)
        
        st.write("---")
        st.subheader("📝 Papan Lembar Absensi")
        st.info("📱 Tip Pengguna HP: Geser tabel ke samping kanan/kiri untuk melihat kolom tanggal lengkap.")
        
        # Data Editor interaktif untuk Guru Kelas
        edited_df = st.data_editor(
            current_data,
            num_rows="dynamic",
            use_container_width=True,
            key=f"crud_{my_class}_{selected_month}"
        )
        
        if st.button("💾 Simpan Permanen ke Cloud", type="primary"):
            with st.spinner("Mengunggah data ke Google Drive..."):
                save_attendance_data(my_class, selected_month, edited_df)
            st.success("🎉 Data Anda sukses disimpan di Google Sheets Cloud!")
            
        # Live Rekap
        st.write("---")
        st.subheader("📋 Ringkasan Kehadiran Otomatis")
        full_report = generate_full_report(edited_df)
        st.dataframe(full_report[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '%']], use_container_width=True)

    # B. DASHBOARD HALAMAN GURU PIKET (READ-ONLY KUNCI DATA)
    elif st.session_state.user_role == "Guru Piket":
        st.title("🕵️‍♂️ Dashboard Peninjauan Guru Piket")
        st.write("Anda memiliki hak akses baca untuk memantau seluruh kelas hari ini.")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            piket_class = st.selectbox("🏫 Pantau Kelas:", classes)
        with col_p2:
            piket_month = st.selectbox("📅 Pilih Bulan:", months)
            
        # Memuat Data
        raw_data = get_attendance_data(piket_class, piket_month)
        calculated_data = generate_full_report(raw_data)
        
        st.write("---")
        st.subheader(f"📊 Laporan Real-Time Kehadiran Kelas {piket_class} ({piket_month})")
        st.warning("⚠️ Mode Guru Piket: Pembatasan aktif. Data dikunci dari segala jenis perubahan manual.")
        
        # Menggunakan st.dataframe biasa (Bukan Data Editor) agar 100% Read-Only & sangat ringan digeser di HP
        st.dataframe(calculated_data, use_container_width=True)

    # C. DASHBOARD HALAMAN ADMIN
    elif st.session_state.user_role == "Admin":
        st.title("🛠️ Pusat Manajemen Administrator")
        st.write("Kelola sandi rahasia untuk semua akun guru dan piket sekolah.")
        
        config_df = pd.DataFrame(list(passwords.items()), columns=['Nama Akun / Kelas', 'Password'])
        
        edited_config = st.data_editor(
            config_df,
            disabled=['Nama Akun / Kelas'],
            use_container_width=True,
            key="admin_editor"
        )
        
        if st.button("💾 Amankan & Simpan Password Baru", type="primary"):
            new_passwords = dict(zip(edited_config['Nama Akun / Kelas'], edited_config['Password']))
            save_config_passwords(new_passwords)
            st.success("🔒 Seluruh password baru berhasil diterapkan di sistem cloud!")
            st.cache_resource.clear()
