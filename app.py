import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
import datetime
import calendar
import io

# Coba muat library holidays untuk kalender Indonesia
try:
    import holidays
    id_holidays = holidays.ID(years=[2026, 2027])
except ImportError:
    id_holidays = {}

# Daftar Libur Nasional Indonesia (Fallback jika library 'holidays' belum terinstal)
manual_holidays = {
    # 2026
    datetime.date(2026, 1, 1): "Tahun Baru Masehi",
    datetime.date(2026, 1, 16): "Isra Mikraj",
    datetime.date(2026, 2, 17): "Tahun Baru Imlek",
    datetime.date(2026, 3, 19): "Hari Suci Nyepi",
    datetime.date(2026, 3, 20): "Hari Raya Idul Fitri",
    datetime.date(2026, 3, 21): "Hari Raya Idul Fitri",
    datetime.date(2026, 4, 3): "Wafat Yesus Kristus",
    datetime.date(2026, 4, 5): "Hari Paskah",
    datetime.date(2026, 5, 1): "Hari Buruh Internasional",
    datetime.date(2026, 5, 14): "Kenaikan Yesus Kristus",
    datetime.date(2026, 5, 27): "Hari Raya Idul Adha",
    datetime.date(2026, 5, 31): "Hari Raya Waisak",
    datetime.date(2026, 6, 1): "Hari Lahir Pancasila",
    datetime.date(2026, 6, 16): "Tahun Baru Islam",
    datetime.date(2026, 8, 17): "Proklamasi Kemerdekaan RI",
    datetime.date(2026, 8, 25): "Maulid Nabi Muhammad SAW",
    datetime.date(2026, 12, 25): "Hari Raya Natal",
    # 2027
    datetime.date(2027, 1, 1): "Tahun Baru Masehi",
    datetime.date(2027, 2, 6): "Tahun Baru Imlek",
    datetime.date(2027, 3, 9): "Hari Raya Idul Fitri",
    datetime.date(2027, 3, 10): "Hari Raya Idul Fitri",
    datetime.date(2027, 3, 26): "Wafat Yesus Kristus",
    datetime.date(2027, 5, 1): "Hari Buruh Internasional",
    datetime.date(2027, 5, 6): "Kenaikan Yesus Kristus",
    datetime.date(2027, 5, 17): "Hari Raya Idul Adha",
    datetime.date(2027, 5, 20): "Hari Raya Waisak",
    datetime.date(2027, 6, 1): "Hari Lahir Pancasila",
    datetime.date(2027, 6, 6): "Tahun Baru Islam",
    datetime.date(2027, 8, 15): "Maulid Nabi Muhammad SAW",
    datetime.date(2027, 8, 17): "Proklamasi Kemerdekaan RI",
    datetime.date(2027, 12, 25): "Hari Raya Natal",
}

# Fungsi Pembantu Cek Hari Libur / Weekend
def is_day_off(dt):
    # Cek Weekend (Sabtu=5, Minggu=6)
    if dt.weekday() in [5, 6]:
        return True, "Weekend"
    # Cek Libur Nasional (Library / Manual)
    if dt in id_holidays:
        return True, str(id_holidays.get(dt))
    if dt in manual_holidays:
        return True, manual_holidays[dt]
    return False, ""

# Konfigurasi Halaman Web
st.set_page_config(layout="wide", page_title="Sistem Absensi Sekolah Digital")

# Mengatur CSS Khusus
st.markdown("""
    <style>
    div[data-testid="stDataFrame"] {
        -webkit-overflow-scrolling: touch;
    }
    .stButton>button {
        width: 100%;
        margin-top: 8px;
        margin-bottom: 8px;
        border-radius: 8px;
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
@st.cache_resource(show_spinner=False)
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

# --- 2. MANAGEMENT DATABASE MASTER NAMA ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_master_df():
    try:
        ws = sh.worksheet("MASTER_SISWA")
        data = ws.get_all_values()
        if not data:
            raise WorksheetNotFound
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        for c in classes:
            if c not in df.columns:
                df[c] = ""
        return df
    except (WorksheetNotFound, APIError):
        try:
            ws = sh.add_worksheet(title="MASTER_SISWA", rows="150", cols="30")
            df = pd.DataFrame(columns=classes)
            for c in classes:
                df[c] = initial_students + [""] * (150 - len(initial_students))
            ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
            return df
        except Exception:
            df = pd.DataFrame(columns=classes)
            for c in classes:
                df[c] = initial_students + [""] * (150 - len(initial_students))
            return df

def get_master_students(kelas):
    df = fetch_all_master_df()
    if kelas in df.columns:
        names = df[kelas].astype(str).str.strip().tolist()
        return [n for n in names if n not in ["", "None", "nan"]]
    return []

def save_master_students(kelas, name_list):
    df = fetch_all_master_df()
    name_list = [str(n).strip() for n in name_list if str(n).strip() != ""]
    df[kelas] = pd.Series(name_list)
    df = df.fillna("")
    
    ws = sh.worksheet("MASTER_SISWA")
    ws.clear()
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
    fetch_all_master_df.clear()

# --- 3. MANAGEMENT PASSWORD DATABASE ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_config_passwords():
    try:
        ws = sh.worksheet("CONFIG")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return dict(zip(df['Key'], df['Password']))
    except (WorksheetNotFound, APIError):
        try:
            ws = sh.add_worksheet(title="CONFIG", rows="30", cols="5")
            keys = ['Admin', 'Guru Piket'] + classes
            default_passwords = ['admin123', 'piket123'] + [f"{c.lower()}123" for c in classes]
            df = pd.DataFrame({'Key': keys, 'Password': default_passwords})
            ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
            return dict(zip(df['Key'], df['Password']))
        except Exception:
            keys = ['Admin', 'Guru Piket'] + classes
            default_passwords = ['admin123', 'piket123'] + [f"{c.lower()}123" for c in classes]
            return dict(zip(keys, default_passwords))

def save_config_passwords(password_dict):
    ws = sh.worksheet("CONFIG")
    ws.clear()
    df = pd.DataFrame(list(password_dict.items()), columns=['Key', 'Password'])
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
    fetch_config_passwords.clear()

# --- 4. MANAGEMENT DATA ABSENSI BULANAN ---
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_attendance_data_from_gsheets(kelas, month):
    sheet_name = f"{kelas}_{month}"
    year = get_year_for_month(month)
    month_num = month_map[month]
    _, max_days = calendar.monthrange(year, month_num)
    
    master_names = get_master_students(kelas)
    if not master_names:
        master_names = ["(Siswa Belum Diisi di Tab Kelola)"]
        
    try:
        ws = sh.worksheet(sheet_name)
        data = ws.get_all_records()
        df_stored = pd.DataFrame(data)
    except Exception:
        df_stored = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        
    df_new = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
    df_new['Nama Siswa'] = master_names
    
    for i in range(1, 32):
        col = f"Tgl {i}"
        if i > max_days:
            df_new[col] = '-'
        else:
            dt = datetime.date(year, month_num, i)
            is_off, _ = is_day_off(dt)
            
            col_values = []
            for idx in range(len(master_names)):
                if idx < len(df_stored) and col in df_stored.columns:
                    val = str(df_stored.loc[idx, col]).strip()
                    if val in ['', 'None', 'nan', 'L', '-']:
                        col_values.append('L' if is_off else '')
                    else:
                        col_values.append(val)
                else:
                    col_values.append('L' if is_off else '')
            df_new[col] = col_values
            
    return df_new

def save_attendance_data(kelas, month, df):
    sheet_name = f"{kelas}_{month}"
    try:
        ws = sh.worksheet(sheet_name)
    except Exception:
        ws = sh.add_worksheet(title=sheet_name, rows="100", cols="40")
        
    ws.clear()
    df = df.fillna('')
    df = df.astype(str)
    data_to_write = [df.columns.values.tolist()] + df.values.tolist()
    ws.update(range_name='A1', values=data_to_write)
    fetch_attendance_data_from_gsheets.clear()

# --- 5. PERHITUNGAN REKAP ABSENSI BULANAN & TAHUNAN ---
def generate_full_report(df):
    df_report = df.copy()
    df_report[date_cols] = df_report[date_cols].fillna('')
    
    active_date_cols = []
    for col in date_cols:
        vals = [str(v).strip().upper() for v in df_report[col].values]
        has_entry = any(v in ['H', 'HADIR', 'S', 'SAKIT', 'I', 'IJIN', 'IZIN', 'A', 'ALPHA', 'ALPA', '.', 'V'] for v in vals)
        if has_entry:
            active_date_cols.append(col)
            
    s_list, i_list, a_list, h_list = [], [], [], []
    pct_h_list, pct_i_list, pct_a_list, pct_s_list = [], [], [], []
    
    for _, row in df_report.iterrows():
        nama = str(row['Nama Siswa']).strip()
        if pd.isna(row['Nama Siswa']) or nama in ["", "(Siswa Belum Diisi di Tab Kelola)"]:
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0)
            pct_h_list.append("0%"); pct_i_list.append("0%"); pct_a_list.append("0%"); pct_s_list.append("0%")
            continue
            
        s, i, a, h = 0, 0, 0, 0
        if not active_date_cols:
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0)
            pct_h_list.append("0%"); pct_i_list.append("0%"); pct_a_list.append("0%"); pct_s_list.append("0%")
            continue
            
        for col in active_date_cols:
            val = str(row[col]).strip().upper()
            if val in ['S', 'SAKIT']:
                s += 1
            elif val in ['I', 'IJIN', 'IZIN']:
                i += 1
            elif val in ['A', 'ALPHA', 'ALPA']:
                a += 1
            elif val in ['H', 'HADIR', '.', 'V', '']:
                h += 1
                
        total = s + i + a + h
        pct_h = (h / total * 100) if total > 0 else 0.0
        pct_i = (i / total * 100) if total > 0 else 0.0
        pct_a = (a / total * 100) if total > 0 else 0.0
        pct_s = (s / total * 100) if total > 0 else 0.0

        s_list.append(s); i_list.append(i); a_list.append(a); h_list.append(h)
        pct_h_list.append(f"{pct_h:.1f}%")
        pct_i_list.append(f"{pct_i:.1f}%")
        pct_a_list.append(f"{pct_a:.1f}%")
        pct_s_list.append(f"{pct_s:.1f}%")
        
    df_report['S'] = s_list
    df_report['I'] = i_list
    df_report['A'] = a_list
    df_report['Hadir'] = h_list
    df_report['% Hadir'] = pct_h_list
    df_report['% Izin'] = pct_i_list
    df_report['% Alpha'] = pct_a_list
    df_report['% Sakit'] = pct_s_list
    return df_report

def calculate_yearly_recap(kelas):
    master_names = get_master_students(kelas)
    recap = {name: {'S': 0, 'I': 0, 'A': 0, 'Hadir': 0} for name in master_names}
    
    for m in months:
        df_m = fetch_attendance_data_from_gsheets(kelas, m)
        rep_m = generate_full_report(df_m)
        for _, row in rep_m.iterrows():
            nama = str(row['Nama Siswa']).strip()
            if nama in recap:
                recap[nama]['S'] += int(row['S'])
                recap[nama]['I'] += int(row['I'])
                recap[nama]['A'] += int(row['A'])
                recap[nama]['Hadir'] += int(row['Hadir'])
                
    rows = []
    for idx, nama in enumerate(master_names, 1):
        s = recap[nama]['S']
        i = recap[nama]['I']
        a = recap[nama]['A']
        h = recap[nama]['Hadir']
        tot = s + i + a + h
        
        pct_h = (h / tot * 100) if tot > 0 else 0.0
        pct_i = (i / tot * 100) if tot > 0 else 0.0
        pct_a = (a / tot * 100) if tot > 0 else 0.0
        pct_s = (s / tot * 100) if tot > 0 else 0.0
        
        rows.append({
            'No': idx,
            'Nama Siswa': nama,
            'Sakit (S)': s,
            'Izin (I)': i,
            'Alpha (A)': a,
            'Total Hadir (H)': h,
            'Total Hari Efektif': tot,
            '% Hadir': f"{pct_h:.1f}%",
            '% Izin': f"{pct_i:.1f}%",
            '% Alpha': f"{pct_a:.1f}%",
            '% Sakit': f"{pct_s:.1f}%"
        })
    return pd.DataFrame(rows)

# --- 6. SISTEM OTENTIKASI & LOGIN ---
passwords = fetch_config_passwords()

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
    # Fungsi Pengatur Konfigurasi Kalender & Pencatat Indeks Libur
    def get_calendar_config(selected_month):
        year = get_year_for_month(selected_month)
        month_num = month_map[selected_month]
        _, max_days = calendar.monthrange(year, month_num)
        days_id = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Mig"]
        
        disabled_cols = []
        col_config = {}
        monthly_holidays = [] # Daftar penampung keterangan libur nasional bulan ini
        
        for i in range(1, 32):
            col_name = f"Tgl {i}"
            if i > max_days:
                disabled_cols.append(col_name)
                col_config[col_name] = st.column_config.TextColumn(label=f"{i} (-)")
            else:
                dt = datetime.date(year, month_num, i)
                day_name = days_id[dt.weekday()]
                is_off, reason = is_day_off(dt)
                
                if is_off:
                    disabled_cols.append(col_name)
                    if reason != "Weekend":
                        col_config[col_name] = st.column_config.TextColumn(label=f"{i} (🔴)")
                        monthly_holidays.append((i, day_name, reason))
                    else:
                        col_config[col_name] = st.column_config.TextColumn(label=f"{i} ({day_name})")
                else:
                    col_config[col_name] = st.column_config.TextColumn(label=f"{i} ({day_name})")
        return col_config, disabled_cols, monthly_holidays

    # A. DASHBOARD HALAMAN GURU KELAS
    if st.session_state.user_role == "Guru Kelas":
        my_class = st.session_state.assigned_class
        st.title(f"🏫 Ruang Kerja Kelas {my_class}")
        
        tab_absen, tab_rekap, tab_nama = st.tabs([
            "📝 Isi Absensi Bulanan", 
            "📊 Rekap Seluruh Bulan (1 Tahun)", 
            "👥 Kelola Daftar Master Siswa"
        ])
        
        with tab_absen:
            selected_month = st.selectbox("📅 Pilih Bulan Absensi:", months)
            col_config, disabled_cols, monthly_holidays = get_calendar_config(selected_month)
            
            # --- TAMPILKAN INDEKS / KETERANGAN LIBUR NASIONAL ---
            if monthly_holidays:
                holiday_items = "\n".join([f"• **Tanggal {day} ({day_name})**: {reason}" for day, day_name, reason in monthly_holidays])
                st.info(f"🔴 **Keterangan Hari Libur Nasional ({selected_month}):**\n\n{holiday_items}")
            else:
                st.caption(f"ℹ️ Bulan {selected_month} tidak memiliki Tanggal Merah Hari Libur Nasional.")
            
            session_key = f"df_{my_class}_{selected_month}"
            if session_key not in st.session_state:
                st.session_state[session_key] = fetch_attendance_data_from_gsheets(my_class, selected_month)
            
            current_data = st.session_state[session_key]
            
            st.subheader("📝 Papan Lembar Absensi")
            st.caption("Catatan: Kolom Nama Siswa, Weekend, & Tanggal Merah (🔴) dikunci otomatis.")
            
            edited_df = st.data_editor(
                current_data,
                num_rows="fixed",
                use_container_width=True,
                column_config=col_config,
                disabled=["Nama Siswa"] + disabled_cols,
                key=f"editor_{session_key}"
            )
            
            st.session_state[session_key] = edited_df
            
            if st.button("💾 Simpan Absensi Bulan Ini", type="primary"):
                with st.spinner("Mengunci absensi ke cloud..."):
                    save_attendance_data(my_class, selected_month, edited_df)
                st.success(f"🎉 Absensi Kelas {my_class} untuk bulan {selected_month} berhasil diamankan!")
                st.rerun()
                
            st.write("---")
            st.subheader("📋 Ringkasan Kehadiran Bulan Ini")
            full_report = generate_full_report(edited_df)
            st.dataframe(
                full_report[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '% Hadir', '% Izin', '% Alpha', '% Sakit']], 
                use_container_width=True
            )

        with tab_rekap:
            st.subheader(f"📊 Rekapitulasi Kehadiran Akumulasi Seluruh Bulan (Kelas {my_class})")
            st.info("💡 Klik tombol di bawah untuk mengalkulasi akumulasi absensi 12 bulan dari cloud.")
            
            recap_key = f"yearly_recap_{my_class}"
            if st.button("🔄 Muat / Perbarui Rekap 1 Tahun", type="primary"):
                with st.spinner("Menghitung akumulasi 12 bulan..."):
                    st.session_state[recap_key] = calculate_yearly_recap(my_class)
                st.success("🎉 Data rekapitulasi 1 tahun berhasil diperbarui!")
                
            if recap_key in st.session_state:
                st.dataframe(st.session_state[recap_key], use_container_width=True, hide_index=True)

        with tab_nama:
            st.subheader(f"👥 Pusat Pengaturan Siswa Kelas {my_class}")
            st.info("Menambah, menghapus, atau mengganti ejaan nama di sini akan otomatis merubah seluruh lembar 12 bulan absensi kelas Anda.")
            
            # --- 📥 UPGRADE: FITUR EXPORT & IMPORT DATA MASTER KELAS ---
            with st.expander("📥 📤 Fitur Export / Import Data Master Siswa (CSV / Excel)", expanded=False):
                col_exp, col_imp = st.columns(2)
                
                # 1. EXPORT
                with col_exp:
                    st.markdown("##### 📥 Export Master Siswa")
                    st.caption("Unduh daftar siswa kelas ini ke file CSV.")
                    current_masters_list = get_master_students(my_class)
                    df_export = pd.DataFrame(current_masters_list, columns=["Nama Siswa"])
                    csv_bytes = df_export.to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label=f"⬇️ Download CSV Master Kelas {my_class}",
                        data=csv_bytes,
                        file_name=f"Master_Siswa_Kelas_{my_class}.csv",
                        mime="text/csv",
                        key=f"dl_csv_{my_class}"
                    )
                
                # 2. IMPORT
                with col_imp:
                    st.markdown("##### 📤 Import Master Siswa")
                    st.caption("Unggah file CSV atau Excel (.xlsx) untuk mengganti data master.")
                    uploaded_file = st.file_uploader(
                        f"Pilih file CSV/Excel untuk Kelas {my_class}:",
                        type=["csv", "xlsx"],
                        key=f"uploader_{my_class}"
                    )
                    
                    if uploaded_file is not None:
                        try:
                            if uploaded_file.name.endswith(".csv"):
                                df_imp = pd.read_csv(uploaded_file)
                            else:
                                df_imp = pd.read_excel(uploaded_file)
                            
                            # Deteksi kolom nama
                            if "Nama Siswa" in df_imp.columns:
                                imp_names = df_imp["Nama Siswa"].dropna().astype(str).str.strip().tolist()
                            else:
                                imp_names = df_imp.iloc[:, 0].dropna().astype(str).str.strip().tolist()
                            
                            imp_names = [n for n in imp_names if n not in ["", "nan", "None"]]
                            st.success(f"Ditemukan {len(imp_names)} siswa dari file yang diupload.")
                            
                            if st.button("💾 Terapkan Data Import Ini", type="primary", key=f"btn_apply_imp_{my_class}"):
                                with st.spinner("Menyimpan data hasil import..."):
                                    save_master_students(my_class, imp_names)
                                    for m in months:
                                        k = f"df_{my_class}_{m}"
                                        if k in st.session_state:
                                            del st.session_state[k]
                                st.success("🎉 Data master berhasil diperbarui dari file import!")
                                st.rerun()
                        except Exception as ex_err:
                            st.error(f"❌ Gagal memproses file: {ex_err}")
            
            st.write("---")
            st.markdown("##### ✏️ Edit Manual Daftar Siswa")
            current_masters = get_master_students(my_class)
            df_masters = pd.DataFrame(current_masters, columns=["Nama Siswa"])
            
            edited_masters = st.data_editor(
                df_masters,
                num_rows="dynamic",
                use_container_width=True,
                key=f"master_edit_workspace_{my_class}"
            )
            
            if st.button("💾 Terapkan & Sinkronisasikan Nama Baru", type="primary"):
                with st.spinner("Sinkronisasi database induk..."):
                    new_names_list = edited_masters["Nama Siswa"].dropna().tolist()
                    save_master_students(my_class, new_names_list)
                    for m in months:
                        k = f"df_{my_class}_{m}"
                        if k in st.session_state:
                            del st.session_state[k]
                st.success("🎉 Berhasil! Nama siswa diselaraskan mutlak di seluruh kalender bulan.")
                st.rerun()

    # B. DASHBOARD HALAMAN GURU PIKET
    elif st.session_state.user_role == "Guru Piket":
        st.title("🕵️‍♂️ Dashboard Peninjauan Guru Piket")
        
        tab_piket_bulanan, tab_piket_tahunan = st.tabs(["📅 Laporan Bulanan", "📊 Rekap Akumulasi Seluruh Bulan"])
        
        with tab_piket_bulanan:
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                piket_class = st.selectbox("🏫 Pantau Kelas:", classes, key="piket_c_m")
            with col_p2:
                piket_month = st.selectbox("📅 Pilih Bulan:", months, key="piket_m_m")
                
            col_config, _, monthly_holidays = get_calendar_config(piket_month)
            
            # --- TAMPILKAN INDEKS / KETERANGAN LIBUR NASIONAL DI HALAMAN PIKET ---
            if monthly_holidays:
                holiday_items = "\n".join([f"• **Tanggal {day} ({day_name})**: {reason}" for day, day_name, reason in monthly_holidays])
                st.info(f"🔴 **Keterangan Hari Libur Nasional ({piket_month}):**\n\n{holiday_items}")
            else:
                st.caption(f"ℹ️ Bulan {piket_month} tidak memiliki Tanggal Merah Hari Libur Nasional.")
                
            raw_data = fetch_attendance_data_from_gsheets(piket_class, piket_month)
            calculated_data = generate_full_report(raw_data)
            
            st.write("---")
            st.subheader(f"📊 Laporan Real-Time Kehadiran Kelas {piket_class} ({piket_month})")
            st.dataframe(calculated_data, use_container_width=True, column_config=col_config)

        with tab_piket_tahunan:
            piket_class_year = st.selectbox("🏫 Pilih Kelas untuk Rekapitulasi Tahunan:", classes, key="piket_c_y")
            st.subheader(f"📊 Rekapitulasi Total Kehadiran Kelas {piket_class_year} (12 Bulan)")
            
            piket_recap_key = f"piket_recap_{piket_class_year}"
            if st.button("🔄 Hitung Rekapitulasi Kelas Ini", type="primary"):
                with st.spinner("Memuat data 12 bulan..."):
                    st.session_state[piket_recap_key] = calculate_yearly_recap(piket_class_year)
                    
            if piket_recap_key in st.session_state:
                st.dataframe(st.session_state[piket_recap_key], use_container_width=True, hide_index=True)

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
                st.rerun()
                
        with tab_master_all:
            st.subheader("📊 Database Induk Nama Siswa Seluruh Kelas")
            df_all_masters = fetch_all_master_df()
            
            # --- 📥 UPGRADE: FITUR EXPORT & IMPORT PUSAT (ADMIN) ---
            with st.expander("📥 📤 Export / Import Database Pusat Master Seluruh Sekolah (CSV / Excel)", expanded=False):
                col_adm_exp, col_adm_imp = st.columns(2)
                
                # EXPORT PUSAT
                with col_adm_exp:
                    st.markdown("##### 📥 Export Master Seluruh Sekolah")
                    st.caption("Unduh database master seluruh 18 kelas ke format CSV.")
                    csv_all_bytes = df_all_masters.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="⬇️ Download CSV Master Seluruh Sekolah",
                        data=csv_all_bytes,
                        file_name="Master_Siswa_Seluruh_Sekolah.csv",
                        mime="text/csv",
                        key="dl_admin_all_csv"
                    )
                
                # IMPORT PUSAT
                with col_adm_imp:
                    st.markdown("##### 📤 Import Master Seluruh Sekolah")
                    st.caption("Unggah file CSV/Excel dengan header nama kelas (7A, 7B, ... 9F).")
                    uploaded_all = st.file_uploader(
                        "Pilih file CSV/Excel Seluruh Sekolah:",
                        type=["csv", "xlsx"],
                        key="uploader_admin_all"
                    )
                    
                    if uploaded_all is not None:
                        try:
                            if uploaded_all.name.endswith(".csv"):
                                df_imp_all = pd.read_csv(uploaded_all)
                            else:
                                df_imp_all = pd.read_excel(uploaded_all)
                            
                            st.write("👀 Preview File Import Pusat:")
                            st.dataframe(df_imp_all.head(5), use_container_width=True)
                            
                            if st.button("💾 Terapkan & Timpa Database Pusat", type="primary", key="btn_apply_imp_all"):
                                with st.spinner("Menyimpan ke cloud Google Sheets..."):
                                    df_cleaned = df_imp_all.fillna("")
                                    ws = sh.worksheet("MASTER_SISWA")
                                    ws.clear()
                                    ws.update(range_name='A1', values=[df_cleaned.columns.values.tolist()] + df_cleaned.values.tolist())
                                    fetch_all_master_df.clear()
                                st.success("🎉 Master siswa 18 kelas seluruh sekolah berhasil ditimpa dari file import!")
                                st.rerun()
                        except Exception as ex_admin_err:
                            st.error(f"❌ Gagal memproses file import pusat: {ex_admin_err}")
            
            st.write("---")
            st.markdown("##### ✏️ Edit Table Manual Seluruh Kelas")
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
                    fetch_all_master_df.clear()
                st.success("🔒 Database pusat 18 kelas sekolah berhasil dikunci!")
                st.rerun()
