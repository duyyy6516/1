import pandas as pd
import numpy as np

def get_biological_block(hour):
    """
    Phân loại giờ thực tế sang 5 khối chu kỳ sinh học của cây trồng
    """
    if 5 <= hour < 10: return "🌅 Sáng (05h-10h)"
    elif 10 <= hour < 15: return "☀️ Trưa (10h-15h)"
    elif 15 <= hour < 19: return "🌇 Chiều (15h-19h)"
    elif 19 <= hour < 23: return "🌌 Tối (19h-23h)"
    else: return "🌙 Khuya (23h-05h)"

def predict_vpd_trend_v3(history_list, current_hour, current_matrix):
    """
    Thuật toán phân tích chuỗi dữ liệu gần nhất để dự đoán xu hướng biến thiên khí hậu.
    """
    if len(history_list) < 2:
        return "Xu hướng: 🔄 Đang tích lũy chu kỳ dữ liệu trạm.", "STABLE"
        
    v1 = history_list[0]["VPD (kPa)"]
    v2 = history_list[1]["VPD (kPa)"]
    diff = v1 - v2
    
    if diff > 0.04:
        return "📈 Chỉ số VPD đang tăng (Khí hậu nóng khô dần).", "RISING"
    elif diff < -0.04:
        return "📉 Chỉ số VPD đang giảm (Khí hậu mát ẩm dần).", "FALLING"
    else:
        return "➡️ Chỉ số VPD đi ngang điềm tĩnh ổn định.", "STABLE"

def calculate_plant_stress_hours(df_processed, file_matrix, filter_option):
    """
    Tính toán thời gian tích lũy cây bị stress khí khổng và rủi ro bùng phát nấm bệnh.
    """
    dry_count = 0
    wet_count = 0
    
    for _, r in df_processed.iterrows():
        b_name = get_biological_block(r["datetime_internal"].hour)
        v_min, v_max = file_matrix[b_name]
        v_val = r["VPD (kPa)"]
        
        if v_val >= v_max + 0.5: dry_count += 1
        if v_val < v_min - 0.2: wet_count += 1
        
    # Quy đổi số điểm ghi nhận sang số giờ thực tế dựa trên bộ resample lọc gộp
    step_hour = 1.0 if "1 Tuần" in filter_option else (10.0 / 60.0)
    dry_hours = round(dry_count * step_hour, 1)
    with_hours = round(wet_count * step_hour, 1)
    
    # Tính phần trăm rủi ro nấm phấn trắng/nấm xám Đà Lạt dựa trên số giờ đọng ẩm
    fungus_risk = int(min(100, (wet_count * step_hour * 15) + 10))
    if df_processed.empty: fungus_risk = 0
        
    return {"dry_hours": dry_hours, "wet_hours": with_hours, "fungus_risk": fungus_risk}

def calculate_dew_point(temp, rh):
    """
    Tính nhiệt độ điểm đọng sương phục vụ cảnh báo sớm ngập sương biểu bì lá.
    """
    a = 17.27
    b = 237.7
    alpha = ((a * temp) / (b + temp)) + np.log(rh / 100.0)
    dew_pt = (b * alpha) / (a - alpha)
    return round(dew_pt, 1)

def analyze_day_by_blocks_rt(history_list, current_matrix, selected_day):
    """
    Tổng hợp báo cáo phán quyết ma trận buổi tổng hợp (Bảng Realtime/Bảng File)
    """
    if not history_list:
        return pd.DataFrame()
        
    df = pd.DataFrame(history_list)
    df_day = df[df["Ngày"] == selected_day].copy()
    
    if df_day.empty:
        return pd.DataFrame()
        
    df_day["Khối Buổi"] = df_day["datetime_internal"].dt.hour.apply(get_biological_block)
    
    summary_data = []
    # Quét qua cả 5 buổi sinh học theo đúng thứ tự ma trận mẫu của bạn
    for block_name in ["🌅 Sáng (05h-10h)", "☀️ Trưa (10h-15h)", "🌇 Chiều (15h-19h)", "🌌 Tối (19h-23h)", "🌙 Khuya (23h-05h)"]:
        df_b = df_day[df_day["Khối Buổi"] == block_name]
        if df_b.empty:
            continue
            
        avg_t = df_b["Nhiệt độ (°C)"].mean()
        avg_h = df_b["Độ ẩm (%)"].mean()
        avg_v = df_b["VPD (kPa)"].mean()
        
        v_min, v_max = current_matrix[block_name]
        
        if avg_v >= v_max + 0.5:
            stt = "🔴 Quá Khô Nóng"
            act = "Cần kích hoạt béc tưới phun mưa trên mái nhà kính xả nhiệt khẩn cấp."
        elif avg_v > v_max:
            stt = "🟡 Hơi Hanh Khô"
            act = "Cần chạy bổ sung hệ thống phun sương mịn vách hông."
        elif avg_v < v_min - 0.2:
            stt = "🔵 Quá Ẩm Đọng Hơi"
            act = "Bắt buộc ngừng toàn bộ chu kỳ tưới gốc, bật quạt đảo gió trần xua ẩm."
        elif avg_v < v_min:
            stt = "🌐 Ẩm Nhẹ"
            act = "Hé nhẹ lưới cắt nắng/rèm hông tăng gió lùa tự nhiên."
        else:
            stt = "🟩 Giao Thoại Lý Tưởng"
            act = "Môi trường phân buổi hoàn hảo, phần cứng giữ trạng thái nghỉ."
            
        summary_data.append({
            "Khoảng Buổi": block_name.split(" ")[0] + " " + block_name.split(" ")[1],
            "Nhiệt độ TB": f"{avg_t:.1f} °C",
            "Độ ẩm TB": f"{avg_h:.1f} %",
            "VPD Trung Bình": f"{avg_v:.2f} kPa",
            "Đánh giá sinh học": stt,
            "Giải pháp kỹ thuật": act
        })
        
    return pd.DataFrame(summary_data)
