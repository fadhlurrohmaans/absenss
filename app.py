import calendar
import datetime
import json
import urllib.request
import pandas as pd
import streamlit as st

# 1. Konfigurasi Halaman (Harus di baris paling awal Streamlit)
st.set_page_config(
    page_title="Presensi Tanggal Merah", page_icon="📅", layout="wide"
)

st.title("📅 Sistem Presensi Bulanan")


# 2. Fungsi Ambil Data Hari Libur (Aman dari Hang/Jaringan Putus)
@st.cache_data(ttl=86400)
def get_indonesian_holidays(year: int) -> dict:
    # Backup Data Lokal SKB 3 Menteri
    static_holidays = {
        # 2025
        "2025-01-01": "Tahun Baru 2025 Masehi",
        "2025-01-27": "Isra Mikraj Nabi Muhammad SAW",
        "2025-01-28": "Cuti Bersama Tahun Baru Imlek",
        "2025-01-29": "Tahun Baru Imlek 2576 Kongzili",
        "2025-03-28": "Cuti Bersama Hari Suci Nyepi",
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

    # Coba Sinkronisasi API via urllib bawaan Python
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
        pass  # Jika gagal/offline, otomatis fallback menggunakan data static lokal

    year_str = str(year)
    return {
        k: v for k, v in static_holidays.items() if k.startswith(year_str)
    }


def is_day_off(dt_obj: datetime.date, holidays_dict: dict):
    date_str = dt_obj.strftime("%Y-%m-%d")
    is_weekend = dt_obj.weekday() in [5, 6]  # Sabtu = 5, Minggu = 6

    if date_str in holidays_dict:
        return True, holidays_dict[date_str]
    elif is_weekend:
        return True, "Akhir Pekan"

    return False, ""


# 3. Kontrol Filter Halaman
st.sidebar.header("Filter Periode")
selected_year = st.sidebar.selectbox("Tahun", [2025, 2026, 2027], index=1)
selected_month = st.sidebar.selectbox(
    "Bulan",
    options=list(range(1, 13)),
    format_func=lambda x: datetime.date(2000, x, 1).strftime("%B"),
    index=7,
)

# 4. Ambil Data Libur & Tampilkan Informasi
holidays_data = get_indonesian_holidays(selected_year)

month_prefix = f"{selected_year}-{selected_month:02d}"
current_month_holidays = {
    d: name
    for d, name in holidays_data.items()
    if d.startswith(month_prefix)
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
else:
    st.caption("ℹ️ Tidak terdapat hari libur nasional pada bulan ini.")

# 5. Generasi Tabel Presensi
_, num_days = calendar.monthrange(selected_year, selected_month)

# Sample Data Anggota/Siswa
raw_data = {
    "NIS/NIP": ["1001", "1002", "1003"],
    "Nama": ["Ahmad Fauzi", "Siti Aminah", "Budi Santoso"],
}

# Isi status per tanggal (L = Libur, H = Hadir/Hari Kerja)
for day in range(1, num_days + 1):
    dt_current = datetime.date(selected_year, selected_month, day)
    libur, _ = is_day_off(dt_current, holidays_data)
    raw_data[str(day)] = ["L" if libur else "H"] * len(raw_data["NIS/NIP"])

df_presensi = pd.DataFrame(raw_data)

st.subheader(f"Tabel Presensi ({selected_month}/{selected_year})")
st.dataframe(df_presensi, use_container_width=True)
