import streamlit as st
import pandas as pd
import io

# Konfigurasi halaman utama (Wide Mode)
st.set_page_config(layout="wide", page_title="Absensi Kelas 7F")

# 1. Daftar Bulan & Database Nama Siswa Awal
months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER', 'JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']

initial_students = [
'ALDRIAN SAPUTRA', 'ABRAHAM JO HENDRIANSYAH', 'ADIBAH QONITAH', 
'ADNAN THARIQ SUBHAN', 'AHMAD FATHIRRAHMAN HIDAYAT', 'AQILA SHIDQIYA FILARTI', 
'AULIANSYAH MUNIS PRATAMA', 'AZHA ZAHWA ZAKIA', 'BAGAS PRATAMA ALBAHAR', 
'BAYU AGUNG PRASSETYA', 'DANISH MIFTAHURRIZQI', 'FARREL FELIX JOSHUA L.TOBING*', 
'FATHAN RIZQI AZZUMAR', 'FELICIA ALEXANDRA WONG*', 'FERALDY AAQIL ZAHRAN', 
'GARNETA MIKHA ZIKHELIA TARIGAN*', 'GLEN ALINSKI', 'HAFIDZ FABRIANO RAHARJO', 
'HAURAH NUR FAUZIYYAH', 'KANISA SITI HUMAIRA', 'KHANZA MALIKA ZAVIRA', 
'KIRANA CLAUDYA ANANDA SUDRAJAT', 'LARISA RIMTAKARINA ELEONORA PASARIBU*', 'LATISYA AQUINA SHANUM', 
'MUHAMAD RIZKY RAMADHAN', 'MUHAMMAD FAJRI', 'MUHAMMAD HAKAN RAHMANSYAH', 
'NAIRA PUTRI KUSUMA', 'NAWAL AGHLA GUSTIAWAN', 'NINDAYU KANYA RENGGANIS', 
'RADITHYA KENZOU RYU PUTRANTO', 'RAFFA KHAIRUL AZAM', 'RANIA', 
'RASYA NUGROHO', 'SABRINA AULIYA MILANI', 'YOAS NATANAEL IGORTHY SIALLAGAN*'
]

# 2. Inisialisasi Data MENTAH (Hanya Nama dan Tanggal agar tidak memicu reset loop)
if 'attendance_data' not in st.session_state:
    st.session_state.attendance_data = {}
    date_cols = [f"Tgl {i}" for i in range(1, 32)]
    
    for m in months:
        df = pd.DataFrame(columns=['Nama Siswa'] + date_cols)
        df['Nama Siswa'] = initial_students
        df[date_cols] = '.'  # Default hadir semua berupa titik
        st.session_state.attendance_data[m] = df

# 3. Fungsi Komputasi Rekapitulasi (Dipanggil saat tampil & download saja)
def generate_full_report(df):
    df_report = df.copy()
    date_cols = [col for col in df_report.columns if col.startswith('Tgl')]
    df_report[date_cols] = df_report[date_cols].fillna('.')
    
    s_list, i_list, a_list, h_list, pct_list = [], [], [], [], []
    
    for _, row in df_report.iterrows():
        if pd.isna(row['Nama Siswa']) or str(row['Nama Siswa']).strip() == "":
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0); pct_list.append("0%")
            continue
            
        vals = [str(v).strip().upper() for v in row[date_cols].values]
        s = vals.count('S')
        s_letter = vals.count('SAKIT')
        total_s = s + s_letter
        
        i = vals.count('I')
        i_letter = vals.count('IJIN') + vals.count('IZIN')
        total_i = i + i_letter
        
        a = vals.count('A')
        a_letter = vals.count('ALPHA') + vals.count('ALPA')
        total_a = a + a_letter
        
        h = vals.count('.') + vals.count('HADIR')
        
        total_days = total_s + total_i + total_a + h
        pct = (h / total_days * 100) if total_days > 0 else 0.0
        
        s_list.append(total_s)
        i_list.append(total_i)
        a_list.append(total_a)
        h_list.append(h)
        pct_list.append(f"{pct:.0f}%")
        
    df_report['S'] = s_list
    df_report['I'] = i_list
    df_report['A'] = a_list
    df_report['Hadir'] = h_list
    df_report['%'] = pct_list
    return df_report

# 4. Tampilan Antarmuka Web
st.title("📊 Aplikasi Absensi Digital - Kelas 7F")
selected_month = st.sidebar.selectbox("📅 Pilih Bulan Absensi", months)

st.write("---")
st.subheader(f"📝 Papan Input Absensi — Bulan {selected_month}")
st.caption("Silakan tambah/hapus baris di bawah atau ganti tanda `.` menjadi S, I, atau A secara manual. Data akan langsung terkunci aman.")

# Ambil data bulan aktif dari session state
current_raw_df = st.session_state.attendance_data[selected_month]

# Papan ketik absensi yang bebas dari bug reset/revert
edited_df = st.data_editor(
    current_raw_df,
    num_rows="dynamic",
    use_container_width=True,
    key=f"editor_core_{selected_month}"
)

# Simpan hasil perubahan ke database utama web
st.session_state.attendance_data[selected_month] = edited_df

# 5. Panel Rekapitulasi Real-Time (Ditampilkan terpisah di bawahnya)
st.write("---")
st.subheader("📋 Live Rekapitulasi Kehadiran Siswa")
st.caption("Bagian ini menampilkan total kalkulasi otomatis dari papan input di atas secara langsung.")

# Hasilkan laporan lengkap
full_calculated_df = generate_full_report(edited_df)

# Tampilkan ringkasan singkat (Nama & Hasil Akhir) agar guru lebih mudah memantau
rekap_view = full_calculated_df[['Nama Siswa', 'S', 'I', 'A', 'Hadir', '%']]
st.dataframe(rekap_view, use_container_width=True)

# 6. Fitur Ekspor File Excel Komplit
st.write("---")
st.subheader("📥 Unduh Laporan Excel Terupdate")

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    for m in months:
        # Papan rekap otomatis dimasukkan ke setiap sheet Excel sebelum diunduh
        monthly_report = generate_full_report(st.session_state.attendance_data[m])
        monthly_report.to_excel(writer, sheet_name=m, index=False)

st.download_button(
    label="Download File Excel (.xlsx)",
    data=buffer.getvalue(),
    file_name="ABSENSI_KELAS_7F_FIXED.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
