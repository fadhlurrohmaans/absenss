import calendar
import datetime
import io
import json
import urllib.request
import pandas as pd
import streamlit as st

# ==========================================
# 1. KONFIGURASI HALAMAN (Harus Paling Atas)
# ==========================================
st.set_page_config(
    page_title="Sistem Presensi Lengkap + Kalender Nasional",
    page_icon="📋",
    layout="wide",
)


# ==========================================
# 2. LOGIKA KALENDER NASIONAL & TANGGAL MERAH
# ==========================================
@st.cache_data(ttl=86400)
def get_indonesian_holidays(year: int) -> dict:
    """Mengambil data hari libur nasional & cuti bersama (Offline Static + Online Fallback)."""
    static_holidays = {
        # 2025
        "2025-01-01": "Tahun Baru 2025 Masehi",
        "2025-01-27": "Isra Mikraj Nabi Muhammad SAW",
        "2025-01-28": "Cuti Bersama Imlek",
        "2025-01-29": "Tahun Baru Imlek 2576 Kongzili",
        "2025-03-28": "Cuti Bersama Nyepi",
        "2025-03-29": "Hari Suci Nyepi",
        "2025-03-31": "Hari Raya Idul Fitri 1446 H",
        "2025-04-01": "Hari Raya Idul Fitri 1446 H",
        "2025-04-18": "Wafat Yesus Kristus",
        "2025-05-01": "Hari Buruh Internasional",
        "2025-05-12": "Hari Raya Waisak 2569 BE",
        "2025-05-29": "Kenaikan Yesus Kristus",
        "2025-06-01": "Hari Lahir Pancasila",
        "2025-06-06": "Hari Raya Idul Adha 1446 H",
        "2025-06-27": "Tahun Baru Islam 1447 H",
        "2025-08-17": "Proklamasi Kemerdekaan RI",
        "2025-09-05": "Maulid Nabi Muhammad SAW",
        "2025-12-25": "Hari Raya Natal",
        # 2026
        "2026-01-01": "Tahun Baru 2026 Masehi",
        "2026-01-16": "Isra Mikraj Nabi Muhammad SAW",
        "2026-02-17": "Tahun Baru Imlek 2577 Kongzili",
        "2026-03-19": "Hari Suci Nyepi",
        "2026-03-21": "Hari Raya Idul Fitri 1447 H",
        "2026-03-22": "Hari Raya Idul Fitri 1447 H",
        "2026-04-03": "Wafat Yesus Kristus",
        "2026-05-01": "Hari Buruh Internasional",
        "2026-05-14": "Kenaikan Yesus Kristus",
        "2026-05-27": "Hari Raya Idul Adha 1447 H",
        "2026-05-31": "Hari Raya Waisak 2570 BE",
        "2026-06-01": "Hari Lahir Pancasila",
        "2026-06-16": "Tahun Baru Islam 1448 H",
        "2026-08-17": "Proklamasi Kemerdekaan RI",
        "2026-08-25": "Maulid Nabi Muhammad SAW",
        "2026-12-25": "Hari Raya Natal",
    }

    try:
        url = f"https://dayoffapi.vercel.app/api?year={year}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                api_holidays = {
                    item["is_holiday_date"]: item.get(
                        "holiday_name", "Hari Libur"
                    )
                    for item in data
                    if item.get("is_holiday")
                }
                if api_holidays:
                    return api_holidays
    except Exception:
        pass

    year_str = str(year)
    return {
        k: v for k, v in static_holidays.items() if k.startswith(year_str)
    }


def is_day_off(dt_obj: datetime.date, holidays_dict: dict):
    date_str = dt_obj.strftime("%Y-%m-%d")
    is_weekend = dt_obj.weekday() in [5, 6]  # 5 = Sabtu, 6 = Minggu

    if date_str in holidays_dict:
        return True, holidays_dict[date_str]
    elif is_weekend:
        return True, "Akhir Pekan"
    return False, ""


# ==========================================
# 3. INISIALISASI DATABASE/SESSION STATE
# ==========================================
if "members" not in st.session_state:
    # Data master anggota/siswa awal
    st.session_state.members = [
        {"NIP": "1001", "Nama": "Ahmad Fauzi"},
        {"NIP": "1002", "Nama": "Siti Aminah"},
        {"NIP": "1003", "Nama": "Budi Santoso"},
    ]

if "presensi_db" not in st.session_state:
    # Menyimpan status per key "YYYY-MM"
    st.session_state.presensi_db = {}


# ==========================================
# 4. SIDEBAR - CONTROL & MANAGEMENT
# ==========================================
st.sidebar.title("📌 Menu & Kontrol")

# Filter Periode
st.sidebar.subheader("🗓️ Pilih Periode")
selected_year = st.sidebar.selectbox("Tahun", [2025, 2026, 2027], index=1)
selected_month = st.sidebar.selectbox(
    "Bulan",
    options=list(range(1, 13)),
    format_func=lambda x: datetime.date(2000, x, 1).strftime("%B"),
    index=7,  # Default Agustus
)

period_key = f"{selected_year}-{selected_month:02d}"
holidays_data = get_indonesian_holidays(selected_year)
_, num_days = calendar.monthrange(selected_year, selected_month)

# Fitur Tambah Anggota / Siswa Baru
st.sidebar.markdown("---")
st.sidebar.subheader("➕ Tambah Anggota Baru")
with st.sidebar.form("form_tambah_anggota", clear_on_submit=True):
    new_nip = st.text_input("NIP / NIS")
    new_nama = st.text_input("Nama Lengkap")
    submit_btn = st.form_submit_button("Simpan Anggota")

    if submit_btn:
        if new_nip and new_nama:
            # Cek jika NIP sudah ada
            if any(m["NIP"] == new_nip for m in st.session_state.members):
                st.sidebar.error("NIP/NIS sudah terdaftar!")
            else:
                st.session_state.members.append(
                    {"NIP": new_nip, "Nama": new_nama}
                )
                st.sidebar.success(f"{new_nama} berhasil ditambahkan!")
                st.rerun()
        else:
            st.sidebar.warning("NIP dan Nama harus diisi.")

# Fitur Hapus Anggota
if st.session_state.members:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🗑️ Hapus Anggota")
    member_to_del = st.sidebar.selectbox(
        "Pilih Anggota",
        options=[m["NIP"] for m in st.session_state.members],
        format_func=lambda nip: next(
            f"{m['Nama']} ({m['NIP']})"
            for m in st.session_state.members
            if m["NIP"] == nip
        ),
    )
    if st.sidebar.button("Hapus Dari Sistem"):
        st.session_state.members = [
            m for m in st.session_state.members if m["NIP"] != member_to_del
        ]
        st.sidebar.success("Anggota berhasil dihapus.")
        st.rerun()

# Legenda Status
st.sidebar.markdown("---")
st.sidebar.info(
    "**Keterangan Kode Status:**\n"
    "- **H**: Hadir\n"
    "- **S**: Sakit\n"
    "- **I**: Izin\n"
    "- **A**: Alpha / Tanpa Keterangan\n"
    "- **L**: Libur (Weekend / Tanggal Merah)"
)


# ==========================================
# 5. HALAMAN UTAMA - DASHBOARD & TABEL
# ==========================================
st.title("📋 Sistem Informasi Presensi")
st.caption(
    f"Periode Aktif: **{datetime.date(selected_year, selected_month, 1).strftime('%B %Y')}**"
)

# Banner Informasi Hari Libur Bulan Ini
current_month_holidays = {
    d: name
    for d, name in holidays_data.items()
    if d.startswith(period_key)
}

if current_month_holidays:
    info_items = [
        f"**Tgl {int(d.split('-')[2])}**: {name}"
        for d, name in sorted(current_month_holidays.items())
    ]
    st.info(
        "🎉 **Hari Libur Nasional & Cuti Bersama Bulan Ini:**\n\n"
        + " • "
        + "\n • ".join(info_items)
    )

# --- PENYUSUNAN DATA MATRIKS PRESENSI ---
day_cols = [str(d) for d in range(1, num_days + 1)]

# Inisialisasi atau Sinkronisasi Data Bulan Ini
if period_key not in st.session_state.presensi_db:
    grid_data = []
    for m in st.session_state.members:
        row = {"NIP": m["NIP"], "Nama": m["Nama"]}
        for day in range(1, num_days + 1):
            dt_curr = datetime.date(selected_year, selected_month, day)
            libur, _ = is_day_off(dt_curr, holidays_data)
            row[str(day)] = "L" if libur else "H"
        grid_data.append(row)
    st.session_state.presensi_db[period_key] = pd.DataFrame(grid_data)
else:
    # Pastikan jika ada anggota baru/hapus, DataFrame disesuaikan
    df_existing = st.session_state.presensi_db[period_key]
    updated_rows = []
    for m in st.session_state.members:
        existing_row = df_existing[df_existing["NIP"] == m["NIP"]]
        if not existing_row.empty:
            updated_rows.append(existing_row.iloc[0].to_dict())
        else:
            row = {"NIP": m["NIP"], "Nama": m["Nama"]}
            for day in range(1, num_days + 1):
                dt_curr = datetime.date(selected_year, selected_month, day)
                libur, _ = is_day_off(dt_curr, holidays_data)
                row[str(day)] = "L" if libur else "H"
            updated_rows.append(row)
    st.session_state.presensi_db[period_key] = pd.DataFrame(updated_rows)

# Form Pencarian / Filter Nama
search_term = st.text_input("🔍 Cari berdasarkan Nama atau NIP/NIS...", "")

df_to_display = st.session_state.presensi_db[period_key].copy()
if search_term:
    df_to_display = df_to_display[
        df_to_display["Nama"].str.contains(search_term, case=False)
        | df_to_display["NIP"].str.contains(search_term, case=False)
    ]

# --- FITUR INTERAKTIF: EDIT PRESENSI (st.data_editor) ---
st.subheader("📝 Input / Edit Presensi Interaktif")
st.caption(
    "Anda dapat mengedit status presensi secara langsung pada tabel di bawah ini:"
)

# Konfigurasi kolom dropdown (H, S, I, A, L)
column_config = {
    "NIP": st.column_config.TextColumn("NIP/NIS", disabled=True),
    "Nama": st.column_config.TextColumn("Nama Lengkap", disabled=True),
}
status_options = ["H", "S", "I", "A", "L"]
for c in day_cols:
    column_config[c] = st.column_config.SelectboxColumn(
        label=c, options=status_options, required=True, width="small"
    )

edited_df = st.data_editor(
    df_to_display,
    column_config=column_config,
    hide_index=True,
    use_container_width=True,
    key=f"editor_{period_key}",
)

# Update database dari hasil editan pengguna
for idx, row in edited_df.iterrows():
    nip_val = row["NIP"]
    st.session_state.presensi_db[period_key].loc[
        st.session_state.presensi_db[period_key]["NIP"] == nip_val, day_cols
    ] = row[day_cols]


# ==========================================
# 6. REKAPITULASI & STATISTIK AUTOMATIS
# ==========================================
st.markdown("---")
st.subheader("📊 Rekapitulasi & Persentase Kehadiran")

df_rekap = st.session_state.presensi_db[period_key].copy()


# Hitung Total Status
def count_status(row, status):
    return (row[day_cols] == status).sum()


df_rekap["Hadir (H)"] = df_rekap.apply(lambda r: count_status(r, "H"), axis=1)
df_rekap["Sakit (S)"] = df_rekap.apply(lambda r: count_status(r, "S"), axis=1)
df_rekap["Izin (I)"] = df_rekap.apply(lambda r: count_status(r, "I"), axis=1)
df_rekap["Alpha (A)"] = df_rekap.apply(lambda r: count_status(r, "A"), axis=1)
df_rekap["Libur (L)"] = df_rekap.apply(lambda r: count_status(r, "L"), axis=1)

# Hitung Persentase Kehadiran (Hari Efektif Kerja = Total Hari - Hari Libur)
df_rekap["Hari Efektif"] = num_days - df_rekap["Libur (L)"]


def calc_pct(row):
    if row["Hari Efektif"] > 0:
        return f"{(row['Hadir (H)'] / row['Hari Efektif']) * 100:.1f}%"
    return "0.0%"


df_rekap["% Kehadiran"] = df_rekap.apply(calc_pct, axis=1)

# Tampilkan Rekapitulasi
cols_rekap = [
    "NIP",
    "Nama",
    "Hadir (H)",
    "Sakit (S)",
    "Izin (I)",
    "Alpha (A)",
    "Libur (L)",
    "Hari Efektif",
    "% Kehadiran",
]
st.dataframe(df_rekap[cols_rekap], hide_index=True, use_container_width=True)


# ==========================================
# 7. FITUR EKSPOR DATA (CSV / EXCEL)
# ==========================================
st.markdown("---")
st.subheader("📥 Unduh Laporan Presensi")

col1, col2 = st.columns(2)

# Export CSV
csv_data = df_rekap.to_csv(index=False).encode("utf-8")
col1.download_button(
    label="📄 Download Format CSV",
    data=csv_data,
    file_name=f"Presensi_{period_key}.csv",
    mime="text/csv",
)

# Export Excel
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    df_rekap.to_excel(writer, sheet_name="Rekap Presensi", index=False)

col2.download_button(
    label="📊 Download Format Excel (.xlsx)",
    data=buffer.getvalue(),
    file_name=f"Presensi_{period_key}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
