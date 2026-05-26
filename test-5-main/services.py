import requests

def send_telegram_message(token, chat_id, text_message):
    """
    Webhook đồng bộ bắn chuỗi thông tin cảnh báo thông minh vượt ngưỡng trực tiếp về máy điện thoại admin.
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
    except:
        return False
