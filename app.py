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
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

try:
    client = get_gspread_client()
    sh = client.open_by_key(st.secrets["spreadsheet_id"])
except Exception as e:
    st.error(f"❌ Gagal terhubung ke Database Google Sheets: {e}")
    st.stop()

# --- 2. LAZY FETCHING DENGAN RETRY AUTOMATION ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sheet_with_retry(sheet_name):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ws = sh.worksheet(sheet_name)
            return pd.DataFrame(ws.get_all_records())
        except WorksheetNotFound:
            return pd.DataFrame()
        except APIError as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

# --- 3. MASTER SISWA & CONFIG ---
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
    fetch_sheet_with_retry.clear()

def fetch_config_passwords():
    df = fetch_sheet_with_retry("CONFIG")
    if not df.empty and 'Key' in df.columns and 'Password' in df.columns:
        return dict(zip(df['Key'], df['Password']))
    
    keys = ['Admin', 'Guru Piket', 'Guru BK', 'Kepala Sekolah'] + classes
    default_passwords = ['admin123', 'piket123', 'bk123', 'kepsek123'] + [f"{c.lower()}123" for c in classes]
    return dict(zip(keys, default_passwords))

def save_config_passwords(password_dict):
    ws = sh.worksheet("CONFIG")
    ws.clear()
    df = pd.DataFrame(list(password_dict.items()), columns=['Key', 'Password'])
    ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())
    fetch_sheet_with_retry.clear()

# --- 4. LOG KETERLAMBATAN, FLAGGING & KONSELING ---
def fetch_lateness_logs():
    return fetch_sheet_with_retry("LOG_KETERLAMBATAN")

def save_lateness_entry(tanggal, kelas, nama, menit, pencatat):
    try:
        try:
            ws = sh.worksheet("LOG_KETERLAMBATAN")
        except WorksheetNotFound:
            ws = sh.add_worksheet("LOG_KETERLAMBATAN", rows="1000", cols="10")
            ws.append_row(['Tanggal', 'Kelas', 'Nama Siswa', 'Menit Terlambat', 'Pencatat'])
        ws.append_row([str(tanggal), kelas, nama, int(menit), pencatat])
        fetch_sheet_with_retry.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan keterlambatan: {e}")
        return False

def fetch_flags():
    return fetch_sheet_with_retry("FLAGS_PERILAKU")

def save_flag_entry(tanggal, kelas, nama, tipe, kategori, catatan, pencatat):
    dt = datetime.datetime.strptime(str(tanggal), "%Y-%m-%d").date() if isinstance(tanggal, str) else tanggal
    year_week = f"{dt.year}-{dt.isocalendar()[1]}"
    
    df_flags = fetch_flags()
    if not df_flags.empty and 'Nama Siswa' in df_flags.columns and 'TahunMinggu' in df_flags.columns:
        existing = df_flags[(df_flags['Nama Siswa'] == nama) & (df_flags['TahunMinggu'] == year_week)]
        if len(existing) > 0:
            return False, f"⚠️ Siswa '{nama}' sudah diberikan flagging pada minggu ini ({year_week})."

    try:
        try:
            ws = sh.worksheet("FLAGS_PERILAKU")
        except WorksheetNotFound:
            ws = sh.add_worksheet("FLAGS_PERILAKU", rows="1000", cols="10")
            ws.append_row(['Tanggal', 'TahunMinggu', 'Kelas', 'Nama Siswa', 'Tipe', 'Kategori', 'Catatan', 'Pencatat'])
        ws.append_row([str(dt), year_week, kelas, nama, tipe, kategori, catatan, pencatat])
        fetch_sheet_with_retry.clear()
        return True, "✅ Flagging perilaku berhasil dicatat!"
    except Exception as e:
        return False, f"Gagal menyimpan flag: {e}"

def fetch_counseling_logs():
    return fetch_sheet_with_retry("KONSELING_BK")

def save_counseling_log(tanggal, kelas, nama, ringkasan, rekomendasi, status, konselor):
    try:
        try:
            ws = sh.worksheet("KONSELING_BK")
        except WorksheetNotFound:
            ws = sh.add_worksheet("KONSELING_BK", rows="500", cols="10")
            ws.append_row(['ID', 'Tanggal', 'Kelas', 'Nama Siswa', 'Ringkasan', 'Rekomendasi', 'Status', 'Konselor'])
        
        c_id = f"BK-{int(datetime.datetime.now().timestamp())}"
        ws.append_row([c_id, str(tanggal), kelas, nama, ringkasan, rekomendasi, status, konselor])
        fetch_sheet_with_retry.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan catatan konseling: {e}")
        return False

# --- 5. DATA ABSENSI BULANAN & GRID EDITOR (DARI APP.PY) ---
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
    try:
        ws = sh.worksheet(sheet_name)
    except Exception:
        ws = sh.add_worksheet(title=sheet_name, rows="100", cols="40")
        
    ws.clear()
    df = df.fillna('')
    df = df.astype(str)
    data_to_write = [df.columns.values.tolist()] + df.values.tolist()
    ws.update(range_name='A1', values=data_to_write)
    fetch_sheet_with_retry.clear()

def get_calendar_config(selected_month):
    year = get_year_for_month(selected_month)
    month_num = month_map[selected_month]
    _, max_days = calendar.monthrange(year, month_num)
    days_id = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Mig"]
    
    disabled_cols = []
    col_config = {}
    monthly_holidays = []
    
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

def generate_full_report(df):
    df_report = df.copy()
    s_list, i_list, a_list, h_list = [], [], [], []
    pct_h_list, pct_i_list, pct_a_list, pct_s_list = [], [], [], []
    
    active_date_cols = []
    for col in date_cols:
        vals = [str(v).strip().upper() for v in df_report[col].values]
        if any(v in ['H', 'HADIR', 'S', 'SAKIT', 'I', 'IJIN', 'IZIN', 'A', 'ALPHA', 'ALPA', '.', 'V'] for v in vals):
            active_date_cols.append(col)

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

# --- 6. RISK SCORING ENGINE ---
def calculate_risk_score(student_name, kelas, df_late=None, df_flags=None):
    total_alpa = 0
    for m in months:
        df_m = fetch_attendance_data_from_cache(kelas, m)
        rep = generate_full_report(df_m)
        r = rep[rep['Nama Siswa'] == student_name]
        if not r.empty:
            total_alpa += int(r.iloc[0]['A'])
            
    if df_late is None: df_late = fetch_lateness_logs()
    total_late_min = 0
    if not df_late.empty and 'Nama Siswa' in df_late.columns and 'Kelas' in df_late.columns:
        s_late = df_late[(df_late['Nama Siswa'] == student_name) & (df_late['Kelas'] == kelas)]
        total_late_min = s_late['Menit Terlambat'].astype(int).sum() if not s_late.empty else 0
        
    if df_flags is None: df_flags = fetch_flags()
    neg_flags, pos_flags = 0, 0
    if not df_flags.empty and 'Nama Siswa' in df_flags.columns and 'Kelas' in df_flags.columns:
        s_flags = df_flags[(df_flags['Nama Siswa'] == student_name) & (df_flags['Kelas'] == kelas)]
        if not s_flags.empty:
            neg_flags = len(s_flags[s_flags['Tipe'] == 'NEGATIF'])
            pos_flags = len(s_flags[s_flags['Tipe'] == 'POSITIF'])
            
    score = max(0, (total_alpa * 15) + (total_late_min // 5) + (neg_flags * 10) - (pos_flags * 5))
    
    if score <= 20: zone, badge = "ZONA HIJAU", "🟢 Hijau (Aman)"
    elif score <= 50: zone, badge = "ZONA KUNING", "🟡 Kuning (Waspada)"
    else: zone, badge = "ZONA MERAH", "🔴 Merah (Bahaya)"
        
    return {
        'score': score, 'zone': zone, 'badge': badge,
        'alpa': total_alpa, 'late_min': total_late_min,
        'neg_flags': neg_flags, 'pos_flags': pos_flags
    }

def generate_ai_student_narrative(student_name, risk_data, flag_history):
    narrative = f"### 🤖 Evaluasi Naratif AI untuk: {student_name}\n\n"
    narrative += f"**Status Risiko:** {risk_data['badge']} (Skor Total Kedisiplinan: **{risk_data['score']} Poin**)\n\n"
    
    if risk_data['alpa'] == 0 and risk_data['late_min'] == 0:
        narrative += "• **Presensi & Ketepatan Waktu:** Siswa menunjukkan tingkat kedisiplinan yang sangat baik tanpa riwayat Alpa maupun keterlambatan.\n"
    else:
        narrative += f"• **Presensi & Ketepatan Waktu:** Terdeteksi akumulasi **{risk_data['alpa']} hari Alpa** dan akumulasi keterlambatan **{risk_data['late_min']} menit**.\n"
        
    narrative += f"• **Catatan Perilaku Guru:** Tercatat {risk_data['pos_flags']} indikator positif dan {risk_data['neg_flags']} catatan indikator negatif.\n"
    
    if risk_data['zone'] == "ZONA MERAH":
        narrative += "\n⚠️ **Rekomendasi Tindakan (Prioritas BK):** Siswa berada dalam Zona Merah. Disarankan untuk *segera melayangkan Surat Pemanggilan Orang Tua (SP)*."
    elif risk_data['zone'] == "ZONA KUNING":
        narrative += "\n💡 **Rekomendasi Tindakan (Wali Kelas):** Siswa dalam Zona Waspada. Wali Kelas disarankan melakukan dialog personal."
    else:
        narrative += "\n✨ **Rekomendasi Tindakan:** Pertahankan motivasi belajar siswa dan berikan apresiasi atas kedisiplinan yang terjaga."
        
    return narrative

# --- 7. OTENTIKASI & USER INTERFACE ---
passwords = fetch_config_passwords()

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

if not st.session_state.logged_in:
    st.title("🔐 Login Sistem Keamanan Absensi & Kedisiplinan Siswa")
    st.caption("GovTech Education Platform - Integrated Early Warning System")
    
    with st.form("login_form"):
        role = st.selectbox("Pilih Hak Akses Peran:", ["Sekretaris / Wali Kelas", "Guru Piket / Pelajaran", "Guru BK", "Kepala Sekolah", "Administrator System"])
        target_class = st.selectbox("Pilih Kelas Anda:", classes) if role == "Sekretaris / Wali Kelas" else None
        password_input = st.text_input("Masukkan Password Akun:", type="password")
        
        if st.form_submit_button("🔑 Masuk / Otentikasi"):
            if role == "Sekretaris / Wali Kelas" and password_input == passwords.get(target_class):
                st.session_state.logged_in, st.session_state.user_role, st.session_state.assigned_class = True, "Sekretaris / Wali Kelas", target_class
                st.rerun()
            elif role == "Guru Piket / Pelajaran" and password_input == passwords.get("Guru Piket"):
                st.session_state.logged_in, st.session_state.user_role = True, "Guru Piket"
                st.rerun()
            elif role == "Guru BK" and password_input == passwords.get("Guru BK", "bk123"):
                st.session_state.logged_in, st.session_state.user_role = True, "Guru BK"
                st.rerun()
            elif role == "Kepala Sekolah" and password_input == passwords.get("Kepala Sekolah", "kepsek123"):
                st.session_state.logged_in, st.session_state.user_role = True, "Kepala Sekolah"
                st.rerun()
            elif role == "Administrator System" and password_input == passwords.get("Admin"):
                st.session_state.logged_in, st.session_state.user_role = True, "Admin"
                st.rerun()
            else:
                st.error("❌ Password atau Hak Akses Salah!")

else:
    # 1. SEKRETARIS / WALI KELAS (MENGGUNAKAN SISTEM GRID DATA EDITOR APP.PY)
    if st.session_state.user_role == "Sekretaris / Wali Kelas":
        my_class = st.session_state.assigned_class
        st.title(f"🏫 Ruang Kerja Sekretaris / Wali Kelas {my_class}")
        
        tab_absen, tab_ganjil, tab_genap, tab_rekap, tab_risk, tab_nama = st.tabs([
            "📝 Isi Absensi Bulanan (Grid)", 
            "🍂 Rekap Semester Ganjil",
            "🌸 Rekap Semester Genap",
            "📊 Rekap 1 Tahun",
            "🎯 Matriks Risk Scoring & AI",
            "👥 Kelola Master Siswa"
        ])
        
        # TAB 1: ISI ABSENSI BULANAN (GRID EDITOR APP.PY)
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
            st.dataframe(
                full_report[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '% Hadir', '% Izin', '% Alpha', '% Sakit']], 
                use_container_width=True
            )

        # TAB 2: REKAP GANJIL
        with tab_ganjil:
            st.subheader(f"🍂 Rekapitulasi Semester Ganjil (Juli - Desember) - Kelas {my_class}")
            if st.button("🔄 Muat / Perbarui Rekap Semester Ganjil", type="primary", key="btn_ganjil_sk"):
                with st.spinner("Kalkulasi Semester Ganjil..."):
                    st.session_state[f"ganjil_{my_class}"] = calculate_period_recap(my_class, ganjil_months)
                st.success("🎉 Rekap Semester Ganjil diperbarui!")
                
            if f"ganjil_{my_class}" in st.session_state:
                st.dataframe(st.session_state[f"ganjil_{my_class}"], use_container_width=True, hide_index=True)

        # TAB 3: REKAP GENAP
        with tab_genap:
            st.subheader(f"🌸 Rekapitulasi Semester Genap (Januari - Juni) - Kelas {my_class}")
            if st.button("🔄 Muat / Perbarui Rekap Semester Genap", type="primary", key="btn_genap_sk"):
                with st.spinner("Kalkulasi Semester Genap..."):
                    st.session_state[f"genap_{my_class}"] = calculate_period_recap(my_class, genap_months)
                st.success("🎉 Rekap Semester Genap diperbarui!")
                
            if f"genap_{my_class}" in st.session_state:
                st.dataframe(st.session_state[f"genap_{my_class}"], use_container_width=True, hide_index=True)

        # TAB 4: REKAP TAHUNAN
        with tab_rekap:
            st.subheader(f"📊 Rekapitulasi Akumulasi 1 Tahun - Kelas {my_class}")
            if st.button("🔄 Muat / Perbarui Rekap 1 Tahun", type="primary", key="btn_yearly_sk"):
                with st.spinner("Kalkulasi 12 Bulan..."):
                    st.session_state[f"yearly_{my_class}"] = calculate_period_recap(my_class, months)
                st.success("🎉 Rekap 1 Tahun diperbarui!")
                
            if f"yearly_{my_class}" in st.session_state:
                st.dataframe(st.session_state[f"yearly_{my_class}"], use_container_width=True, hide_index=True)

        # TAB 5: RISK SCORING & AI EVALUATION (EARLY WARNING SYSTEM)
        with tab_risk:
            st.subheader(f"🛡️ Analisis Risiko Kedisiplinan Siswa - Kelas {my_class}")
            students = get_master_students(my_class)
            df_late_all = fetch_lateness_logs()
            df_flags_all = fetch_flags()
            
            risk_table = []
            for s in students:
                r_data = calculate_risk_score(s, my_class, df_late_all, df_flags_all)
                risk_table.append({
                    'Nama Siswa': s, 'Zona Risiko': r_data['zone'], 'Skor Poin': r_data['score'],
                    'Alpa (Hari)': r_data['alpa'], 'Terlambat (Menit)': r_data['late_min'],
                    'Flag Negatif': r_data['neg_flags'], 'Flag Positif': r_data['pos_flags']
                })
            
            df_risk = pd.DataFrame(risk_table)
            if not df_risk.empty:
                col1, col2, col3 = st.columns(3)
                col1.metric("🔴 Zona Merah (Bahaya)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA MERAH']))
                col2.metric("🟡 Zona Kuning (Waspada)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA KUNING']))
                col3.metric("🟢 Zona Hijau (Aman)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA HIJAU']))
                
                st.dataframe(df_risk.sort_values(by='Skor Poin', ascending=False), use_container_width=True)
                
                st.write("---")
                st.subheader("🤖 AI Narrative Evaluation Generator")
                selected_eval_student = st.selectbox("Pilih Siswa untuk Generasi Evaluasi AI:", students, key="ai_eval_sk")
                
                if st.button("✨ Generasi Deskripsi Naratif AI"):
                    r_info = calculate_risk_score(selected_eval_student, my_class, df_late_all, df_flags_all)
                    flags = df_flags_all[df_flags_all['Nama Siswa'] == selected_eval_student] if not df_flags_all.empty and 'Nama Siswa' in df_flags_all.columns else pd.DataFrame()
                    narrative_text = generate_ai_student_narrative(selected_eval_student, r_info, flags)
                    st.markdown(narrative_text)
            else:
                st.info("Belum ada data siswa di kelas ini.")

        # TAB 6: KELOLA MASTER SISWA & IMPORT/EXPORT
        with tab_nama:
            st.subheader(f"👥 Pengaturan Daftar Siswa Kelas {my_class}")
            with st.expander("📥 📤 Import / Export Data Master Siswa (CSV / Excel)", expanded=False):
                col_exp, col_imp = st.columns(2)
                with col_exp:
                    current_masters_list = get_master_students(my_class)
                    df_export = pd.DataFrame(current_masters_list, columns=["Nama Siswa"])
                    st.download_button(
                        label=f"⬇️ Download CSV Master Kelas {my_class}",
                        data=df_export.to_csv(index=False).encode('utf-8'),
                        file_name=f"Master_Siswa_{my_class}.csv",
                        mime="text/csv"
                    )
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
            edited_masters = st.data_editor(
                pd.DataFrame(current_masters, columns=["Nama Siswa"]),
                num_rows="dynamic",
                use_container_width=True,
                key=f"master_edit_{my_class}"
            )
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
            else:
                st.warning("Daftar siswa belum diisi di kelas ini.")
                
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

    # 3. GURU BK
    elif st.session_state.user_role == "Guru BK":
        st.title("📊 Dashboard Eksekutif Bimbingan Konseling (BK)")
        target_c = st.selectbox("Pilih Kelas Pantauan BK:", classes)
        
        tab_exec_risk, tab_counseling = st.tabs(["🎯 Matriks Risk Scoring & AI Evaluation", "📝 Modul Pemanggilan / Konseling BK"])
        
        with tab_exec_risk:
            st.subheader(f"🛡️ Analisis Risiko Kedisiplinan - Kelas {target_c}")
            students = get_master_students(target_c)
            df_late_all = fetch_lateness_logs()
            df_flags_all = fetch_flags()
            
            risk_table = []
            for s in students:
                r_data = calculate_risk_score(s, target_c, df_late_all, df_flags_all)
                risk_table.append({
                    'Nama Siswa': s, 'Zona Risiko': r_data['zone'], 'Skor Poin': r_data['score'],
                    'Alpa (Hari)': r_data['alpa'], 'Terlambat (Menit)': r_data['late_min'],
                    'Flag Negatif': r_data['neg_flags'], 'Flag Positif': r_data['pos_flags']
                })
            
            df_risk = pd.DataFrame(risk_table)
            if not df_risk.empty:
                col1, col2, col3 = st.columns(3)
                col1.metric("🔴 Zona Merah (Bahaya)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA MERAH']))
                col2.metric("🟡 Zona Kuning (Waspada)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA KUNING']))
                col3.metric("🟢 Zona Hijau (Aman)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA HIJAU']))
                
                st.dataframe(df_risk.sort_values(by='Skor Poin', ascending=False), use_container_width=True)
                
                st.write("---")
                st.subheader("🤖 AI Narrative Evaluation Generator")
                selected_eval_student = st.selectbox("Pilih Siswa untuk Generasi Evaluasi AI:", students)
                
                if st.button("✨ Generasi Deskripsi Naratif AI"):
                    r_info = calculate_risk_score(selected_eval_student, target_c, df_late_all, df_flags_all)
                    flags = df_flags_all[df_flags_all['Nama Siswa'] == selected_eval_student] if not df_flags_all.empty and 'Nama Siswa' in df_flags_all.columns else pd.DataFrame()
                    narrative_text = generate_ai_student_narrative(selected_eval_student, r_info, flags)
                    st.markdown(narrative_text)

        with tab_counseling:
            st.subheader("📝 Modul Konseling & Tindak Lanjut")
            with st.form("form_bk"):
                c_student = st.selectbox("Nama Siswa:", students) if students else None
                c_date = st.date_input("Tanggal Konseling:", datetime.date.today())
                c_ringkasan = st.text_area("Ringkasan Hasil Wawancara / Sesi Konseling:")
                c_rekomendasi = st.text_area("Rekomendasi Tindakan / Kesepakatan:")
                c_status = st.selectbox("Status Penanganan:", ["OPEN", "IN_PROGRESS", "RESOLVED", "ESCALATED"])
                
                if st.form_submit_button("💾 Simpan Catatan Konseling"):
                    if c_student:
                        if save_counseling_log(c_date, target_c, c_student, c_ringkasan, c_rekomendasi, c_status, "Guru BK"):
                            st.success("Catatan konseling berhasil disimpan!")

    # 4. KEPALA SEKOLAH
    elif st.session_state.user_role == "Kepala Sekolah":
        st.title("🏛️ Dashboard Makro Kedisiplinan - Kepala Sekolah")
        df_late_all = fetch_lateness_logs()
        df_flags_all = fetch_flags()
        
        macro_summary = []
        for c in classes:
            st_list = get_master_students(c)
            red, yellow, green = 0, 0, 0
            for s in st_list:
                z = calculate_risk_score(s, c, df_late_all, df_flags_all)['zone']
                if z == "ZONA MERAH": red += 1
                elif z == "ZONA KUNING": yellow += 1
                else: green += 1
            macro_summary.append({'Kelas': c, 'Total Siswa': len(st_list), '🔴 Zona Merah': red, '🟡 Zona Kuning': yellow, '🟢 Zona Hijau': green})
            
        df_macro = pd.DataFrame(macro_summary)
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Siswa Zona Merah", df_macro['🔴 Zona Merah'].sum())
        col2.metric("Total Siswa Zona Kuning", df_macro['🟡 Zona Kuning'].sum())
        col3.metric("Total Siswa Zona Hijau", df_macro['🟢 Zona Hijau'].sum())
        
        st.subheader("📊 Distribusi Risiko per Kelas")
        st.dataframe(df_macro, use_container_width=True)
        st.bar_chart(df_macro.set_index('Kelas')[['🔴 Zona Merah', '🟡 Zona Kuning', '🟢 Zona Hijau']])

    # 5. ADMIN SYSTEM
    elif st.session_state.user_role == "Admin":
        st.title("🛠️ Pusat Pengaturan Administrator")
        tab_pass, tab_master_all = st.tabs(["🔐 Kelola Password", "👥 Kelola Database Master Pusat"])
        
        with tab_pass:
            config_df = pd.DataFrame(list(passwords.items()), columns=['Key', 'Password'])
            edited_config = st.data_editor(config_df, disabled=['Key'], use_container_width=True)
            if st.button("💾 Simpan Password Baru", type="primary"):
                save_config_passwords(dict(zip(edited_config['Key'], edited_config['Password'])))
                st.success("🔒 Password berhasil diperbarui!")
                st.rerun()
                
        with tab_master_all:
            st.dataframe(fetch_all_master_df(), use_container_width=True)
