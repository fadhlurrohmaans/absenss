import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
import datetime
import calendar

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

month_map = {
    'JANUARI': 1, 'FEBRUARI': 2, 'MARET': 3, 'APRIL': 4, 'MEI': 5, 'JUNI': 6,
    'JULI': 7, 'AGUSTUS': 8, 'SEPTEMBER': 9, 'OKTOBER': 10, 'NOVEMBER': 11, 'DESEMBER': 12
}

def get_year_for_month(month_name):
    return 2026 if month_map[month_name] >= 7 else 2027

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

# --- 2. MANAGEMENT DATABASE MASTER NAMA (MASTER_SISWA) ---
def get_all_master_df():
    try:
        ws = sh.worksheet("MASTER_SISWA")
        data = ws.get_all_values()
        if not data:
            raise gspread.exceptions.WorksheetNotFound
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        for c in classes:
            if c not in df.columns:
                df[c] = ""
        return df
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="MASTER_SISWA", rows="150", cols="30")
        df = pd.DataFrame(columns=classes)
        for c in classes:
            df[c] = initial_students + [""] * (150 - len(initial_students))
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
        return df

def get_master_students(kelas):
    df = get_all_master_df()
    if kelas in df.columns:
        names = df[kelas].astype(str).str.strip().tolist()
        names = [n for n in names if n != "" and n != "None" and n != "nan"]
        return names
    return []

def save_master_students(kelas, name_list):
    df = get_all_master_df()
    name_list = [str(n).strip() for n in name_list if str(n).strip() != ""]
    
    # Reset kolom kelas ini dengan data baru, sisanya di-pad dengan string kosong
    df[kelas] = pd.Series(name_list)
    df = df.fillna("")
    
    ws = sh.worksheet("MASTER_SISWA")
    ws.clear()
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())

# --- 3. MANAGEMENT PASSWORD DATABASE (CONFIG) ---
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

# --- 4. MANAGEMENT DATA ABSENSI MENGGUNAKAN INDEKS REFERENSI ---
def get_attendance_data(kelas, month):
    sheet_name = f"{kelas}_{month}"
    year = get_year_for_month(month)
    month_num = month_map[month]
    _, max_days = calendar.monthrange(year, month_num)
    
    # PANGGIL REFERENSI INDUK
    master_names = get_master_students(kelas)
    if not master_names:
        master_names = ["(Siswa Belum Diisi di Tab Kelola)"]
        
    try:
        ws = sh.worksheet(sheet_name)
        data = ws.get_all_records()
        df_stored = pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        df_stored = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        
    # Bangun ulang struktur DataFrame secara runtime berbasis POSISI INDEKS Master Nama
    df_new = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
    df_new['Nama Siswa'] = master_names
    
    for i in range(1, 32):
        col = f"Tgl {i}"
        if i > max_days:
            df_new[col] = '-'
        else:
            dt = datetime.date(year, month_num, i)
            is_weekend = dt.weekday() in [5, 6]
            
            col_values = []
            for idx in range(len(master_names)):
                # Jika baris data tersimpan di posisi indeks ini ada, ambil isinya
                if idx < len(df_stored) and col in df_stored.columns:
                    val = str(df_stored.loc[idx, col]).strip()
                    if val in ['', 'None', 'nan', 'L', '-']:
                        col_values.append('L' if is_weekend else '')
                    else:
                        col_values.append(val)
                else:
                    # Jika baris baru hasil penambahan di lembar master
                    col_values.append('L' if is_weekend else '')
            df_new[col] = col_values
            
    return df_new

def save_attendance_data(kelas, month, df):
    sheet_name = f"{kelas}_{month}"
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows="100", cols="40")
        
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
        if pd.isna(row['Nama Siswa']) or str(row['Nama Siswa']).strip() in ["", "(Siswa Belum Diisi di Tab Kelola)"]:
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

# --- 5. SISTEM OTENTIKASI & LOGIN ---
passwords = get_config_passwords()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'assigned_class' not in st.session_state:
    st.session_state.assigned_class = None

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
    
    with st.form(key="login_form_mobile"):
        role = st.selectbox("Pilih Hak Akses Peran:", ["Guru Kelas", "Guru Piket", "Administrator System"])
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
    def get_calendar_config(selected_month):
        year = get_year_for_month(selected_month)
        month_num = month_map[selected_month]
        _, max_days = calendar.monthrange(year, month_num)
        days_id = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Mig"]
        
        disabled_cols = []
        col_config = {}
        
        for i in range(1, 32):
            col_name = f"Tgl {i}"
            if i > max_days:
                disabled_cols.append(col_name)
                col_config[col_name] = st.column_config.TextColumn(label=f"{i} (-)")
            else:
                dt = datetime.date(year, month_num, i)
                day_name = days_id[dt.weekday()]
                if dt.weekday() in [5, 6]:
                    disabled_cols.append(col_name)
                col_config[col_name] = st.column_config.TextColumn(label=f"{i} ({day_name})")
        return col_config, disabled_cols

    # A. DASHBOARD HALAMAN GURU KELAS
    if st.session_state.user_role == "Guru Kelas":
        my_class = st.session_state.assigned_class
        st.title(f"🏫 Ruang Kerja Kelas {my_class}")
        
        # MEMBUAT DUA SUB-TAB KERJA (ABSENSI vs KELOLA NAMA)
        tab_absen, tab_nama = st.tabs(["📝 Isi Absensi Bulanan", "👥 Kelola Daftar Master Siswa"])
        
        with tab_absen:
            selected_month = st.selectbox("📅 Pilih Bulan Absensi:", months)
            col_config, disabled_cols = get_calendar_config(selected_month)
            
            # Load Data Absen (Otomatis mengadopsi susunan Master Nama terbaru)
            current_data = get_attendance_data(my_class, selected_month)
            
            st.subheader("📝 Papan Lembar Absensi")
            st.caption("Catatan: Kolom Nama Siswa & Hari Libur dikunci otomatis demi keselarasan data.")
            
            # Kolom Nama Siswa di-KUNCI (disabled) agar tidak bisa dirubah di tab absen!
            edited_df = st.data_editor(
                current_data,
                num_rows="fixed", # Jumlah baris dikunci mengikuti jumlah master nama
                use_container_width=True,
                column_config=col_config,
                disabled=["Nama Siswa"] + disabled_cols,
                key=f"crud_{my_class}_{selected_month}"
            )
            
            if st.button("💾 Simpan Absensi Bulan Ini", type="primary"):
                with st.spinner("Mengunci absensi ke cloud..."):
                    save_attendance_data(my_class, selected_month, edited_df)
                st.success(f"🎉 Absensi Kelas {my_class} untuk bulan {selected_month} berhasil diamankan!")
                
            # Live Rekap
            st.write("---")
            st.subheader("📋 Ringkasan Kehadiran Otomatis")
            full_report = generate_full_report(edited_df)
            st.dataframe(full_report[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '%']], use_container_width=True)

        with tab_nama:
            st.subheader(f"👥 Pusat Pengaturan Siswa Kelas {my_class}")
            st.info("Menambah, menghapus, atau mengganti ejaan nama di sini akan otomatis merubah seluruh lembar 12 bulan absensi kelas Anda.")
            
            # Ambil list nama dari database induk
            current_masters = get_master_students(my_class)
            df_masters = pd.DataFrame(current_masters, columns=["Nama Siswa"])
            
            edited_masters = st.data_editor(
                df_masters,
                num_rows="dynamic", # Di sini guru bisa menambah/menghapus baris siswa bebas
                use_container_width=True,
                key=f"master_edit_workspace_{my_class}"
            )
            
            if st.button("💾 Terapkan & Sinkronisasikan Nama Baru", type="primary"):
                with st.spinner("Sinkronisasi database induk..."):
                    new_names_list = edited_masters["Nama Siswa"].dropna().tolist()
                    save_master_students(my_class, new_names_list)
                st.success("🎉 Berhasil! Nama siswa diselaraskan mutlak di seluruh kalender bulan.")
                st.cache_resource.clear()

    # B. DASHBOARD HALAMAN GURU PIKET (READ-ONLY)
    elif st.session_state.user_role == "Guru Piket":
        st.title("🕵️‍♂️ Dashboard Peninjauan Guru Piket")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            piket_class = st.selectbox("🏫 Pantau Kelas:", classes)
        with col_p2:
            piket_month = st.selectbox("📅 Pilih Bulan:", months)
            
        col_config, _ = get_calendar_config(piket_month)
        
        raw_data = get_attendance_data(piket_class, piket_month)
        calculated_data = generate_full_report(raw_data)
        
        st.write("---")
        st.subheader(f"📊 Laporan Real-Time Kehadiran Kelas {piket_class} ({piket_month})")
        st.dataframe(calculated_data, use_container_width=True, column_config=col_config)

    # C. DASHBOARD HALAMAN ADMIN
    elif st.session_state.user_role == "Admin":
        st.title("🛠️ Pusat Manajemen Administrator")
        
        tab_pass, tab_master_all = st.tabs(["🔐 Kelola Password", "👥 Kelola Master Seluruh Sekolah"])
        
        with tab_pass:
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
                
        with tab_master_all:
            st.subheader("📊 Database Induk Nama Siswa Seluruh Kelas")
            df_all_masters = get_all_master_df()
            
            edited_all_masters = st.data_editor(
                df_all_masters,
                num_rows="dynamic",
                use_container_width=True,
                key="admin_master_all_editor"
            )
            if st.button("💾 Simpan Database Pusat Sekolah", type="primary"):
                with st.spinner("Menyimpan..."):
                    df_cleaned = edited_all_masters.fillna("")
                    ws = sh.worksheet("MASTER_SISWA")
                    ws.clear()
                    ws.update(range_name='A1', values=[df_cleaned.columns.values.tolist()] + df_cleaned.values.tolist())
                st.success("🔒 Database pusat 18 kelas sekolah berhasil dikunci!")
                st.cache_resource.clear()
