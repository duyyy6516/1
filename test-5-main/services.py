import requests

def send_telegram_message(token, chat_id, text_message):
    """
    Cổng kết nối Webhook gửi tin nhắn cảnh báo vượt ngưỡng thông minh
    trực tiếp từ trạm cảm biến IoT về máy điện thoại qua Telegram.
    """
    if not token or not chat_id:
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Lỗi kết nối API Bot Telegram: {e}")
        return False
