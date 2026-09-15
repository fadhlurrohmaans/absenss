import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
import datetime
import calendar
import time
import io

# --- 0. KONFIGURASI KALENDER & LIBUR NASIONAL ---
try:
    import holidays
    id_holidays = holidays.ID(years=[2026, 2027])
except ImportError:
    id_holidays = {}

manual_holidays = {
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
}

def is_day_off(dt):
    if dt.weekday() in [5, 6]:
        return True, "Weekend"
    if dt in id_holidays:
        return True, str(id_holidays.get(dt))
    if dt in manual_holidays:
        return True, manual_holidays[dt]
    return False, ""

st.set_page_config(layout="wide", page_title="Sistem Absensi & Early Warning Kedisiplinan Siswa", page_icon="🏫")

st.markdown("""
    <style>
    div[data-testid="stDataFrame"] { -webkit-overflow-scrolling: touch; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

classes = [f"{grade}{letter}" for grade in [7, 8, 9] for letter in ['A', 'B', 'C', 'D', 'E', 'F']]
months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER', 'JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']
ganjil_months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER']
genap_months = ['JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']
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
def get_gspread_spreadsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key(st.secrets["spreadsheet_id"])

try:
    sh = get_gspread_spreadsheet()
except Exception as e:
    st.error(f"❌ Gagal terhubung ke Database Google Sheets: {e}")
    st.stop()

# --- 2. LAZY FETCHING DENGAN CACHE & RETRY ---
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_sheet_with_retry(sheet_name):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            ws = sh.worksheet(sheet_name)
            return pd.DataFrame(ws.get_all_records())
        except WorksheetNotFound:
            return pd.DataFrame()
        except APIError as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

# --- 3. MASTER SISWA & CONFIG ---
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all_master_df():
    df = fetch_sheet_with_retry("MASTER_SISWA")
    if df.empty:
        df = pd.DataFrame(columns=classes)
        for c in classes:
            df[c] = initial_students + [""] * (150 - len(initial_students))
    for c in classes:
        if c not in df.columns: df[c] = ""
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
    fetch_sheet_with_retry.clear("MASTER_SISWA")

def save_all_master_df(df_master):
    df_master = df_master.fillna("")
    ws = sh.worksheet("MASTER_SISWA")
    ws.clear()
    ws.update(range_name='A1', values=[df_master.columns.values.tolist()] + df_master.values.tolist())
    fetch_all_master_df.clear()
    fetch_sheet_with_retry.clear("MASTER_SISWA")

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_config_passwords():
    df = fetch_sheet_with_retry("CONFIG")
    if not df.empty and 'Key' in df.columns and 'Password' in df.columns:
        return dict(zip(df['Key'].astype(str), df['Password'].astype(str)))
    
    # PERUBAHAN: Menambahkan Key & Password Wali Kelas dan Sekretaris secara terpisah
    keys = ['Admin', 'Guru Piket', 'Guru BK', 'Kepala Sekolah'] + classes + [f"Wali{c}" for c in classes]
    default_passwords = ['admin123', 'piket123', 'bk123', 'kepsek123'] + \
                        [f"{c.lower()}123" for c in classes] + \
                        [f"wali{c.lower()}" for c in classes]
    
    return dict(zip(keys, default_passwords))

def save_config_passwords(password_dict):
    ws = sh.worksheet("CONFIG")
    ws.clear()
    df = pd.DataFrame(list(password_dict.items()), columns=['Key', 'Password'])
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
    fetch_config_passwords.clear()
    fetch_sheet_with_retry.clear("CONFIG")

# --- 4. LOG KETERLAMBATAN, FLAGGING & KONSELING ---
def fetch_lateness_logs(): return fetch_sheet_with_retry("LOG_KETERLAMBATAN")

def save_lateness_entry(tanggal, kelas, nama, menit, pencatat):
    try:
        try: ws = sh.worksheet("LOG_KETERLAMBATAN")
        except WorksheetNotFound:
            ws = sh.add_worksheet("LOG_KETERLAMBATAN", rows="1000", cols="10")
            ws.append_row(['Tanggal', 'Kelas', 'Nama Siswa', 'Menit Terlambat', 'Pencatat'])
        ws.append_row([str(tanggal), kelas, nama, int(menit), pencatat])
        fetch_sheet_with_retry.clear("LOG_KETERLAMBATAN")
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan keterlambatan: {e}")
        return False

def fetch_flags(): return fetch_sheet_with_retry("FLAGS_PERILAKU")

def save_flag_entry(tanggal, kelas, nama, tipe, kategori, catatan, pencatat):
    dt = datetime.datetime.strptime(str(tanggal), "%Y-%m-%d").date() if isinstance(tanggal, str) else tanggal
    year_week = f"{dt.year}-{dt.isocalendar()[1]}"
    
    df_flags = fetch_flags()
    if not df_flags.empty and 'Nama Siswa' in df_flags.columns and 'TahunMinggu' in df_flags.columns:
        existing = df_flags[(df_flags['Nama Siswa'] == nama) & (df_flags['TahunMinggu'] == year_week)]
        if len(existing) > 0:
            return False, f"⚠️ Siswa '{nama}' sudah diberikan flagging pada minggu ini ({year_week})."

    try:
        try: ws = sh.worksheet("FLAGS_PERILAKU")
        except WorksheetNotFound:
            ws = sh.add_worksheet("FLAGS_PERILAKU", rows="1000", cols="10")
            ws.append_row(['Tanggal', 'TahunMinggu', 'Kelas', 'Nama Siswa', 'Tipe', 'Kategori', 'Catatan', 'Pencatat'])
        ws.append_row([str(dt), year_week, kelas, nama, tipe, kategori, catatan, pencatat])
        fetch_sheet_with_retry.clear("FLAGS_PERILAKU")
        return True, "✅ Flagging perilaku berhasil dicatat!"
    except Exception as e: return False, f"Gagal menyimpan flag: {e}"

def fetch_counseling_logs(): return fetch_sheet_with_retry("KONSELING_BK")

def save_counseling_log(tanggal, kelas, nama, ringkasan, rekomendasi, status, konselor):
    try:
        try: ws = sh.worksheet("KONSELING_BK")
        except WorksheetNotFound:
            ws = sh.add_worksheet("KONSELING_BK", rows="500", cols="10")
            ws.append_row(['ID', 'Tanggal', 'Kelas', 'Nama Siswa', 'Ringkasan', 'Rekomendasi', 'Status', 'Konselor'])
        c_id = f"BK-{int(datetime.datetime.now().timestamp())}"
        ws.append_row([c_id, str(tanggal), kelas, nama, ringkasan, rekomendasi, status, konselor])
        fetch_sheet_with_retry.clear("KONSELING_BK")
        return True
    except Exception as e: return False

# --- 5. DATA ABSENSI BULANAN & GRID EDITOR ---
def fetch_attendance_data_from_cache(kelas, month):
    sheet_name = f"{kelas}_{month}"
    df_stored = fetch_sheet_with_retry(sheet_name)
    year = get_year_for_month(month)
    month_num = month_map[month]
    _, max_days = calendar.monthrange(year, month_num)
    master_names = get_master_students(kelas) or ["(Siswa Belum Diisi)"]
    
    df_new = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
    df_new['Nama Siswa'] = master_names
    
    for i in range(1, 32):
        col = f"Tgl {i}"
        if i > max_days:
            df_new[col] = '-'
        else:
            dt = datetime.date(year, month_num, i)
            is_off, _ = is_day_off(dt)
            col_vals = []
            for idx in range(len(master_names)):
                if not df_stored.empty and idx < len(df_stored) and col in df_stored.columns:
                    val = str(df_stored.loc[idx, col]).strip()
                    col_vals.append('L' if (is_off and val in ['', 'None', 'nan', '-']) else val)
                else:
                    col_vals.append('L' if is_off else '')
            df_new[col] = col_vals
    return df_new

def save_attendance_data(kelas, month, df):
    sheet_name = f"{kelas}_{month}"
    try: ws = sh.worksheet(sheet_name)
    except Exception: ws = sh.add_worksheet(title=sheet_name, rows="100", cols="40")
        
    ws.clear()
    df = df.fillna('').astype(str)
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
    fetch_sheet_with_retry.clear(sheet_name)

def get_calendar_config(selected_month):
    year = get_year_for_month(selected_month)
    month_num = month_map[selected_month]
    _, max_days = calendar.monthrange(year, month_num)
    days_id = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Mig"]
    
    disabled_cols, col_config, monthly_holidays = [], {}, []
    
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
                else: col_config[col_name] = st.column_config.TextColumn(label=f"{i} ({day_name})")
            else: col_config[col_name] = st.column_config.TextColumn(label=f"{i} ({day_name})")
    return col_config, disabled_cols, monthly_holidays

def generate_full_report(df):
    df_report = df.copy()
    s_list, i_list, a_list, h_list = [], [], [], []
    pct_h_list, pct_i_list, pct_a_list, pct_s_list = [], [], [], []
    
    active_date_cols = [c for c in date_cols if any(str(v).strip().upper() in ['H', 'S', 'I', 'A', '.', 'V'] for v in df_report[c].values)]

    for _, row in df_report.iterrows():
        s, i, a, h = 0, 0, 0, 0
        if not active_date_cols:
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0)
            pct_h_list.append("0%"); pct_i_list.append("0%"); pct_a_list.append("0%"); pct_s_list.append("0%")
            continue

        for col in active_date_cols:
            val = str(row[col]).strip().upper()
            if val in ['S', 'SAKIT']: s += 1
            elif val in ['I', 'IJIN', 'IZIN']: i += 1
            elif val in ['A', 'ALPHA', 'ALPA']: a += 1
            elif val in ['H', 'HADIR', '.', 'V', '']: h += 1
            
        total = s + i + a + h
        s_list.append(s); i_list.append(i); a_list.append(a); h_list.append(h)
        pct_h_list.append(f"{(h / total * 100):.1f}%" if total > 0 else "0%")
        pct_i_list.append(f"{(i / total * 100):.1f}%" if total > 0 else "0%")
        pct_a_list.append(f"{(a / total * 100):.1f}%" if total > 0 else "0%")
        pct_s_list.append(f"{(s / total * 100):.1f}%" if total > 0 else "0%")

    df_report['S'], df_report['I'], df_report['A'], df_report['Hadir'] = s_list, i_list, a_list, h_list
    df_report['% Hadir'], df_report['% Izin'], df_report['% Alpha'], df_report['% Sakit'] = pct_h_list, pct_i_list, pct_a_list, pct_s_list
    return df_report

def calculate_period_recap(kelas, target_months):
    master_names = get_master_students(kelas)
    recap = {name: {'S': 0, 'I': 0, 'A': 0, 'Hadir': 0} for name in master_names}
    
    for m in target_months:
        df_m = fetch_attendance_data_from_cache(kelas, m)
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
        s, i, a, h = recap[nama]['S'], recap[nama]['I'], recap[nama]['A'], recap[nama]['Hadir']
        tot = s + i + a + h
        rows.append({
            'No': idx, 'Nama Siswa': nama, 'Sakit (S)': s, 'Izin (I)': i, 'Alpha (A)': a,
            'Total Hadir (H)': h, 'Total Hari Efektif': tot,
            '% Hadir': f"{(h / tot * 100):.1f}%" if tot > 0 else "0%",
            '% Izin': f"{(i / tot * 100):.1f}%" if tot > 0 else "0%",
            '% Alpha': f"{(a / tot * 100):.1f}%" if tot > 0 else "0%",
            '% Sakit': f"{(s / tot * 100):.1f}%" if tot > 0 else "0%"
        })
    return pd.DataFrame(rows)

# --- 6. OPTIMIZED BATCH RISK SCORING ENGINE ---
def get_class_alpa_summary(kelas):
    students = get_master_students(kelas)
    alpa_map = {s: 0 for s in students}
    for m in months:
        df_m = fetch_attendance_data_from_cache(kelas, m)
        rep = generate_full_report(df_m)
        for _, row in rep.iterrows():
            nama = str(row['Nama Siswa']).strip()
            if nama in alpa_map:
                alpa_map[nama] += int(row['A'])
    return alpa_map

def calculate_class_risk_table(kelas, df_late_all=None, df_flags_all=None):
    students = get_master_students(kelas)
    alpa_map = get_class_alpa_summary(kelas)
    if df_late_all is None: df_late_all = fetch_lateness_logs()
    if df_flags_all is None: df_flags_all = fetch_flags()
    
    risk_table = []
    for s in students:
        total_alpa = alpa_map.get(s, 0)
        total_late_min, neg_flags, pos_flags = 0, 0, 0
        
        if not df_late_all.empty and 'Nama Siswa' in df_late_all.columns:
            s_late = df_late_all[(df_late_all['Nama Siswa'] == s) & (df_late_all['Kelas'] == kelas)]
            total_late_min = s_late['Menit Terlambat'].astype(int).sum() if not s_late.empty else 0
            
        if not df_flags_all.empty and 'Nama Siswa' in df_flags_all.columns:
            s_flags = df_flags_all[(df_flags_all['Nama Siswa'] == s) & (df_flags_all['Kelas'] == kelas)]
            if not s_flags.empty:
                neg_flags = len(s_flags[s_flags['Tipe'] == 'NEGATIF'])
                pos_flags = len(s_flags[s_flags['Tipe'] == 'POSITIF'])
                
        score = max(0, (total_alpa * 15) + (total_late_min // 5) + (neg_flags * 10) - (pos_flags * 5))
        zone = "ZONA HIJAU" if score <= 20 else ("ZONA KUNING" if score <= 50 else "ZONA MERAH")
            
        risk_table.append({
            'Nama Siswa': s, 'Zona Risiko': zone, 'Skor Poin': score,
            'Alpa (Hari)': total_alpa, 'Terlambat (Menit)': total_late_min,
            'Flag Negatif': neg_flags, 'Flag Positif': pos_flags
        })
    return pd.DataFrame(risk_table)

def generate_ai_student_narrative(student_name, risk_row):
    badge = "🟢 Hijau (Aman)" if risk_row['Zona Risiko'] == "ZONA HIJAU" else ("🟡 Kuning (Waspada)" if risk_row['Zona Risiko'] == "ZONA KUNING" else "🔴 Merah (Bahaya)")
    narrative = f"### 🤖 Evaluasi Naratif AI untuk: {student_name}\n\n**Status Risiko:** {badge} (Skor Total Kedisiplinan: **{risk_row['Skor Poin']} Poin**)\n\n"
    if risk_row['Alpa (Hari)'] == 0 and risk_row['Terlambat (Menit)'] == 0: narrative += "• **Presensi & Ketepatan Waktu:** Siswa menunjukkan tingkat kedisiplinan yang sangat baik tanpa riwayat Alpa maupun keterlambatan.\n"
    else: narrative += f"• **Presensi & Ketepatan Waktu:** Terdeteksi akumulasi **{risk_row['Alpa (Hari)']} hari Alpa** dan akumulasi keterlambatan **{risk_row['Terlambat (Menit)']} menit**.\n"
    narrative += f"• **Catatan Perilaku Guru:** Tercatat {risk_row['Flag Positif']} indikator positif dan {risk_row['Flag Negatif']} catatan indikator negatif.\n"
    if risk_row['Zona Risiko'] == "ZONA MERAH": narrative += "\n⚠️ **Rekomendasi Tindakan (Prioritas BK):** Siswa berada dalam Zona Merah. Disarankan untuk *segera melayangkan Surat Pemanggilan Orang Tua (SP)*."
    elif risk_row['Zona Risiko'] == "ZONA KUNING": narrative += "\n💡 **Rekomendasi Tindakan (Wali Kelas):** Siswa dalam Zona Waspada. Wali Kelas disarankan melakukan dialog personal."
    else: narrative += "\n✨ **Rekomendasi Tindakan:** Pertahankan motivasi belajar siswa dan berikan apresiasi atas kedisiplinan yang terjaga."
    return narrative

# --- 7. OTENTIKASI & USER INTERFACE TERPISAH ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'assigned_class' not in st.session_state: st.session_state.assigned_class = None

st.sidebar.title("🏢 Early Warning & Absensi Digital")

if st.session_state.logged_in:
    st.sidebar.success(f"Masuk sebagai:\n**{st.session_state.user_role}** " + (f"({st.session_state.assigned_class})" if st.session_state.assigned_class else ""))
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.assigned_class = None
        st.rerun()

# GERBANG LOGIN TERPISAH
if not st.session_state.logged_in:
    st.title("🔐 Login Sistem Keamanan Absensi & Kedisiplinan")
    st.caption("GovTech Education Platform - Integrated Early Warning System")
    
    login_tab_wali, login_tab_staf = st.tabs(["🏫 Sekretaris / Wali Kelas", "🏢 Guru Piket, BK, Kepsek & Admin"])
    
    # PERUBAHAN LOGIN: Memisahkan peran Sekretaris & Wali Kelas dengan opsi radio button
    with login_tab_wali:
        with st.form("form_login_wali"):
            st.subheader("Login Ruang Kelas")
            role_wali = st.radio("Masuk Sebagai:", ["Sekretaris Kelas", "Wali Kelas"], horizontal=True)
            target_class = st.selectbox("Pilih Kelas Anda:", classes, key="sel_wali_class")
            password_wali = st.text_input("Masukkan Password:", type="password", key="pass_wali")
            
            if st.form_submit_button("🔑 Masuk Ke Ruang Kelas", type="primary"):
                passwords = fetch_config_passwords()
                
                # Cek peran untuk menentukan key yang dicocokkan
                login_key = target_class if role_wali == "Sekretaris Kelas" else f"Wali{target_class}"
                
                if password_wali == passwords.get(login_key):
                    st.session_state.logged_in = True
                    st.session_state.user_role = role_wali
                    st.session_state.assigned_class = target_class
                    st.rerun()
                else:
                    st.error("❌ Password Salah! Pastikan Anda menggunakan sandi yang benar sesuai peran (Sekretaris/Wali).")
                    
    with login_tab_staf:
        with st.form("form_login_staf"):
            st.subheader("Login Staf & Manajemen Sekolah")
            role_staf = st.selectbox("Pilih Peran / Akses Peran:", ["Guru Piket / Pelajaran", "Guru BK", "Kepala Sekolah", "Administrator System"], key="sel_staf_role")
            password_staf = st.text_input("Masukkan Password Akun:", type="password", key="pass_staf")
            
            if st.form_submit_button("🔑 Masuk Portal Staf", type="primary"):
                passwords = fetch_config_passwords()
                role_key_map = {"Guru Piket / Pelajaran": "Guru Piket", "Guru BK": "Guru BK", "Kepala Sekolah": "Kepala Sekolah", "Administrator System": "Admin"}
                key_name = role_key_map.get(role_staf)
                if password_staf == passwords.get(key_name):
                    st.session_state.logged_in = True
                    st.session_state.user_role = role_staf
                    st.session_state.assigned_class = None
                    st.rerun()
                else:
                    st.error("❌ Password Akun Salah!")

else:
    # 1. SEKRETARIS KELAS & WALI KELAS (DIPISAH BERDASARKAN HAK AKSES TAB)
    if st.session_state.user_role in ["Sekretaris Kelas", "Wali Kelas"]:
        my_class = st.session_state.assigned_class
        st.title(f"🏫 Ruang Kerja {st.session_state.user_role} {my_class}")
        
        # PERUBAHAN: Menentukan tab yang terlihat berdasarkan hak akses
        if st.session_state.user_role == "Wali Kelas":
            tabs = st.tabs([
                "📝 Isi Absensi Bulanan (Grid)", 
                "🍂 Rekap Semester Ganjil",
                "🌸 Rekap Semester Genap",
                "📊 Rekap 1 Tahun",
                "🎯 Matriks Risk Scoring & AI",
                "👥 Kelola Master Siswa"
            ])
            tab_absen, tab_ganjil, tab_genap, tab_rekap, tab_risk, tab_nama = tabs
        else:
            # Sekretaris Kelas hanya menerima 1 Tab
            tabs = st.tabs(["📝 Isi Absensi Bulanan (Grid)"])
            tab_absen = tabs[0]
        
        with tab_absen:
            selected_month = st.selectbox("📅 Pilih Bulan Absensi:", months)
            col_config, disabled_cols, monthly_holidays = get_calendar_config(selected_month)
            
            if monthly_holidays:
                holiday_items = "\n".join([f"• **Tanggal {day} ({day_name})**: {reason}" for day, day_name, reason in monthly_holidays])
                st.info(f"🔴 **Keterangan Hari Libur Nasional ({selected_month}):**\n\n{holiday_items}")
            else:
                st.caption(f"ℹ️ Bulan {selected_month} tidak memiliki Tanggal Merah Hari Libur Nasional.")
            
            session_key = f"df_{my_class}_{selected_month}"
            if session_key not in st.session_state:
                st.session_state[session_key] = fetch_attendance_data_from_cache(my_class, selected_month)
            
            current_data = st.session_state[session_key]
            
            st.subheader("📝 Papan Lembar Absensi Digital")
            st.caption("Petunjuk: Isi H (Hadir), S (Sakit), I (Izin), A (Alpha). Kolom Nama, Weekend, & Tanggal Merah dikunci otomatis.")
            
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
                with st.spinner("Mengunci data absensi ke Cloud Google Sheets..."):
                    save_attendance_data(my_class, selected_month, edited_df)
                st.success(f"🎉 Absensi Kelas {my_class} bulan {selected_month} berhasil disimpan!")
                st.rerun()
                
            st.write("---")
            st.subheader("📋 Ringkasan Kehadiran Bulan Ini")
            full_report = generate_full_report(edited_df)
            st.dataframe(full_report[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '% Hadir', '% Izin', '% Alpha', '% Sakit']], use_container_width=True)

        # Tab ekstra hanya dimuat dan ditampilkan untuk Wali Kelas
        if st.session_state.user_role == "Wali Kelas":
            with tab_ganjil:
                st.subheader(f"🍂 Rekapitulasi Semester Ganjil (Juli - Desember) - Kelas {my_class}")
                if st.button("🔄 Muat / Perbarui Rekap Semester Ganjil", type="primary", key="btn_ganjil_sk"):
                    with st.spinner("Kalkulasi Semester Ganjil..."):
                        st.session_state[f"ganjil_{my_class}"] = calculate_period_recap(my_class, ganjil_months)
                    st.success("🎉 Rekap Semester Ganjil diperbarui!")
                if f"ganjil_{my_class}" in st.session_state:
                    st.dataframe(st.session_state[f"ganjil_{my_class}"], use_container_width=True, hide_index=True)

            with tab_genap:
                st.subheader(f"🌸 Rekapitulasi Semester Genap (Januari - Juni) - Kelas {my_class}")
                if st.button("🔄 Muat / Perbarui Rekap Semester Genap", type="primary", key="btn_genap_sk"):
                    with st.spinner("Kalkulasi Semester Genap..."):
                        st.session_state[f"genap_{my_class}"] = calculate_period_recap(my_class, genap_months)
                    st.success("🎉 Rekap Semester Genap diperbarui!")
                if f"genap_{my_class}" in st.session_state:
                    st.dataframe(st.session_state[f"genap_{my_class}"], use_container_width=True, hide_index=True)

            with tab_rekap:
                st.subheader(f"📊 Rekapitulasi Akumulasi 1 Tahun - Kelas {my_class}")
                if st.button("🔄 Muat / Perbarui Rekap 1 Tahun", type="primary", key="btn_yearly_sk"):
                    with st.spinner("Kalkulasi 12 Bulan..."):
                        st.session_state[f"yearly_{my_class}"] = calculate_period_recap(my_class, months)
                    st.success("🎉 Rekap 1 Tahun diperbarui!")
                if f"yearly_{my_class}" in st.session_state:
                    st.dataframe(st.session_state[f"yearly_{my_class}"], use_container_width=True, hide_index=True)

            with tab_risk:
                st.subheader(f"🛡️ Analisis Risiko Kedisiplinan Siswa - Kelas {my_class}")
                if st.button("🔄 Hitung Matriks Risiko Kelas", type="primary", key="btn_risk_sk"):
                    with st.spinner("Mengkalkulasi tingkat risiko kedisiplinan siswa..."):
                        st.session_state[f"risk_df_{my_class}"] = calculate_class_risk_table(my_class)
                    st.success("🎉 Matriks Risiko Diperbarui!")
                if f"risk_df_{my_class}" in st.session_state:
                    df_risk = st.session_state[f"risk_df_{my_class}"]
                    if not df_risk.empty:
                        col1, col2, col3 = st.columns(3)
                        col1.metric("🔴 Zona Merah (Bahaya)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA MERAH']))
                        col2.metric("🟡 Zona Kuning (Waspada)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA KUNING']))
                        col3.metric("🟢 Zona Hijau (Aman)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA HIJAU']))
                        st.dataframe(df_risk.sort_values(by='Skor Poin', ascending=False), use_container_width=True)
                        st.write("---")
                        st.subheader("🤖 AI Narrative Evaluation Generator")
                        selected_eval_student = st.selectbox("Pilih Siswa untuk Generasi Evaluasi AI:", df_risk['Nama Siswa'].tolist(), key="ai_eval_sk")
                        if st.button("✨ Generasi Deskripsi Naratif AI"):
                            s_row = df_risk[df_risk['Nama Siswa'] == selected_eval_student].iloc[0].to_dict()
                            st.markdown(generate_ai_student_narrative(selected_eval_student, s_row))
                else:
                    st.info("Klik tombol di atas untuk memuat analisis risiko kelas.")

            with tab_nama:
                st.subheader(f"👥 Pengaturan Daftar Siswa Kelas {my_class}")
                with st.expander("📥 📤 Import / Export Data Master Siswa (CSV / Excel)", expanded=False):
                    col_exp, col_imp = st.columns(2)
                    with col_exp:
                        current_masters_list = get_master_students(my_class)
                        df_export = pd.DataFrame(current_masters_list, columns=["Nama Siswa"])
                        st.download_button(label=f"⬇️ Download CSV Master Kelas {my_class}", data=df_export.to_csv(index=False).encode('utf-8'), file_name=f"Master_Siswa_{my_class}.csv", mime="text/csv")
                    with col_imp:
                        uploaded_file = st.file_uploader(f"Pilih file CSV/Excel untuk Kelas {my_class}:", type=["csv", "xlsx"])
                        if uploaded_file is not None:
                            try:
                                df_imp = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
                                imp_names = df_imp["Nama Siswa"].dropna().astype(str).str.strip().tolist() if "Nama Siswa" in df_imp.columns else df_imp.iloc[:, 0].dropna().astype(str).str.strip().tolist()
                                imp_names = [n for n in imp_names if n not in ["", "nan", "None"]]
                                st.success(f"Terdeteksi {len(imp_names)} siswa dari file.")
                                if st.button("💾 Terapkan Data Import Ini", type="primary"):
                                    save_master_students(my_class, imp_names)
                                    st.success("🎉 Data master berhasil diperbarui!")
                                    st.rerun()
                            except Exception as ex_err:
                                st.error(f"❌ Gagal membaca file: {ex_err}")
                st.write("---")
                st.markdown("##### ✏️ Edit Manual Nama Siswa")
                current_masters = get_master_students(my_class)
                edited_masters = st.data_editor(pd.DataFrame(current_masters, columns=["Nama Siswa"]), num_rows="dynamic", use_container_width=True, key=f"master_edit_{my_class}")
                if st.button("💾 Terapkan Perubahan Nama", type="primary"):
                    new_names = edited_masters["Nama Siswa"].dropna().tolist()
                    save_master_students(my_class, new_names)
                    st.success("🎉 Daftar nama berhasil diselaraskan!")
                    st.rerun()

    # 2. GURU PIKET
    elif st.session_state.user_role == "Guru Piket / Pelajaran":
        st.title("🕵️‍♂️ Modul Guru Piket & Pelajaran")
        tab_piket_input, tab_flagging = st.tabs(["⏱️ Input Presensi & Keterlambatan", "🚩 Fitur Flagging Perilaku"])
        with tab_piket_input:
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1: p_class = st.selectbox("Pilih Kelas:", classes, key="piket_c")
            with col_p2: p_month = st.selectbox("Pilih Bulan:", months, key="piket_m")
            with col_p3: p_date = st.date_input("Tanggal Transaksi:", datetime.date.today())
            students = get_master_students(p_class)
            if students:
                with st.form("form_late"):
                    sel_student = st.selectbox("Nama Siswa:", students)
                    late_min = st.number_input("Keterlambatan (Dalam Menit):", min_value=0, step=5, value=15)
                    if st.form_submit_button("💾 Catat Menit Terlambat"):
                        if save_lateness_entry(p_date, p_class, sel_student, late_min, "Guru Piket"):
                            st.success(f"Berhasil mencatat keterlambatan {late_min} menit untuk {sel_student}!")
            else: st.warning("Daftar siswa belum diisi di kelas ini.")
        with tab_flagging:
            st.subheader("🚩 Form Flagging Perilaku Siswa")
            with st.form("form_flagging"):
                f_class = st.selectbox("Kelas Siswa:", classes, key="flag_c")
                f_students = get_master_students(f_class)
                f_student = st.selectbox("Pilih Siswa:", f_students) if f_students else None
                f_type = st.radio("Jenis Flagging:", ["POSITIF", "NEGATIF"], horizontal=True)
                f_category = st.selectbox("Kategori Perilaku:", ["Ketertiban / Kerapihan", "Kedisiplinan Jam Pelajaran", "Prestasi / Kerjasama", "Pelanggaran Tata Tertib", "Bullying / Perkelahian", "Lainnya"])
                f_catatan = st.text_area("Deskripsi Catatan Guru:")
                if st.form_submit_button("🚩 Kirim Flagging Perilaku"):
                    if f_student:
                        success, msg = save_flag_entry(datetime.date.today(), f_class, f_student, f_type, f_category, f_catatan, "Guru Piket")
                        if success: st.success(msg)
                        else: st.warning(msg)

    # 3. GURU BK (DASHBOARD EKSEKUTIF BK TERPRODUKSI)
    elif st.session_state.user_role == "Guru BK":
        st.title("📊 Dashboard Eksekutif Bimbingan Konseling (BK)")
        target_c = st.selectbox("🎯 Pilih Kelas Pantauan Utama BK:", classes, key="bk_target_class")
        tab_rekap_bk, tab_exec_risk, tab_counseling = st.tabs(["📊 Rekap & Agregasi Kedisiplinan", "🎯 Risk Scoring & Grafik Tren AI", "📝 Modul Pemanggilan & Konseling BK"])
        
        with tab_rekap_bk:
            st.subheader(f"📑 Rekap Harian, Bulanan & Flagging Guru - Kelas {target_c}")
            df_lateness_all = fetch_lateness_logs()
            df_flags_all = fetch_flags()
            c_late = df_lateness_all[df_lateness_all['Kelas'] == target_c] if not df_lateness_all.empty and 'Kelas' in df_lateness_all.columns else pd.DataFrame()
            c_flags = df_flags_all[df_flags_all['Kelas'] == target_c] if not df_flags_all.empty and 'Kelas' in df_flags_all.columns else pd.DataFrame()
            col_bk1, col_bk2, col_bk3 = st.columns(3)
            col_bk1.metric("⏱️ Total Menit Terlambat Kelas", f"{c_late['Menit Terlambat'].astype(int).sum() if not c_late.empty else 0} Menit")
            col_bk2.metric("🚩 Catatan Perilaku Negatif", f"{len(c_flags[c_flags['Tipe'] == 'NEGATIF']) if not c_flags.empty else 0} Kasus")
            col_bk3.metric("✨ Catatan Perilaku Positif", f"{len(c_flags[c_flags['Tipe'] == 'POSITIF']) if not c_flags.empty else 0} Apresiasi")
            st.write("---")
            col_df_l, col_df_f = st.columns(2)
            with col_df_l:
                st.markdown("##### ⏱️ Riwayat Keterlambatan (Piket)")
                if not c_late.empty: st.dataframe(c_late.sort_values(by='Tanggal', ascending=False), use_container_width=True, hide_index=True)
                else: st.info("Belum ada catatan keterlambatan untuk kelas ini.")
            with col_df_f:
                st.markdown("##### 🚩 Riwayat Catatan Perilaku Guru")
                if not c_flags.empty: st.dataframe(c_flags.sort_values(by='Tanggal', ascending=False), use_container_width=True, hide_index=True)
                else: st.info("Belum ada riwayat flagging perilaku dari guru.")

        with tab_exec_risk:
            st.subheader(f"🛡️ Sistem Risk Scoring & Tren Kedisiplinan - Kelas {target_c}")
            if st.button("🔄 Kalkulasi Matriks Risiko & Tren Terbaru", type="primary", key="btn_bk_calc_risk"):
                with st.spinner("Mengkalkulasi tingkat risiko kedisiplinan & tren..."):
                    st.session_state[f"risk_bk_{target_c}"] = calculate_class_risk_table(target_c)
            if f"risk_bk_{target_c}" in st.session_state:
                df_risk = st.session_state[f"risk_bk_{target_c}"]
                if not df_risk.empty:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("🔴 Zona Merah (Bahaya)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA MERAH']))
                    c2.metric("🟡 Zona Kuning (Waspada)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA KUNING']))
                    c3.metric("🟢 Zona Hijau (Aman)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA HIJAU']))
                    st.markdown("##### 📋 Matriks Poin Risiko Kedisiplinan Siswa")
                    st.dataframe(df_risk.sort_values(by='Skor Poin', ascending=False), use_container_width=True, hide_index=True)
                    st.write("---")
                    st.subheader("📈 Grafik Tren Kedisiplinan Kelas")
                    df_lateness_all = fetch_lateness_logs()
                    if not df_lateness_all.empty and 'Kelas' in df_lateness_all.columns:
                        c_late_trend = df_lateness_all[df_lateness_all['Kelas'] == target_c]
                        if not c_late_trend.empty:
                            trend_summary = c_late_trend.groupby('Tanggal')['Menit Terlambat'].astype(int).sum().reset_index()
                            st.bar_chart(trend_summary.set_index('Tanggal'))
                        else: st.caption("ℹ️ Belum ada tren grafik keterlambatan untuk kelas ini.")
                    st.write("---")
                    st.subheader("🤖 Deskripsi Naratif Otomatis (AI Narrative Evaluation)")
                    selected_eval_student = st.selectbox("Pilih Siswa untuk Generasi Laporan AI:", df_risk['Nama Siswa'].tolist(), key="bk_ai_select")
                    if st.button("✨ Generasi Laporan Naratif AI"):
                        s_row = df_risk[df_risk['Nama Siswa'] == selected_eval_student].iloc[0].to_dict()
                        st.markdown(generate_ai_student_narrative(selected_eval_student, s_row))
            else: st.info("Klik tombol di atas untuk memuat analisis risiko dan tren kelas.")

        with tab_counseling:
            st.subheader(f"📝 Modul Pemanggilan & Konseling Siswa - Kelas {target_c}")
            students = get_master_students(target_c)
            counseling_col1, counseling_col2 = st.columns([1, 1])
            with counseling_col1:
                st.markdown("##### ➕ Form Input Wawancara / Sesi Konseling")
                with st.form("form_bk_session"):
                    c_student = st.selectbox("Nama Siswa:", students) if students else None
                    c_date = st.date_input("Tanggal Sesi / Pemanggilan:", datetime.date.today())
                    c_ringkasan = st.text_area("Ringkasan Hasil Wawancara / Keluhan / Pelanggaran:")
                    c_rekomendasi = st.text_area("Rekomendasi Tindakan / Komitmen Siswa:")
                    c_status = st.selectbox("Penandatanganan / Status Penanganan:", ["OPEN", "IN_PROGRESS", "RESOLVED", "ESCALATED"])
                    if st.form_submit_button("💾 Simpan Record Konseling BK", type="primary"):
                        if c_student and c_ringkasan.strip():
                            if save_counseling_log(c_date, target_c, c_student, c_ringkasan, c_rekomendasi, c_status, "Guru BK"):
                                st.success(f"🎉 Catatan konseling untuk {c_student} berhasil tersimpan!")
                                st.rerun()
                        else: st.error("❌ Nama Siswa dan Ringkasan Wawancara wajib diisi!")
            with counseling_col2:
                st.markdown("##### 📑 Riwayat Record Konseling Terdaftar")
                df_counsel = fetch_counseling_logs()
                if not df_counsel.empty and 'Kelas' in df_counsel.columns:
                    c_history = df_counsel[df_counsel['Kelas'] == target_c]
                    if not c_history.empty: st.dataframe(c_history.sort_values(by='Tanggal', ascending=False), use_container_width=True, hide_index=True)
                    else: st.info("Belum ada riwayat konseling untuk kelas ini.")
                else: st.info("Belum ada data konseling tersimpan di database.")

    # 4. KEPALA SEKOLAH (DASHBOARD MAKRO TINGKAT SEKOLAH)
    elif st.session_state.user_role == "Kepala Sekolah":
        st.title("🏛️ Dashboard Makro Kedisiplinan - Kepala Sekolah")
        if st.button("🔄 Muat Data Eksekutif Makro Seluruh Kelas", type="primary"):
            with st.spinner("Mengagregasi data dari seluruh kelas di sekolah..."):
                df_late_all = fetch_lateness_logs()
                df_flags_all = fetch_flags()
                macro_summary, all_red_students = [], []
                for c in classes:
                    c_risk_df = calculate_class_risk_table(c, df_late_all, df_flags_all)
                    red = len(c_risk_df[c_risk_df['Zona Risiko'] == 'ZONA MERAH'])
                    yellow = len(c_risk_df[c_risk_df['Zona Risiko'] == 'ZONA KUNING'])
                    green = len(c_risk_df[c_risk_df['Zona Risiko'] == 'ZONA HIJAU'])
                    red_df = c_risk_df[c_risk_df['Zona Risiko'] == 'ZONA MERAH'].copy()
                    if not red_df.empty:
                        red_df['Kelas'] = c
                        all_red_students.append(red_df)
                    macro_summary.append({'Kelas': c, 'Total Siswa': len(c_risk_df), '🔴 Zona Merah': red, '🟡 Zona Kuning': yellow, '🟢 Zona Hijau': green})
                st.session_state["macro_kepsek"] = pd.DataFrame(macro_summary)
                st.session_state["macro_red_students"] = pd.concat(all_red_students, ignore_index=True) if all_red_students else pd.DataFrame()

        if "macro_kepsek" in st.session_state:
            df_macro = st.session_state["macro_kepsek"]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🔴 Total Siswa Zona Merah", df_macro['🔴 Zona Merah'].sum())
            col2.metric("🟡 Total Siswa Zona Kuning", df_macro['🟡 Zona Kuning'].sum())
            col3.metric("🟢 Total Siswa Zona Hijau", df_macro['🟢 Zona Hijau'].sum())
            col4.metric("🏫 Total Kelas Terpantau", len(df_macro))
            st.write("---")
            st.subheader("📊 Distribusi Risiko Kedisiplinan per Kelas")
            st.dataframe(df_macro, use_container_width=True, hide_index=True)
            st.bar_chart(df_macro.set_index('Kelas')[['🔴 Zona Merah', '🟡 Zona Kuning', '🟢 Zona Hijau']])
            st.write("---")
            st.subheader("⚠️ Daftar Prioritas Siswa Zona Merah (Perlu Atensi Kepsek & BK)")
            if "macro_red_students" in st.session_state and not st.session_state["macro_red_students"].empty:
                df_red = st.session_state["macro_red_students"]
                cols_order = ['Kelas', 'Nama Siswa', 'Skor Poin', 'Alpa (Hari)', 'Terlambat (Menit)', 'Flag Negatif']
                st.dataframe(df_red[cols_order].sort_values(by='Skor Poin', ascending=False), use_container_width=True, hide_index=True)
            else: st.success("🎉 Tidak ada siswa dalam Zona Merah di seluruh kelas!")
        else: st.info("Klik tombol di atas untuk memuat laporan makro tingkat sekolah.")

    # 5. ADMIN SYSTEM (MANAGEMENT HUB)
    elif st.session_state.user_role in ["Admin", "Administrator System"]:
        st.title("🛠️ Pusat Pengaturan Administrator System")
        tab_pass, tab_master_all = st.tabs(["🔐 Kelola Pengguna (CRUD)", "👥 Kelola Data Master Siswa (CRUD & I/O)"])
        
        with tab_pass:
            st.subheader("🔐 Manajemen Akun Pengguna & Akses Hak Masuk")
            passwords = fetch_config_passwords()
            col_add_user, col_edit_user = st.columns([1, 2])
            with col_add_user:
                with st.expander("➕ Tambah Pengguna Baru", expanded=True):
                    with st.form("form_add_user"):
                        new_key = st.text_input("Nama Pengguna / Role Key:")
                        new_pass = st.text_input("Password Baru:", type="password")
                        if st.form_submit_button("➕ Tambah Akun", type="primary"):
                            if not new_key or not new_pass: st.error("❌ Nama pengguna dan password wajib diisi!")
                            elif new_key in passwords: st.warning(f"⚠️ Pengguna '{new_key}' sudah ada.")
                            else:
                                passwords[new_key] = new_pass
                                save_config_passwords(passwords)
                                st.success(f"🎉 Akun '{new_key}' berhasil ditambahkan!")
                                st.rerun()
            with col_edit_user:
                st.markdown("##### 📋 Daftar Akun Pengguna (Edit Password & Hapus)")
                config_df = pd.DataFrame(list(passwords.items()), columns=['Key', 'Password'])
                edited_config = st.data_editor(config_df, num_rows="dynamic", use_container_width=True, key="editor_users")
                if st.button("💾 Simpan Perubahan Pengguna", type="primary"):
                    valid_rows = edited_config.dropna(subset=['Key'])
                    new_pass_dict = {k: v for k, v in dict(zip(valid_rows['Key'].astype(str).str.strip(), valid_rows['Password'].astype(str).str.strip())).items() if k != ""}
                    save_config_passwords(new_pass_dict)
                    st.success("🔒 Data pengguna & password berhasil diperbarui!")
                    st.rerun()

        with tab_master_all:
            st.subheader("👥 Kelola Master Data Siswa Pusat")
            admin_siswa_tab1, admin_siswa_tab2, admin_siswa_tab3 = st.tabs(["📝 Grid Editor Master Siswa", "➕ Single Form Add/Remove", "📦 Export & Import Batch Master"])
            df_all_master = fetch_all_master_df()
            with admin_siswa_tab1:
                st.markdown("##### ✏️ Master Siswa Grid Editor (Seluruh Kelas)")
                edited_master = st.data_editor(df_all_master, num_rows="dynamic", use_container_width=True, key="admin_editor_master")
                if st.button("💾 Simpan Perubahan Master Siswa", type="primary", key="btn_save_all_master"):
                    with st.spinner("Menyimpan seluruh data master ke database..."):
                        save_all_master_df(edited_master)
                    st.success("🎉 Database Master Siswa berhasil diperbarui!")
                    st.rerun()
            with admin_siswa_tab2:
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    with st.expander("➕ Tambah Siswa Baru ke Kelas", expanded=True):
                        with st.form("form_admin_add_siswa"):
                            target_c = st.selectbox("Pilih Kelas Target:", classes, key="adm_add_c")
                            new_s_name = st.text_input("Nama Lengkap Siswa Baru:")
                            if st.form_submit_button("➕ Tambahkan Siswa"):
                                if new_s_name.strip():
                                    current_list = get_master_students(target_c)
                                    if new_s_name.strip() in current_list: st.warning("⚠️ Nama siswa sudah ada di kelas tersebut.")
                                    else:
                                        current_list.append(new_s_name.strip())
                                        save_master_students(target_c, current_list)
                                        st.success(f"🎉 Siswa '{new_s_name}' berhasil ditambahkan ke kelas {target_c}!")
                                        st.rerun()
                                else: st.error("Nama siswa tidak boleh kosong!")
                with col_c2:
                    with st.expander("🗑️ Hapus Siswa dari Kelas", expanded=True):
                        with st.form("form_admin_del_siswa"):
                            target_del_c = st.selectbox("Pilih Kelas Target:", classes, key="adm_del_c")
                            c_students = get_master_students(target_del_c)
                            siswa_to_del = st.selectbox("Pilih Siswa yang Akan Dihapus:", c_students) if c_students else None
                            if st.form_submit_button("🗑️ Hapus Siswa Terpilih", type="secondary"):
                                if siswa_to_del:
                                    updated_list = [s for s in c_students if s != siswa_to_del]
                                    save_master_students(target_del_c, updated_list)
                                    st.success(f"🎉 Siswa '{siswa_to_del}' berhasil dihapus dari kelas {target_del_c}!")
                                    st.rerun()
                                else: st.error("Tidak ada siswa untuk dihapus pada kelas ini.")
            with admin_siswa_tab3:
                st.markdown("##### 📦 Batch Import & Export Data Master")
                exp_col, imp_col = st.columns(2)
                with exp_col:
                    exp_mode = st.radio("Pilih Mode Export:", ["Seluruh Kelas (Full Matrix)", "Per Kelas Spesifik"])
                    if exp_mode == "Seluruh Kelas (Full Matrix)":
                        st.download_button(label="⬇️ Download Full Master Data (CSV)", data=df_all_master.to_csv(index=False).encode('utf-8'), file_name="Master_Siswa_All_Classes.csv", mime="text/csv", type="primary")
                    else:
                        selected_exp_c = st.selectbox("Pilih Kelas yang Diexport:", classes, key="sel_exp_c")
                        df_c_exp = pd.DataFrame(get_master_students(selected_exp_c), columns=["Nama Siswa"])
                        st.download_button(label=f"⬇️ Download Master Kelas {selected_exp_c} (CSV)", data=df_c_exp.to_csv(index=False).encode('utf-8'), file_name=f"Master_Siswa_{selected_exp_c}.csv", mime="text/csv")
                with imp_col:
                    imp_mode = st.radio("Pilih Mode Import:", ["Import per Kelas", "Import Full Matrix (Banyak Kelas)"])
                    if imp_mode == "Import per Kelas":
                        target_imp_c = st.selectbox("Pilih Kelas Target Import:", classes, key="sel_imp_c")
                        up_file_c = st.file_uploader(f"Upload CSV/Excel untuk Kelas {target_imp_c}:", type=["csv", "xlsx"], key="up_c")
                        if up_file_c is not None:
                            try:
                                df_imp = pd.read_csv(up_file_c) if up_file_c.name.endswith(".csv") else pd.read_excel(up_file_c)
                                imp_names = df_imp["Nama Siswa"].dropna().astype(str).str.strip().tolist() if "Nama Siswa" in df_imp.columns else df_imp.iloc[:, 0].dropna().astype(str).str.strip().tolist()
                                imp_names = [n for n in imp_names if n not in ["", "nan", "None"]]
                                if st.button(f"💾 Terapkan Import Kelas {target_imp_c}", type="primary"):
                                    save_master_students(target_imp_c, imp_names)
                                    st.success(f"🎉 Master Siswa Kelas {target_imp_c} berhasil diperbarui!")
                                    st.rerun()
                            except Exception as ex: st.error(f"❌ Error membaca file: {ex}")
                    else:
                        up_file_full = st.file_uploader("Upload CSV/Excel Full Matrix:", type=["csv", "xlsx"], key="up_full")
                        if up_file_full is not None:
                            try:
                                df_imp_full = pd.read_csv(up_file_full) if up_file_full.name.endswith(".csv") else pd.read_excel(up_file_full)
                                st.dataframe(df_imp_full.head(), use_container_width=True)
                                if st.button("💾 Terapkan Import Full Matrix Master Siswa", type="primary"):
                                    save_all_master_df(df_imp_full)
                                    st.success("🎉 Database Master Siswa Seluruh Kelas berhasil diperbarui!")
                                    st.rerun()
                            except Exception as ex: st.error(f"❌ Error membaca file: {ex}")
