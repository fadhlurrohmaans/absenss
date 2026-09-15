import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
import datetime
import calendar
import time

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
    datetime.date(2026, 8, 17): "Proklamasi Kemerdekaan RI",
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

st.set_page_config(layout="wide", page_title="Sistem Early Warning Kedisiplinan Siswa - GovTech", page_icon="🏫")

st.markdown("""
    <style>
    div[data-testid="stDataFrame"] { -webkit-overflow-scrolling: touch; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

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
    st.error(f"❌ Gagal terhubung ke Database Google Sheets: {e}")
    st.stop()

# --- 2. LAZY FETCHING DENGAN CACHING ---
@st.cache_data(ttl=1800, show_spinner=False)
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

def fetch_config_passwords():
    df = fetch_sheet_with_retry("CONFIG")
    if not df.empty and 'Key' in df.columns and 'Password' in df.columns:
        return dict(zip(df['Key'], df['Password']))
    
    keys = ['Admin', 'Guru Piket', 'Guru BK', 'Kepala Sekolah'] + classes
    default_passwords = ['admin123', 'piket123', 'bk123', 'kepsek123'] + [f"{c.lower()}123" for c in classes]
    return dict(zip(keys, default_passwords))

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

# --- 5. DATA ABSENSI BULANAN & INPUT SEKRETARIS ---
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

def save_daily_attendance_batch(kelas, month, day_number, attendance_map):
    sheet_name = f"{kelas}_{month}"
    target_col = f"Tgl {day_number}"
    try:
        try:
            ws = sh.worksheet(sheet_name)
            df_curr = pd.DataFrame(ws.get_all_records())
        except WorksheetNotFound:
            ws = sh.add_worksheet(sheet_name, rows="200", cols="35")
            df_curr = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        
        students = get_master_students(kelas)
        if df_curr.empty or 'Nama Siswa' not in df_curr.columns:
            df_curr = pd.DataFrame({'Nama Siswa': students})
            for col in date_cols:
                df_curr[col] = ''
                
        for s in students:
            if s not in df_curr['Nama Siswa'].values:
                new_row = {c: '' for c in df_curr.columns}
                new_row['Nama Siswa'] = s
                df_curr = pd.concat([df_curr, pd.DataFrame([new_row])], ignore_index=True)
                
            val = attendance_map.get(s, 'H')
            df_curr.loc[df_curr['Nama Siswa'] == s, target_col] = val

        ws.clear()
        ws.update([df_curr.columns.values.tolist()] + df_curr.fillna('').values.tolist())
        fetch_sheet_with_retry.clear()
        return True, "✅ Absensi harian kelas berhasil diperbarui!"
    except Exception as e:
        return False, f"❌ Gagal memperbarui absensi: {e}"

def generate_full_report(df):
    df_report = df.copy()
    s_list, i_list, a_list, h_list = [], [], [], []
    for _, row in df_report.iterrows():
        s, i, a, h = 0, 0, 0, 0
        for col in date_cols:
            val = str(row[col]).strip().upper()
            if val in ['S', 'SAKIT']: s += 1
            elif val in ['I', 'IJIN', 'IZIN']: i += 1
            elif val in ['A', 'ALPHA', 'ALPA']: a += 1
            elif val in ['H', 'HADIR', '.', 'V']: h += 1
        s_list.append(s); i_list.append(i); a_list.append(a); h_list.append(h)
    df_report['S'], df_report['I'], df_report['A'], df_report['Hadir'] = s_list, i_list, a_list, h_list
    return df_report

# --- 6. OPTIMIZED RISK SCORING ENGINE ---
@st.cache_data(ttl=600, show_spinner=False)
def compute_class_risk_df(kelas):
    """Menghitung risk score satu kelas sekaligus (di-cache untuk mempercepat KepSek dashboard)"""
    students = get_master_students(kelas)
    df_late_all = fetch_lateness_logs()
    df_flags_all = fetch_flags()
    
    monthly_reports = {}
    for m in months:
        monthly_reports[m] = generate_full_report(fetch_attendance_data_from_cache(kelas, m))
        
    risk_rows = []
    for s in students:
        total_alpa = 0
        for m in months:
            rep = monthly_reports[m]
            r = rep[rep['Nama Siswa'] == s]
            if not r.empty:
                total_alpa += int(r.iloc[0]['A'])
                
        total_late_min = 0
        if not df_late_all.empty and 'Nama Siswa' in df_late_all.columns and 'Kelas' in df_late_all.columns:
            s_late = df_late_all[(df_late_all['Nama Siswa'] == s) & (df_late_all['Kelas'] == kelas)]
            total_late_min = s_late['Menit Terlambat'].astype(int).sum() if not s_late.empty else 0
            
        neg_flags, pos_flags = 0, 0
        if not df_flags_all.empty and 'Nama Siswa' in df_flags_all.columns and 'Kelas' in df_flags_all.columns:
            s_flags = df_flags_all[(df_flags_all['Nama Siswa'] == s) & (df_flags_all['Kelas'] == kelas)]
            if not s_flags.empty:
                neg_flags = len(s_flags[s_flags['Tipe'] == 'NEGATIF'])
                pos_flags = len(s_flags[s_flags['Tipe'] == 'POSITIF'])
                
        score = max(0, (total_alpa * 15) + (total_late_min // 5) + (neg_flags * 10) - (pos_flags * 5))
        
        if score <= 20: zone, badge = "ZONA HIJAU", "🟢 Hijau (Aman)"
        elif score <= 50: zone, badge = "ZONA KUNING", "🟡 Kuning (Waspada)"
        else: zone, badge = "ZONA MERAH", "🔴 Merah (Bahaya)"
            
        risk_rows.append({
            'Nama Siswa': s, 'Zona Risiko': zone, 'Badge': badge,
            'Skor Poin': score, 'Alpa (Hari)': total_alpa,
            'Terlambat (Menit)': total_late_min,
            'Flag Negatif': neg_flags, 'Flag Positif': pos_flags
        })
    return pd.DataFrame(risk_rows)

def generate_ai_student_narrative(student_name, risk_row):
    narrative = f"### 🤖 Evaluasi Naratif AI untuk: {student_name}\n\n"
    narrative += f"**Status Risiko:** {risk_row['Badge']} (Skor Total Kedisiplinan: **{risk_row['Skor Poin']} Poin**)\n\n"
    
    if risk_row['Alpa (Hari)'] == 0 and risk_row['Terlambat (Menit)'] == 0:
        narrative += "• **Presensi & Ketepatan Waktu:** Siswa menunjukkan tingkat kedisiplinan yang sangat baik tanpa riwayat Alpa maupun keterlambatan.\n"
    else:
        narrative += f"• **Presensi & Ketepatan Waktu:** Terdeteksi akumulasi **{risk_row['Alpa (Hari)']} hari Alpa** dan akumulasi keterlambatan **{risk_row['Terlambat (Menit)']} menit**.\n"
        
    narrative += f"• **Catatan Perilaku Guru:** Tercatat {risk_row['Flag Positif']} indikator positif dan {risk_row['Flag Negatif']} catatan indikator negatif.\n"
    
    if risk_row['Zona Risiko'] == "ZONA MERAH":
        narrative += "\n⚠️ **Rekomendasi Tindakan (Prioritas BK):** Siswa berada dalam Zona Merah. Disarankan untuk *segera melayangkan Surat Pemanggilan Orang Tua (SP)*."
    elif risk_row['Zona Risiko'] == "ZONA KUNING":
        narrative += "\n💡 **Rekomendasi Tindakan (Wali Kelas):** Siswa dalam Zona Waspada. Wali Kelas disarankan melakukan dialog personal."
    else:
        narrative += "\n✨ **Rekomendasi Tindakan:** Pertahankan motivasi belajar siswa dan berikan apresiasi atas kedisiplinan yang terjaga."
        
    return narrative

# --- 7. OTENTIKASI & USER INTERFACE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'assigned_class' not in st.session_state: st.session_state.assigned_class = None

st.sidebar.title("🏢 Early Warning System")

if st.session_state.logged_in:
    st.sidebar.success(f"Masuk sebagai:\n**{st.session_state.user_role}** " + (f"({st.session_state.assigned_class})" if st.session_state.assigned_class else ""))
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.assigned_class = None
        st.rerun()

if not st.session_state.logged_in:
    st.title("🔐 Login Sistem Kedisiplinan Siswa")
    st.caption("GovTech Education Platform - Early Warning Architecture")
    
    passwords = fetch_config_passwords()
    
    tab_op, tab_mgmt = st.tabs(["🏫 Operasional (Sekretaris, Wali Kelas, Piket)", "🏛️ Manajemen (BK, KepSek, Admin)"])
    
    with tab_op:
        st.subheader("Akses Tim Operasional Kelas & Piket")
        role_op = st.selectbox("Pilih Hak Akses Peran Operasional:", ["Sekretaris Kelas", "Wali Kelas", "Guru Piket / Pelajaran"])
        
        with st.form("form_login_op"):
            if role_op == "Sekretaris Kelas":
                user_input = st.text_input("Username Sekretaris (contoh: siswa7f, siswa8a):")
                pass_input = st.text_input("Password (contoh: 7f123, 8a123):", type="password")
            elif role_op == "Wali Kelas":
                target_c = st.selectbox("Pilih Kelas Anda:", classes, key="wk_class")
                pass_input = st.text_input("Password Wali Kelas:", type="password")
            else: # Guru Piket
                pass_input = st.text_input("Password Guru Piket:", type="password")
                
            if st.form_submit_button("🔑 Masuk Operasional"):
                if role_op == "Sekretaris Kelas":
                    clean_u = user_input.strip().lower()
                    if clean_u.startswith("siswa") and clean_u.replace("siswa", "").upper() in classes:
                        c_code = clean_u.replace("siswa", "").upper()
                        expected_pass = f"{c_code.lower()}123"
                        if pass_input == expected_pass:
                            st.session_state.logged_in, st.session_state.user_role, st.session_state.assigned_class = True, "Sekretaris Kelas", c_code
                            st.rerun()
                        else: st.error("❌ Password Sekretaris Salah!")
                    else: st.error("❌ Username Sekretaris tidak valid! Format: siswa[kelas] (contoh: siswa7f)")
                elif role_op == "Wali Kelas":
                    if pass_input == passwords.get(target_c, f"{target_c.lower()}123"):
                        st.session_state.logged_in, st.session_state.user_role, st.session_state.assigned_class = True, "Wali Kelas", target_c
                        st.rerun()
                    else: st.error("❌ Password Wali Kelas Salah!")
                elif role_op == "Guru Piket / Pelajaran":
                    if pass_input == passwords.get("Guru Piket", "piket123"):
                        st.session_state.logged_in, st.session_state.user_role = True, "Guru Piket"
                        st.rerun()
                    else: st.error("❌ Password Guru Piket Salah!")

    with tab_mgmt:
        st.subheader("Akses Manajemen & Pengelola Sistem")
        role_mgmt = st.selectbox("Pilih Hak Akses Peran Manajemen:", ["Guru BK", "Kepala Sekolah", "Administrator System"])
        
        with st.form("form_login_mgmt"):
            pass_mgmt = st.text_input("Masukkan Password Akun:", type="password")
            
            if st.form_submit_button("🔑 Masuk Manajemen"):
                if role_mgmt == "Guru BK" and pass_mgmt == passwords.get("Guru BK", "bk123"):
                    st.session_state.logged_in, st.session_state.user_role = True, "Guru BK"
                    st.rerun()
                elif role_mgmt == "Kepala Sekolah" and pass_mgmt == passwords.get("Kepala Sekolah", "kepsek123"):
                    st.session_state.logged_in, st.session_state.user_role = True, "Kepala Sekolah"
                    st.rerun()
                elif role_mgmt == "Administrator System" and pass_mgmt == passwords.get("Admin", "admin123"):
                    st.session_state.logged_in, st.session_state.user_role = True, "Admin"
                    st.rerun()
                else:
                    st.error("❌ Password Manajemen Salah!")

else:
    # 1. SEKRETARIS KELAS
    if st.session_state.user_role == "Sekretaris Kelas":
        sec_class = st.session_state.assigned_class
        st.title(f"✏️ Input Absensi Harian - Kelas {sec_class}")
        st.caption("Modul Khusus Sekretaris Kelas untuk Penginputan Kehadiran Siswa")
        
        col_s1, col_s2 = st.columns(2)
        with col_s1: s_date = st.date_input("Tanggal Absensi:", datetime.date.today())
        with col_s2:
            s_month_idx = s_date.month
            # Map Python month number to academic calendar month name
            reverse_month_map = {v: k for k, v in month_map.items()}
            s_month = reverse_month_map.get(s_month_idx, 'JULI')
            st.text_input("Bulan Akademik (Otomatis):", value=s_month, disabled=True)
            
        st.write("---")
        students = get_master_students(sec_class)
        
        if students:
            st.subheader(f"Daftar Siswa Kelas {sec_class} (Tanggal: {s_date.strftime('%d-%m-%Y')})")
            
            # Form Absensi Harian
            with st.form("form_attendance_sekretaris"):
                att_input_map = {}
                cols = st.columns([3, 2])
                cols[0].markdown("**Nama Siswa**")
                cols[1].markdown("**Status Kehadiran**")
                
                for idx, student in enumerate(students):
                    c1, c2 = st.columns([3, 2])
                    c1.write(f"{idx+1}. {student}")
                    status = c2.selectbox(
                        f"Status_{idx}", 
                        ["H (Hadir)", "S (Sakit)", "I (Izin)", "A (Alpa)"], 
                        key=f"att_{sec_class}_{idx}",
                        label_visibility="collapsed"
                    )
                    att_input_map[student] = status[0]
                    
                if st.form_submit_button("💾 Simpan Absensi Hari Ini"):
                    success, msg = save_daily_attendance_batch(sec_class, s_month, s_date.day, att_input_map)
                    if success: st.success(msg)
                    else: st.error(msg)
        else:
            st.warning("⚠️ Daftar siswa untuk kelas ini belum dikonfigurasi oleh Admin.")

    # 2. GURU PIKET
    elif st.session_state.user_role == "Guru Piket":
        st.title("🕵️‍♂️ Modul Input Guru Piket & Pelajaran")
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
                        success, msg = save_flag_entry(p_date, f_class, f_student, f_type, f_category, f_catatan, "Guru Piket")
                        if success: st.success(msg)
                        else: st.warning(msg)

    # 3. WALI KELAS & GURU BK
    elif st.session_state.user_role in ["Wali Kelas", "Guru BK"]:
        st.title(f"📊 Dashboard Eksekutif ({st.session_state.user_role})")
        target_c = st.session_state.assigned_class if st.session_state.user_role == "Wali Kelas" else st.selectbox("Pilih Kelas Pantauan BK:", classes)
        
        tab_exec_risk, tab_counseling = st.tabs(["🎯 Matriks Risk Scoring & AI Evaluation", "📝 Modul Pemanggilan / Konseling BK"])
        
        with tab_exec_risk:
            st.subheader(f"🛡️ Analisis Risiko Kedisiplinan - Kelas {target_c}")
            students = get_master_students(target_c)
            df_risk = compute_class_risk_df(target_c)
            
            if not df_risk.empty:
                col1, col2, col3 = st.columns(3)
                col1.metric("🔴 Zona Merah (Bahaya)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA MERAH']))
                col2.metric("🟡 Zona Kuning (Waspada)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA KUNING']))
                col3.metric("🟢 Zona Hijau (Aman)", len(df_risk[df_risk['Zona Risiko'] == 'ZONA HIJAU']))
                
                st.dataframe(df_risk.drop(columns=['Badge']).sort_values(by='Skor Poin', ascending=False), use_container_width=True)
                
                st.write("---")
                st.subheader("🤖 AI Narrative Evaluation Generator")
                selected_eval_student = st.selectbox("Pilih Siswa untuk Generasi Evaluasi AI:", students)
                
                if st.button("✨ Generasi Deskripsi Naratif AI"):
                    r_match = df_risk[df_risk['Nama Siswa'] == selected_eval_student]
                    if not r_match.empty:
                        r_row = r_match.iloc[0]
                        narrative_text = generate_ai_student_narrative(selected_eval_student, r_row)
                        st.markdown(narrative_text)
            else:
                st.info("Belum ada data siswa di kelas ini.")

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
                        if save_counseling_log(c_date, target_c, c_student, c_ringkasan, c_rekomendasi, c_status, st.session_state.user_role):
                            st.success("Catatan konseling berhasil ditandatangani dan disimpan!")

    # 4. KEPALA SEKOLAH (FAST LOAD OPTIMIZATION)
    elif st.session_state.user_role == "Kepala Sekolah":
        st.title("🏛️ Dashboard Makro Kedisiplinan - Kepala Sekolah")
        st.caption("Ringkasan Agregat Risiko Kedisiplinan Seluruh Kelas")
        
        with st.spinner("Memuat analisis risiko makro seluruh kelas..."):
            macro_summary = []
            for c in classes:
                df_c = compute_class_risk_df(c)
                red = len(df_c[df_c['Zona Risiko'] == 'ZONA MERAH']) if not df_c.empty else 0
                yellow = len(df_c[df_c['Zona Risiko'] == 'ZONA KUNING']) if not df_c.empty else 0
                green = len(df_c[df_c['Zona Risiko'] == 'ZONA HIJAU']) if not df_c.empty else 0
                
                macro_summary.append({
                    'Kelas': c,
                    'Total Siswa': len(df_c),
                    '🔴 Zona Merah': red,
                    '🟡 Zona Kuning': yellow,
                    '🟢 Zona Hijau': green
                })
            df_macro = pd.DataFrame(macro_summary)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Siswa Zona Merah (Sekolah)", df_macro['🔴 Zona Merah'].sum())
        col2.metric("Total Siswa Zona Kuning (Sekolah)", df_macro['🟡 Zona Kuning'].sum())
        col3.metric("Total Siswa Zona Hijau (Sekolah)", df_macro['🟢 Zona Hijau'].sum())
        
        st.subheader("📊 Distribusi Risiko per Kelas")
        st.dataframe(df_macro, use_container_width=True)
        st.bar_chart(df_macro.set_index('Kelas')[['🔴 Zona Merah', '🟡 Zona Kuning', '🟢 Zona Hijau']])

    # 5. ADMIN SYSTEM
    elif st.session_state.user_role == "Admin":
        st.title("🛠️ Pusat Pengaturan Admin")
        st.info("Kelola Kredensial & Master Database Seluruh Sekolah.")
        df_all_masters = fetch_all_master_df()
        st.dataframe(df_all_masters, use_container_width=True)
