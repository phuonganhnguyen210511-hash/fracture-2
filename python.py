from datetime import datetime
import json
import pandas as pd
import requests


def extract_nasa_power(lat, lon, start_date, end_date):
  """Trích xuất dữ liệu khí hậu hàng ngày từ NASA POWER API.

  Parameters:
      lat (float): Vĩ độ
      lon (float): Kinh độ
      start_date (str): Ngày bắt đầu định dạng 'YYYYMMDD'
      end_date (str): Ngày kết thúc định dạng 'YYYYMMDD'
  """
  url = (
      "https://power.larc.nasa.gov/api/temporal/daily/point?"
      f"parameters=T2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR&community=RE&"
      f"longitude={lon}&latitude={lat}&start={start_date}&end={end_date}&format=JSON"
  )

  try:
    print(f"Đang kết nối tới NASA POWER API cho tọa độ ({lat}, {lon})...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    # Trích xuất phần dữ liệu thông số (parameters)
    parameters = data.get("properties", {}).get("parameter", {})
    if not parameters:
      print("Không tìm thấy dữ liệu thông số trong phản hồi từ API.")
      return pd.DataFrame()

    # Chuyển đổi từ dictionary sang Pandas DataFrame
    df = pd.DataFrame(parameters)

    # Chuyển đổi index (chuỗi ngày dạng YYYYMMDD) thành cột datetime
    df.index = pd.to_datetime(df.index, format="%Y%m%d", errors="coerce")
    df.reset_index(inplace=True)
    df.rename(columns={"index": "date"}, inplace=True)

    return df

  except requests.exceptions.RequestException as e:
    print(f"Lỗi kết nối API: {e}")
    return pd.DataFrame()
  except Exception as e:
    print(f"Lỗi xử lý dữ liệu: {e}")
    return pd.DataFrame()


def clean_and_normalize_data(df_power, df_phenocam=None):
  """Làm sạch, xử lý giá trị thiếu và chuẩn hóa dữ liệu."""
  if df_power.empty:
    return []

  # 1. Xử lý mã lỗi dữ liệu khuyết thiếu của NASA POWER (thường là -999 hoặc -999.0)
  df_power.replace([-999, -999.0], pd.NA, inplace=True)

  # 2. Làm sạch và điền giá trị khuyết thiếu an toàn
  # - Nhiệt độ và bức xạ: dùng nội suy tuyến tính (interpolate) theo thời gian
  df_power["T2M"] = df_power["T2M"].interpolate(method="linear")
  df_power["ALLSKY_SFC_SW_DWN"] = df_power["ALLSKY_SFC_SW_DWN"].interpolate(
      method="linear"
  )
  # - Lượng mưa: giá trị NA thay bằng 0 (không mưa)
  df_power["PRECTOTCORR"] = df_power["PRECTOTCORR"].fillna(0)

  # 3. Chuẩn hóa tên cột và đơn vị rõ ràng
  df_power.rename(
      columns={
          "T2M": "temperature_2m_celsius",
          "ALLSKY_SFC_SW_DWN": "solar_radiation_mj_m2_day",
          "PRECTOTCORR": "precipitation_mm_day",
      },
      inplace=True,
  )

  # 4. Định dạng lại cột ngày thành chuỗi chuẩn ISO (YYYY-MM-DD)
  df_power["date"] = df_power["date"].dt.strftime("%Y-%m-%d")

  # 5. Xử lý tích hợp thêm dữ liệu PhenoCam (nếu có DataFrame truyền vào)
  if df_phenocam is not None and not df_phenocam.empty:
    df_phenocam["date"] = pd.to_datetime(
        df_phenocam["date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    # Gộp dữ liệu theo ngày (Outer join để giữ toàn bộ mốc thời gian)
    merged_df = pd.merge(df_power, df_phenocam, on="date", how="outer")
    merged_df.sort_values("date", inplace=True)
    # Đưa các giá trị NA còn lại về None để JSON hỗ trợ chuẩn null
    merged_df = merged_df.where(pd.notnull(merged_df), None)
    return merged_df.to_dict(orient="records")

  # Nếu không có PhenoCam, chuyển đổi DataFrame sạch thành danh sách dict
  df_power = df_power.where(pd.notnull(df_power), None)
  return df_power.to_dict(orient="records")


def export_to_json(data, output_path="nasa_environmental_data.json"):
  """Xuất dữ liệu dạng danh sách dictionary ra file JSON chuẩn."""
  try:
    with open(output_path, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Đã xuất file JSON thành công tại: {output_path}")
  except Exception as e:
    print(f"Lỗi khi ghi file JSON: {e}")


# --- Ví dụ thực thi ---
if __name__ == "__main__":
  # Cấu hình tham số đầu vào (Ví dụ: Khu vực Hà Nội)
  LATITUDE = 21.0285
  LONGITUDE = 105.8542
  START_DATE = "20250101"
  END_DATE = "20251231"

  # Thực thi trích xuất
  df_raw = extract_nasa_power(LATITUDE, LONGITUDE, START_DATE, END_DATE)

  if not df_raw.empty:
    # Làm sạch và chuẩn hóa
    cleaned_data = clean_and_normalize_data(df_raw)

    # Xuất file JSON
    export_to_json(cleaned_data, "nasa_power_cleaned.json")
    