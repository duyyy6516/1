import requests

def send_telegram_message(token, chat_id, message):
    """Gửi thông báo khẩn cấp ngầm về Telegram Bot"""
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except Exception:
        return False

def get_quick_solution(vpd_val, vpd_min, vpd_max, hour):
    """Tra cứu nhanh giải pháp kỹ thuật nhà kính dựa theo mốc giờ và trị số"""
    if vpd_val < vpd_min:
        if 7 <= hour < 11:
            return "Mở bạt hông muộn hoặc bật quạt gió để xua tan sương ẩm ban đêm đọng trên lá."
        elif 11 <= hour < 19:
            return "Trời ẩm u hoặc có mưa. Bật quạt đối lưu mạnh, đóng vách ngăn nước mưa và hạn chế tưới gốc dầm dề."
        else:
            return "Ẩm độ ban đêm rất cao. Tuyệt đối không tưới muộn sau 16h; bật thông gió định kỳ."
    elif vpd_min <= vpd_val <= vpd_max:
        return "Môi trường hoàn hảo. Duy trì chế độ thông thoáng tự nhiên và lịch tưới hiện tại của nhà kính."
    else:
        if 7 <= hour < 11:
            return "Nắng lên nhanh làm nhiệt tăng. Kích hoạt nhẹ tưới nhỏ giọt để cấp ẩm vùng rễ."
        elif 11 <= hour < 15:
            return "Cao điểm nắng nóng! Kéo lưới đen cắt nắng (giảm 30%), phun sương mịn định kỳ 5-10 phút/lần."
        elif 15 <= hour < 19:
            return "Nhiệt muộn vẫn cao. Bổ sung một lượt phun sương ngắn để hạ nhiệt trước khi đóng vách kính."
        else:
            return "Hiện tượng nhiệt tăng bất thường ban đêm. Kiểm tra thiết bị sưởi hoặc đóng kín vách ngăn gió."
