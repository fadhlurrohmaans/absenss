import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
import datetime
import calendar
import io
import base64

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

# Konfigurasi Halaman Streamlit
st.set_page_config(layout="wide", page_title="Sistem Early Warning Kedisiplinan Siswa - GovTech", page_icon="🏫")

# CSS Custom UI Enterprise
st.markdown("""
    <style>
    div[data-testid="stDataFrame"] { -webkit-overflow-scrolling: touch; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    .badge-red { background-color: #ff4d4f; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
    .badge-yellow { background-color: #faad14; color: black; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
    .badge-green { background-color: #52c41a; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# Parameter Utamanya
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

# --- 2. MANAGEMENT DATABASE MASTER NAMA ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_master_df():
    try:
        ws = sh.worksheet("MASTER_SISWA")
        data = ws.get_all_values()
        if not data: raise WorksheetNotFound
        df = pd.DataFrame(data[1:], columns=data[0])
        for c in classes:
            if c not in df.columns: df[c] = ""
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

# --- 3. CONFIG & USER MANAGEMENTS ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_config_passwords():
    try:
        ws = sh.worksheet("CONFIG")
        data = ws.get_all_records()
        return dict(zip(pd.DataFrame(data)['Key'], pd.DataFrame(data)['Password']))
    except Exception:
        keys = ['Admin', 'Guru Piket', 'Guru BK', 'Kepala Sekolah'] + classes
        default_passwords = ['admin123', 'piket123', 'bk123', 'kepsek123'] + [f"{c.lower()}123" for c in classes]
        return dict(zip(keys, default_passwords))

# --- 4. LOG KETERLAMBATAN, FLAGGING & KONSELING (OPTIMIZED WITH CACHE) ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_lateness_logs():
    try:
        ws = sh.worksheet("LOG_KETERLAMBATAN")
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame(columns=['Tanggal', 'Kelas', 'Nama Siswa', 'Menit Terlambat', 'Pencatat'])

def save_lateness_entry(tanggal, kelas, nama, menit, pencatat):
    try:
        try:
            ws = sh.worksheet("LOG_KETERLAMBATAN")
        except WorksheetNotFound:
            ws = sh.add_worksheet("LOG_KETERLAMBATAN", rows="1000", cols="10")
            ws.append_row(['Tanggal', 'Kelas', 'Nama Siswa', 'Menit Terlambat', 'Pencatat'])
        ws.append_row([str(tanggal), kelas, nama, int(menit), pencatat])
        fetch_lateness_logs.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan keterlambatan: {e}")
        return False

@st.cache_data(ttl=300, show_spinner=False)
def fetch_flags():
    try:
        ws = sh.worksheet("FLAGS_PERILAKU")
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame(columns=['Tanggal', 'TahunMinggu', 'Kelas', 'Nama Siswa', 'Tipe', 'Kategori', 'Catatan', 'Pencatat'])

def save_flag_entry(tanggal, kelas, nama, tipe, kategori, catatan, pencatat):
    dt = datetime.datetime.strptime(str(tanggal), "%Y-%m-%d").date() if isinstance(tanggal, str) else tanggal
    year_week = f"{dt.year}-{dt.isocalendar()[1]}"
    
    df_flags = fetch_flags()
    if not df_flags.empty:
        existing = df_flags[(df_flags['Nama Siswa'] == nama) & (df_flags['TahunMinggu'] == year_week)]
        if len(existing) > 0:
            return False, f"⚠️ Siswa '{nama}' sudah diberikan flagging pada minggu ini ({year_week}). Batas maksimal 1x/minggu!"

    try:
        try:
            ws = sh.worksheet("FLAGS_PERILAKU")
        except WorksheetNotFound:
            ws = sh.add_worksheet("FLAGS_PERILAKU", rows="1000", cols="10")
            ws.append_row(['Tanggal', 'TahunMinggu', 'Kelas', 'Nama Siswa', 'Tipe', 'Kategori', 'Catatan', 'Pencatat'])
        ws.append_row([str(dt), year_week, kelas, nama, tipe, kategori, catatan, pencatat])
        fetch_flags.clear()
        return True, "✅ Flagging perilaku berhasil dicatat!"
    except Exception as e:
        return False, f"Gagal menyimpan flag: {e}"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_counseling_logs():
    try:
        ws = sh.worksheet("KONSELING_BK")
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame(columns=['ID', 'Tanggal', 'Kelas', 'Nama Siswa', 'Ringkasan', 'Rekomendasi', 'Status', 'Konselor'])

def save_counseling_log(tanggal, kelas, nama, ringkasan, rekomendasi, status, konselor):
    try:
        try:
            ws = sh.worksheet("KONSELING_BK")
        except WorksheetNotFound:
            ws = sh.add_worksheet("KONSELING_BK", rows="500", cols="10")
            ws.append_row(['ID', 'Tanggal', 'Kelas', 'Nama Siswa', 'Ringkasan', 'Rekomendasi', 'Status', 'Konselor'])
        
        c_id = f"BK-{int(datetime.datetime.now().timestamp())}"
        ws.append_row([c_id, str(tanggal), kelas, nama, ringkasan, rekomendasi, status, konselor])
        fetch_counseling_logs.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan catatan konseling: {e}")
        return False

# --- 5. DATA ABSENSI BULANAN ---
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_attendance_data_from_gsheets(kelas, month):
    sheet_name = f"{kelas}_{month}"
    year = get_year_for_month(month)
    month_num = month_map[month]
    _, max_days = calendar.monthrange(year, month_num)
    master_names = get_master_students(kelas) or ["(Siswa Belum Diisi)"]
    
    try:
        ws = sh.worksheet(sheet_name)
        df_stored = pd.DataFrame(ws.get_all_records())
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
            col_vals = []
            for idx in range(len(master_names)):
                if idx < len(df_stored) and col in df_stored.columns:
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
    ws.update(range_name='A1', values=[df.fillna('').astype(str).columns.values.tolist()] + df.fillna('').astype(str).values.tolist())
    fetch_attendance_data_from_gsheets.clear()

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

# --- 6. ENGINE RISK SCORING & ZONASIKAN (BATCH OPTIMIZED) ---
def calculate_risk_score(student_name, kelas, df_late=None, df_flags=None):
    total_alpa = 0
    for m in months:
        df_m = fetch_attendance_data_from_gsheets(kelas, m)
        rep = generate_full_report(df_m)
        r = rep[rep['Nama Siswa'] == student_name]
        if not r.empty:
            total_alpa += int(r.iloc[0]['A'])
            
    if df_late is None:
        df_late = fetch_lateness_logs()
        
    total_late_min = 0
    if not df_late.empty:
        s_late = df_late[(df_late['Nama Siswa'] == student_name) & (df_late['Kelas'] == kelas)]
        total_late_min = s_late['Menit Terlambat'].astype(int).sum() if not s_late.empty else 0
        
    if df_flags is None:
        df_flags = fetch_flags()
        
    neg_flags, pos_flags = 0, 0
    if not df_flags.empty:
        s_flags = df_flags[(df_flags['Nama Siswa'] == student_name) & (df_flags['Kelas'] == kelas)]
        if not s_flags.empty:
            neg_flags = len(s_flags[s_flags['Tipe'] == 'NEGATIF'])
            pos_flags = len(s_flags[s_flags['Tipe'] == 'POSITIF'])
            
    score = (total_alpa * 15) + (total_late_min // 5) + (neg_flags * 10) - (pos_flags * 5)
    score = max(0, score)
    
    if score <= 20:
        zone = "ZONA HIJAU"
        badge = "🟢 Hijau (Aman)"
    elif score <= 50:
        zone = "ZONA KUNING"
        badge = "🟡 Kuning (Waspada)"
    else:
        zone = "ZONA MERAH"
        badge = "🔴 Merah (Kritis/Bahaya)"
        
    return {
        'score': score,
        'zone': zone,
        'badge': badge,
        'alpa': total_alpa,
        'late_min': total_late_min,
        'neg_flags': neg_flags,
        'pos_flags': pos_flags
    }

# --- 7. INTEGRASI AI GENERATOR ---
def generate_ai_student_narrative(student_name, risk_data, flag_history):
    narrative = f"### 🤖 Evaluasi Naratif AI untuk: {student_name}\n\n"
    narrative += f"**Status Risiko:** {risk_data['badge']} (Skor Total Kedisiplinan: **{risk_data['score']} Poin**)\n\n"
    
    if risk_data['alpa'] == 0 and risk_data['late_min'] == 0:
        narrative += "• **Presensi & Ketepatan Waktu:** Siswa menunjukkan tingkat kedisiplinan yang sangat baik tanpa riwayat Alpa maupun keterlambatan.\n"
    else:
        narrative += f"• **Presensi & Ketepatan Waktu:** Terdeteksi akumulasi **{risk_data['alpa']} hari Alpa** dan akumulasi keterlambatan **{risk_data['late_min']} menit**. Hal ini membutuhkan perhatian pada konsistensi kehadiran.\n"
        
    narrative += f"• **Catatan Perilaku Guru:** Tercatat {risk_data['pos_flags']} indikator positif dan {risk_data['neg_flags']} catatan indikator negatif.\n"
    
    if risk_data['zone'] == "ZONA MERAH":
        narrative += "\n⚠️ **Rekomendasi Tindakan (Prioritas BK):** Siswa berada dalam Zona Merah. Disarankan untuk *segera melayangkan Surat Pemanggilan Orang Tua (SP)* dan mengadakan sesi konseling khusus untuk mengidentifikasi kendala utama di rumah/lingkungan."
    elif risk_data['zone'] == "ZONA KUNING":
        narrative += "\n💡 **Rekomendasi Tindakan (Wali Kelas):** Siswa dalam Zona Waspada. Wali Kelas disarankan melakukan dialog personal dan memberikan pendampingan agar kedisiplinan tidak kian menurun."
    else:
        narrative += "\n✨ **Rekomendasi Tindakan:** Pertahankan motivasi belajar siswa dan berikan apresiasi atas kedisiplinan yang terjaga."
        
    return narrative

# --- 8. OTENTIKASI & SESSION STATE ---
passwords = fetch_config_passwords()

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

# --- LOGIN FORM ---
if not st.session_state.logged_in:
    st.title("🔐 Login Sistem Kedisiplinan Siswa")
    st.caption("GovTech Education Platform - Early Warning Architecture")
    
    with st.form("login_form"):
        role = st.selectbox("Pilih Hak Akses Peran:", ["Wali Kelas", "Guru Piket / Pelajaran", "Guru BK", "Kepala Sekolah", "Administrator System"])
        target_class = st.selectbox("Pilih Kelas Anda:", classes) if role == "Wali Kelas" else None
        password_input = st.text_input("Masukkan Password Akun:", type="password")
        
        if st.form_submit_button("🔑 Masuk / Otentikasi"):
            if role == "Wali Kelas" and password_input == passwords.get(target_class):
                st.session_state.logged_in, st.session_state.user_role, st.session_state.assigned_class = True, "Wali Kelas", target_class
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

# --- DASHBOARD ROLES ---
else:
    # 1. GURU PIKET / PELAJARAN
    if st.session_state.user_role == "Guru Piket":
        st.title("🕵️‍♂️ Modul Input Guru Piket & Pelajaran")
        
        tab_piket_input, tab_flagging = st.tabs(["⏱️ Input Presensi & Keterlambatan", "🚩 Fitur Flagging Perilaku (Max 1x/Minggu)"])
        
        with tab_piket_input:
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1: p_class = st.selectbox("Pilih Kelas:", classes, key="piket_c")
            with col_p2: p_month = st.selectbox("Pilih Bulan:", months, key="piket_m")
            with col_p3: p_date = st.date_input("Tanggal Transaksi:", datetime.date.today())
            
            students = get_master_students(p_class)
            if students:
                st.markdown(f"##### Form Input Keterlambatan Khusus - Kelas {p_class}")
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
            st.info("💡 **Aturan System GovTech:** Maksimal **1 kali/minggu** per siswa untuk mencatat indikator positif/negatif.")
            
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
                    else:
                        st.error("Siswa belum dipilih!")

    # 2. WALI KELAS & GURU BK
    elif st.session_state.user_role in ["Wali Kelas", "Guru BK"]:
        st.title(f"📊 Dashboard Eksekutif ({st.session_state.user_role})")
        
        target_c = st.session_state.assigned_class if st.session_state.user_role == "Wali Kelas" else st.selectbox("Pilih Kelas Pantauan BK:", classes)
        
        tab_exec_risk, tab_counseling = st.tabs(["🎯 Matriks Risk Scoring & AI Evaluation", "📝 Modul Pemanggilan / Konseling BK"])
        
        with tab_exec_risk:
            st.subheader(f"🛡️ Analisis Risiko Kedisiplinan - Kelas {target_c}")
            students = get_master_students(target_c)
            
            # Fetch log sekali saja untuk mengurangi kuota API Google Sheets
            df_late_all = fetch_lateness_logs()
            df_flags_all = fetch_flags()
            
            risk_table = []
            for s in students:
                r_data = calculate_risk_score(s, target_c, df_late_all, df_flags_all)
                risk_table.append({
                    'Nama Siswa': s,
                    'Zona Risiko': r_data['zone'],
                    'Skor Poin': r_data['score'],
                    'Alpa (Hari)': r_data['alpa'],
                    'Terlambat (Menit)': r_data['late_min'],
                    'Flag Negatif': r_data['neg_flags'],
                    'Flag Positif': r_data['pos_flags']
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
                    flags = df_flags_all[df_flags_all['Nama Siswa'] == selected_eval_student] if not df_flags_all.empty else pd.DataFrame()
                    narrative_text = generate_ai_student_narrative(selected_eval_student, r_info, flags)
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

    # 3. KEPALA SEKOLAH
    elif st.session_state.user_role == "Kepala Sekolah":
        st.title("🏛️ Dashboard Makro Kedisiplinan - Kepala Sekolah")
        st.caption("Ringkasan Agregat Risiko Kedisiplinan Seluruh Kelas")
        
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
            macro_summary.append({
                'Kelas': c,
                'Total Siswa': len(st_list),
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

    # 4. ADMIN SYSTEM
    elif st.session_state.user_role == "Admin":
        st.title("🛠️ Pusat Pengaturan Admin")
        st.info("Kelola Kredensial & Master Database Seluruh Sekolah.")
        df_all_masters = fetch_all_master_df()
        st.dataframe(df_all_masters, use_container_width=True)
