import pandas as pd
from datetime import datetime

def analyze_day_by_blocks_rt(history_list, vpd_min, vpd_max, target_date_str):
    """Tính toán số liệu trung bình theo từng buổi sáng, trưa, chiều, tối"""
    day_data = [r for r in history_list if r["Ngày"] == target_date_str]
    
    blocks = {
        "🌅 Sáng (07h-11h)": [],
        "☀️ Trưa (11h-15h)": [],
        "🌤️ Chiều (15h-19h)": [],
        "🌙 Tối (19h-24h)": []
    }
    
    for r in day_data:
        time_obj = datetime.strptime(r["Hiển thị Giờ"], "%H:%M")
        hour = time_obj.hour
        vpd_val = r["VPD (kPa)"]
        
        if 7 <= hour < 11:
            blocks["🌅 Sáng (07h-11h)"].append(vpd_val)
        elif 11 <= hour < 15:
            blocks["☀️ Trưa (11h-15h)"].append(vpd_val)
        elif 15 <= hour < 19:
            blocks["🌤️ Chiều (15h-19h)"].append(vpd_val)
        else:
            blocks["🌙 Tối (19h-24h)"].append(vpd_val)
            
    summary = []
    for block_name, vpd_list in blocks.items():
        if vpd_list:
            avg_vpd = sum(vpd_list) / len(vpd_list)
            if avg_vpd < vpd_min:
                danh_gia = "🟦 Quá ẩm"
                huong_xu_ly = "Mở bạt hông muộn hoặc bật quạt gió xua tan sương ẩm" if "Sáng" in block_name else "Bật đối lưu mạnh, giảm tưới"
            elif vpd_min <= avg_vpd <= vpd_max:
                danh_gia = "🟩 Lý tưởng"
                huong_xu_ly = "Môi trường hoàn hảo. Duy trì thông thoáng tự nhiên."
            else:
                danh_gia = "🟥 Quá khô"
                huong_xu_ly = "Cấp ẩm vùng rễ" if "Sáng" in block_name else "Kéo lưới đen, phun sương hạ nhiệt gấp"
            
            summary.append({
                "Khoảng Thời Gian": block_name,
                "VPD TB (kPa)": round(avg_vpd, 2),
                "Đánh Giá": danh_gia,
                "Hướng Xử Lý Đề Xuất": huong_xu_ly
            })
        else:
            summary.append({
                "Khoảng Thời Gian": block_name,
                "VPD TB (kPa)": "--",
                "Đánh Giá": "⚪ Đang chờ mốc giờ...",
                "Hướng Xử Lý Đề Xuất": "Chưa có dữ liệu thu thập cho buổi này."
            })
    return pd.DataFrame(summary)

def predict_vpd_trend_v3(filtered_history, current_hour, vpd_min, vpd_max):
    """
    THUẬT TOÁN DỰ BÁO TOÁN HỌC CHÍNH XÁC CAO:
    Dựa trên độ dốc biến thiên dữ liệu (Delta VPD) kết hợp chu kỳ thời tiết Đà Lạt.
    Phát hiện sớm trạng thái SẮP CHẠM NGƯỠNG để đẩy cảnh báo mạnh lên.
    """
    if len(filtered_history) < 2:
        return "🔄 Hệ thống đang tích lũy dữ liệu mốc giờ để tính toán...", "info"
    
    # Lấy 2 mốc dữ liệu realtime gần nhất để tính độ dốc Delta
    current_vpd = filtered_history[0]["VPD (kPa)"]
    prev_vpd = filtered_history[1]["VPD (kPa)"]
    delta_vpd = current_vpd - prev_vpd  # Tốc độ thay đổi sau 10 phút
    
    # TH LÀM MẠNH CẢNH BÁO 1: Sắp chạm đáy nguy hiểm (Quá Ẩm)
    if current_vpd > vpd_min and (current_vpd - vpd_min) <= 0.12:
        if delta_vpd < 0: # Đi xuống nguy hiểm
            return f"⚠️ CẢNH BÁO SỚM: Chỉ số đang lao dốc nhanh (Δ:{delta_vpd:.2f}). Sắp chạm ngưỡng QUÁ ẨM nguy hiểm trong 10-20 phút tới! Cần chuẩn bị bật quạt đối lưu hoặc giảm tưới.", "danger_blue"
            
    # TH LÀM MẠNH CẢNH BÁO 2: Sắp chạm trần nguy hiểm (Quá Khô)
    if current_vpd < vpd_max and (vpd_max - current_vpd) <= 0.12:
        if delta_vpd > 0: # Đi lên nguy hiểm
            return f"🔥 CẢNH BÁO SỚM: Chỉ số đang tăng phi mã (Δ:+{delta_vpd:.2f}). Sắp vượt ngưỡng QUÁ KHÔ bốc hơi nước lá trong mốc giờ tới! Cần chuẩn bị kéo lưới cắt nắng hoặc kích hoạt phun sương.", "danger_red"

    # Dự báo thông thường dựa theo toán học Delta kết hợp mốc giờ tự nhiên Đà Lạt
    trend_text = ""
    if delta_vpd > 0.03:
        trend_text = f"📈 Xu hướng thực tế: Chỉ số đang tăng mạnh (+{delta_vpd:.2f} kPa/10p). "
    elif delta_vpd < -0.03:
        trend_text = f"📉 Xu hướng thực tế: Chỉ số đang sụt giảm nhanh ({delta_vpd:.2f} kPa/10p). "
    else:
        trend_text = "⚖️ Xu hướng thực tế: Chỉ số đang đi ngang ổn định. "

    if 7 <= current_hour < 11:
        return trend_text + "Chu kỳ sáng: Nắng đang lên nhanh, bức xạ nhiệt tăng, ẩm độ rớt sâu.", "warning"
    elif 11 <= current_hour < 15:
        return trend_text + "Chu kỳ trưa: Đạt đỉnh bức xạ. Môi trường khô nóng gắt.", "error"
    elif 15 <= current_hour < 19:
        return trend_text + "Chu kỳ chiều muộn: Nắng tắt, nhiệt độ hạ nhanh, ẩm độ không khí đảo chiều tăng mạnh.", "success"
    else:
        return trend_text + "Chu kỳ đêm: Không có bức xạ, trời lạnh ẩm sâu, tiến sát mốc bão hòa rủi ro nấm bệnh.", "info"
