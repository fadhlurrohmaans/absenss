import streamlit as st
import pandas as pd
import io

# Konfigurasi halaman agar tampilan melebar (Wide Mode)
st.set_page_config(layout="wide", page_title="Absensi Kelas 7A")

# 1. Daftar Bulan & Database Nama Siswa Awal dari Excel Anda
months = ['JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER', 'JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI']

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

# 2. Inisialisasi Data ke dalam Web Session State
if 'all_months_data' not in st.session_state:
    st.session_state.all_months_data = {}
    date_cols = [f"Tgl {i}" for i in range(1, 32)]
    cols = ['Nama Siswa'] + date_cols + ['S', 'I', 'A', 'Hadir', '%']
    
    for m in months:
        df = pd.DataFrame(columns=cols)
        df['Nama Siswa'] = initial_students
        df[date_cols] = '.'  # Default hadir semua di awal
        df[['S', 'I', 'A', 'Hadir']] = 0
        df['%'] = '100%'
        st.session_state.all_months_data[m] = df

# 3. Desain Antarmuka (UI) Aplikasi
st.title("📊 Aplikasi Absensi Digital - Kelas 7A")
st.write("Kelola absensi kelas secara interaktif. Anda dapat menambah, mengubah, atau menghapus nama siswa langsung di tabel bawah.")

# Pilihan Bulan di Sidebar
selected_month = st.sidebar.selectbox("📅 Pilih Bulan Absensi", months)

st.subheader(f"Tabel Absensi - Bulan {selected_month}")
st.info("""
💡 **Petunjuk Penggunaan:**
* **Tambah Siswa Baru:** Gulir ke baris paling bawah tabel, klik baris kosong berlambang `*`, lalu ketik nama siswa.
* **Hapus Siswa:** Klik kotak angka di paling kiri baris siswa yang ingin dihapus, lalu tekan tombol `Delete` di keyboard Anda.
* **Ubah Kehadiran:** Ketik `.` (Hadir), `S` (Sakit), `I` (Izin), atau `A` (Alpha) pada tanggal yang sesuai.
""")

# Fungsi untuk menghitung rekapitulasi otomatis
def recalculate_summary(df):
    date_cols = [col for col in df.columns if col.startswith('Tgl')]
    df[date_cols] = df[date_cols].fillna('.')
    
    s_list, i_list, a_list, h_list, pct_list = [], [], [], [], []
    for _, row in df.iterrows():
        # Validasi jika nama kosong
        if pd.isna(row['Nama Siswa']) or str(row['Nama Siswa']).strip() == "":
            s_list.append(0); i_list.append(0); a_list.append(0); h_list.append(0); pct_list.append("0%")
            continue
            
        vals = [str(v).strip().upper() for v in row[date_cols].values]
        s = vals.count('S')
        i = vals.count('I')
        a = vals.count('A')
        h = vals.count('.') + vals.count('HADIR')
        
        total = s + i + a + h
        pct = (h / total * 100) if total > 0 else 0.0
        
        s_list.append(s)
        i_list.append(i)
        a_list.append(a)
        h_list.append(h)
        pct_list.append(f"{pct:.0f}%")
        
    df['S'] = s_list
    df['I'] = i_list
    df['A'] = a_list
    df['Hadir'] = h_list
    df['%'] = pct_list
    return df

# Mengambil data bulan aktif
current_df = st.session_state.all_months_data[selected_month]

# Menampilkan Editor Tabel Dinamis (Kolom rekap dikunci agar tidak bisa diubah manual)
edited_df = st.data_editor(
    current_df,
    num_rows="dynamic",
    use_container_width=True,
    disabled=['S', 'I', 'A', 'Hadir', '%'],
    key=f"editor_{selected_month}"
)

# Simpan perubahan dan perbarui kalkulasi total
st.session_state.all_months_data[selected_month] = recalculate_summary(edited_df)

# 4. Fitur Download File Excel Terupdate
st.markdown("---")
st.subheader("📥 Download File Excel")

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    for m in months:
        processed_df = recalculate_summary(st.session_state.all_months_data[m])
        processed_df.to_excel(writer, sheet_name=m, index=False)

st.download_button(
    label="Download Seluruh Data Absensi (.xlsx)",
    data=buffer.getvalue(),
    file_name="ABSEN_KELAS_7A_TERBARU.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)