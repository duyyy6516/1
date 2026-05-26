import requests

def send_telegram_message(token: str, chat_id: str, message: str) -> bool:
    """
    Gửi thông báo cảnh báo VPD và lệnh điều hành trực tiếp qua Telegram Bot
    """
    if not token or not chat_id:
        return False
    try:
        # Cấu hình endpoint API gửi tin nhắn của Telegram
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"  # Giúp tin nhắn hiển thị định dạng đậm/nghiêng đẹp mắt
        }
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def get_quick_solution(vpd: float, vpd_min: float, vpd_max: float, hour: int, temp: float = 20.0, rh: float = 70.0) -> str:
    """
    Trả về giải pháp xử lý vi khí hậu bóc tách rõ nguyên nhân:
    - Quá ẩm do: Nhiệt thấp hay Độ ẩm cao
    - Quá khô do: Nhiệt cao hay Độ ẩm thấp
    """
    # ==================== TRƯỜNG HỢP VPD QUÁ ẨM (VPD < Ngưỡng tối thiểu) ====================
    if vpd < vpd_min:
        # Kịch bản 1: Ẩm do nhiệt độ thấp (Thường ban đêm/rạng sáng ở Đà Lạt)
        if temp < 18.0:
            return "Trời ẩm do NHIỆT THẤP: Đóng bạt hông/mái giữ nhiệt, bật đèn/hệ thống sưởi, dừng hoàn toàn quạt hút làm mát."
        
        # Kịch bản 2: Ẩm do độ ẩm không khí quá cao (Môi trường bão hòa hơi nước sau mưa)
        elif rh > 85.0:
            return "Trời ẩm do ĐỘ ẨM CAO: Bật mạnh quạt đối lưu nội bộ xé màng ẩm trên lá, mở thông gió nếu trời không mưa, CẤM phun sương."
        
        else:
            return "Trời ẩm nhẹ: Bật quạt lưu thông không khí, giảm tưới gốc, dừng phun sương."

    # ==================== TRƯỜNG HỢP VPD QUÁ KHÔ (VPD > Ngưỡng tối đa) ====================
    elif vpd > vpd_max:
        # Kịch bản 3: Khô do NHIỆT ĐỘ QUÁ CAO (Trưa nắng gắt gao - Gây stress nhiệt)
        if temp >= 28.0:
            return "Trời khô do NHIỆT CAO: Kéo ngay lưới cắt nắng để hạ nhiệt mặt lá, bật quạt hút thông gió kết hợp phun sương hạt mịn áp suất cao."
        
        # Kịch bản 4: Khô do ĐỘ ẨM TỤT QUÁ SÂU (Gió hanh khô, độ ẩm môi trường quá thấp)
        elif rh < 45.0:
            return "Trời khô do ĐỘ ẨM THẤP: Bật phun sương bù ẩm hệ thống, tăng lưu lượng tưới nhỏ giọt cấp nước cho rễ, đóng bớt bạt hông đón hướng gió hanh."
        
        else:
            return "Trời khô nhẹ: Bật phun sương bù ẩm chu kỳ ngắn, kiểm tra độ ẩm giá thể cây."
            
    # ==================== TRƯỜNG HỢP VPD LÝ TƯỞNG ====================
    return "Khí hậu lý tưởng: Duy trì trạng thái ổn định, cây đang mở khí khổng quang hợp tốt."
