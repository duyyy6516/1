import requests

def send_discord_message(webhook_url: str, message: str) -> bool:
    """
    Gửi thông báo cảnh báo VPD qua Discord Webhook
    """
    if not webhook_url:
        return False
    try:
        payload = {
            "content": message
        }
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code in [200, 204]
    except Exception:
        return False

def get_quick_solution(vpd: float, vpd_min: float, vpd_max: float, hour: int, temp: float = 0.0, rh: float = 0.0) -> str:
    """
    Trả về giải pháp xử lý vi khí hậu nhanh dựa trên giá trị VPD và mốc thời gian
    """
    if vpd < vpd_min:
        if 6 <= hour <= 17:
            return f"Trời ẩm ({temp}°C, {rh}%) - Ban ngày: Bật quạt đối lưu, mở bạt mái thông gió, dừng phun sương."
        else:
            return f"Trời ẩm ({temp}°C, {rh}%) - Ban đêm: Bật quạt gió, kích hoạt hệ thống sưởi nâng nhiệt nhẹ nếu cần."
    
    elif vpd > vpd_max:
        if 10 <= hour <= 15:
            return f"Trời khô ({temp}°C, {rh}%) - Trưa nắng gắt: Kéo lưới cắt nắng, bật phun sương làm mát mịn áp suất cao."
        else:
            return f"Trời khô ({temp}°C, {rh}%) - Ban đêm/Chiều: Đóng bạt chắn gió ngoài, phun sương bù ẩm nhẹ hạt."
            
    return "Môi trường tối ưu: Duy trì trạng thái ổn định hiện tại của nhà kính."
