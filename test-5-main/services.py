import requests

def send_telegram_message(token: str, chat_id: str, message: str) -> bool:
    """
    Gửi thông báo cảnh báo VPD qua Telegram Bot API
    """
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"  # Giữ nguyên các định dạng **chữ đậm** và *chữ nghiêng*
        }
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def get_quick_solution(vpd: float, vpd_min: float, vpd_max: float, hour: int) -> str:
    """
    Trả về giải pháp xử lý vi khí hậu nhanh dựa trên giá trị VPD và mốc thời gian
    """
    if vpd < vpd_min:
        if 6 <= hour <= 17:
            return "Trời ẩm - Ban ngày: Bật quạt đối lưu, mở bạt mái thông gió, dừng phun sương."
        else:
            return "Trời ẩm - Ban đêm: Bật quạt gió, kích hoạt hệ thống sưởi nâng nhiệt nhẹ nếu cần."
    
    elif vpd > vpd_max:
        if 10 <= hour <= 15:
            return "Trời khô - Trưa nắng gắt: Kéo lưới cắt nắng, bật phun sương làm mát mịn áp suất cao."
        else:
            return "Trời khô - Giờ thấp điểm: Bật phun sương boong, tưới bù ẩm nhẹ cho nền sàn."
            
    return "Môi trường hoàn hảo: Duy trì trạng thái thông thoáng hiện tại cho nhà kính."
