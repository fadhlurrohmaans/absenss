import datetime
import requests
import streamlit as st


# ==========================================
# FUNGSI DETEKSI HARI LIBUR NASIONAL INDONESIA
# ==========================================
@st.cache_data(ttl=86400)
def get_indonesian_holidays(year: int) -> dict:
    """Mengembalikan dictionary tanggal hari libur nasional Indonesia (YYYY-MM-DD -> Keterangan).

    Menggabungkan static dictionary (SKB 3 Menteri) dengan API fallback.
    """
    # Database Static Libur Nasional & Cuti Bersama (2025 - 2027)
    static_holidays = {
        # --- TAHUN 2025 ---
        "2025-01-01": "Tahun Baru 2025 Masehi",
        "2025-01-27": "Isra Mikraj Nabi Muhammad SAW",
        "2025-01-28": "Cuti Bersama Tahun Baru Imlek",
        "2025-01-29": "Tahun Baru Imlek 2576 Kongzili",
        "2025-03-28": "Cuti Bersama Hari Suci Nyepi",
        "2025-03-29": "Hari Suci Nyepi (Tahun Baru Saka 1947)",
        "2025-03-31": "Hari Raya Idul Fitri 1446 H",
        "2025-04-01": "Hari Raya Idul Fitri 1446 H",
        "2025-04-02": "Cuti Bersama Idul Fitri 1446 H",
        "2025-04-03": "Cuti Bersama Idul Fitri 1446 H",
        "2025-04-04": "Cuti Bersama Idul Fitri 1446 H",
        "2025-04-07": "Cuti Bersama Idul Fitri 1446 H",
        "2025-04-18": "Wafat Yesus Kristus",
        "2025-04-20": "Kebangkitan Yesus Kristus (Paskah)",
        "2025-05-01": "Hari Buruh Internasional",
        "2025-05-12": "Hari Raya Waisak 2569 BE",
        "2025-05-13": "Cuti Bersama Hari Raya Waisak",
        "2025-05-29": "Kenaikan Yesus Kristus",
        "2025-05-30": "Cuti Bersama Kenaikan Yesus Kristus",
        "2025-06-01": "Hari Lahir Pancasila",
        "2025-06-06": "Hari Raya Idul Adha 1446 H",
        "2025-06-09": "Cuti Bersama Idul Adha 1446 H",
        "2025-06-27": "1 Muharam Tahun Baru Islam 1447 H",
        "2025-08-17": "Proklamasi Kemerdekaan RI",
        "2025-09-05": "Maulid Nabi Muhammad SAW",
        "2025-12-25": "Kelahiran Yesus Kristus (Natal)",
        "2025-12-26": "Cuti Bersama Hari Raya Natal",
        # --- TAHUN 2026 ---
        "2026-01-01": "Tahun Baru 2026 Masehi",
        "2026-01-16": "Isra Mikraj Nabi Muhammad SAW",
        "2026-02-16": "Cuti Bersama Tahun Baru Imlek",
        "2026-02-17": "Tahun Baru Imlek 2577 Kongzili",
        "2026-03-18": "Cuti Bersama Hari Suci Nyepi",
        "2026-03-19": "Hari Suci Nyepi (Tahun Baru Saka 1948)",
        "2026-03-20": "Cuti Bersama Idul Fitri 1447 H",
        "2026-03-21": "Hari Raya Idul Fitri 1447 H",
        "2026-03-22": "Hari Raya Idul Fitri 1447 H",
        "2026-03-23": "Cuti Bersama Idul Fitri 1447 H",
        "2026-03-24": "Cuti Bersama Idul Fitri 1447 H",
        "2026-04-03": "Wafat Yesus Kristus",
        "2026-04-05": "Kebangkitan Yesus Kristus (Paskah)",
        "2026-05-01": "Hari Buruh Internasional",
        "2026-05-14": "Kenaikan Yesus Kristus",
        "2026-05-15": "Cuti Bersama Kenaikan Yesus Kristus",
        "2026-05-27": "Hari Raya Idul Adha 1447 H",
        "2026-05-28": "Cuti Bersama Idul Adha 1447 H",
        "2026-05-31": "Hari Raya Waisak 2570 BE",
        "2026-06-01": "Hari Lahir Pancasila",
        "2026-06-16": "1 Muharam Tahun Baru Islam 1448 H",
        "2026-08-17": "Proklamasi Kemerdekaan RI",
        "2026-08-25": "Maulid Nabi Muhammad SAW",
        "2026-12-24": "Cuti Bersama Hari Raya Natal",
        "2026-12-25": "Kelahiran Yesus Kristus (Natal)",
        # --- TAHUN 2027 ---
        "2027-01-01": "Tahun Baru 2027 Masehi",
        "2027-02-06": "Tahun Baru Imlek 2578 Kongzili",
        "2027-03-09": "Hari Suci Nyepi (Tahun Baru Saka 1949)",
        "2027-03-10": "Hari Raya Idul Fitri 1448 H",
        "2027-03-11": "Hari Raya Idul Fitri 1448 H",
        "2027-03-26": "Wafat Yesus Kristus",
        "2027-03-28": "Kebangkitan Yesus Kristus (Paskah)",
        "2027-05-01": "Hari Buruh Internasional",
        "2027-05-06": "Kenaikan Yesus Kristus",
        "2027-05-17": "Hari Raya Idul Adha 1448 H",
        "2027-05-20": "Hari Raya Waisak 2571 BE",
        "2027-06-01": "Hari Lahir Pancasila",
        "2027-06-06": "1 Muharam Tahun Baru Islam 1449 H",
        "2027-08-17": "Proklamasi Kemerdekaan RI",
        "2027-08-25": "Maulid Nabi Muhammad SAW",
        "2027-12-25": "Kelahiran Yesus Kristus (Natal)",
    }

    # Mencoba mengambil data terbaru via API online jika ada koneksi
    try:
        res = requests.get(
            f"https://dayoffapi.vercel.app/api?year={year}", timeout=2
        )
        if res.status_code == 200:
            api_data = res.json()
            api_holidays = {
                item["is_holiday_date"]: item.get("holiday_name", "Hari Libur")
                for item in api_data
                if item.get("is_holiday")
            }
            if api_holidays:
                return api_holidays
    except Exception:
        pass  # Gunakan data static jika koneksi internet/API gagal

    year_str = str(year)
    return {
        k: v for k, v in static_holidays.items() if k.startswith(year_str)
    }


def is_day_off(dt_obj: datetime.date, holidays_dict: dict) -> tuple[bool, str]:
    """Mengecek apakah suatu tanggal adalah libur akhir pekan atau libur nasional."""
    date_str = dt_obj.strftime("%Y-%m-%d")
    is_weekend = dt_obj.weekday() in [5, 6]  # Sabtu = 5, Minggu = 6

    if date_str in holidays_dict:
        return True, holidays_dict[date_str]
    elif is_weekend:
        return (
            True,
            "Akhir Pekan (Sabtu)" if dt_obj.weekday() == 5 else "Akhir Pekan (Minggu)",
        )

    return False, ""
