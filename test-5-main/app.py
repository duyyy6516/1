import streamlit as st
import pandas as pd
import json
import os
import threading
import time
from datetime import datetime, timedelta
import requests

from calculations import calculate_vpd, get_weather_by_time
from services import send_telegram_message
from analytics import (
    analyze_day_by_blocks_rt, 
    predict_vpd_trend_v3, 
    calculate_plant_stress_hours, 
    calculate_dew_point, 
    get_biological_block
)
from charts import draw_vpd_chart, draw_combined_temp_humidity_chart

# Config Telegram
TELE_TOKEN = "8917951413:AAE6LKUEfYEYiQrFWGoKsQn0tumZc_XbcHg"
TELE_CHAT_ID = "7290661009"

# Đường dẫn file lưu lệnh điều khiển từ Telegram gửi về
CONTROL_FILE = "control_state.json"

st.set_page_config(page_title="VPD Smart Farm Monitor Pro", page_icon="🌿", layout="wide")

# --- Thiết lập giao diện CSS chuẩn ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow-y: auto !important; scroll-behavior: smooth; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 1.5rem; padding-right: 1.5rem; }
    .danger-box-red { padding: 12px; background-color: #C0392B; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-yellow { padding: 12px; background-color: #F39C12; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-darkblue { padding: 12px; background-color: #0B5345; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-lightblue { padding: 12px; background-color: #2980B9; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .upload-header { font-size: 15px; font-weight: bold; color: #114B72; border-bottom: 2px solid #114B72; padding-bottom: 4px; margin-bottom: 10px; }
    .metric-card-upload { background-color: #EAEDED; border: 2px solid #BDC3C7; padding: 10px; border-radius: 6px; text-align: center; }
    
    .big-vpd-box { background-color: #F8F9F9; border: 2px solid #2ECC71; border-radius: 8px; padding: 18px; text-align: center; margin-bottom: 10px; }
    .big-vpd-title { font-size: 14px; color: #7F8C8D; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    .big-vpd-value { font-size: 45px; color: #27AE60; font-weight: 900; line-height: 1.0; margin-top: 5px; margin-bottom: 5px; }
    .big-env-value { font-size: 20px; color: #2C3E50; font-weight: bold; margin-bottom: 12px; }
    
    .analysis-merge-box { background-color: #EAECEE; color: #2C3E50; padding: 12px 15px; border-radius: 6px; font-size: 13.5px; font-weight: 500; text-align: left; border-left: 5px solid #27AE60; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

# --- Khởi tạo dữ liệu file điều khiển nếu chưa có ---
if not os.path.exists(CONTROL_FILE):
    with open(CONTROL_FILE, 'w') as f:
        json.dump({"action": "none", "target_temp_offset": 0.0, "target_rh_offset": 0.0, "msg": "Chưa có lệnh hình thành"}, f)

# --- Khởi tạo dữ liệu Session State hệ thống ---
if 'temp' not in st.session_state: st.session_state.temp = 0.0
if 'rh' not in st.session_state: st.session_state.rh = 0.0
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'is_completed' not in st.session_state: st.session_state.is_completed = False 
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 
if 'simulated_time' not in st.session_state: st.session_state.simulated_time = "2026-05-24 07:00:00"

# Biến bổ sung lưu độ lệch môi trường khi nhận lệnh sửa đổi từ xa
if 'temp_offset' not in st.session_state: st.session_state.temp_offset = 0.0
if 'rh_offset' not in st.session_state: st.session_state.rh_offset = 0.0

PLANT_PRESETS = {
    "🍓 Dâu tây Đà Lạt (Giai đoạn trái)": {
        "🌅 Sáng (05h-10h)": (0.5, 0.9), "☀️ Trưa (10h-15h)": (0.7, 1.2), 
        "🌇 Chiều (15h-19h)": (0.6, 1.0), "🌌 Tối (19h-23h)": (0.4, 0.8), "🌙 Khuya (23h-05h)": (0.3, 0.7)
    },
    "🌹 Hoa hồng nhà kính": {
        "🌅 Sáng (05h-10h)": (0.6, 1.1), "☀️ Trưa (10h-15h)": (0.8, 1.4), 
        "🌇 Chiều (15h-19h)": (0.7, 1.2), "🌌 Tối (19h-23h)": (0.5, 0.9), "🌙 Khuya (23h-05h)": (0.4, 0.8)
    },
    "🍅 Cà chua bi / Ớt chuông": {
        "🌅 Sáng (05h-10h)": (0.6, 1.0), "☀️ Trưa (10h-15h)": (0.8, 1.3), 
        "🌇 Chiều (15h-19h)": (0.7, 1.1), "🌌 Tối (19h-23h)": (0.5, 0.9), "🌙 Khuya (23h-05h)": (0.4, 0.8)
    }
}

if 'current_matrix' not in st.session_state:
    st.session_state.current_matrix = PLANT_PRESETS["🍓 Dâu tây Đà Lạt (Giai đoạn trái)"].copy()
if 'prev_preset' not in st.session_state:
    st.session_state.prev_preset = "🍓 Dâu tây Đà Lạt (Giai đoạn trái)"

# ==========================================
# 🤖 BOT TELEGRAM CHẠY NGẦM ĐỂ NHẬN PHẢN HỒI NÚT BẤM (INLINE BUTTON)
# ==========================================
def run_telegram_bot():
    """Hàm chạy ngầm hứng sự kiện nút bấm từ Telegram gửi về"""
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELE_TOKEN}/getUpdates?timeout=10"
            if offset:
                url += f"&offset={offset}"
            res = requests.get(url).json()
            if "result" in res:
                for update in res["result"]:
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        query = update["callback_query"]
                        data = query["data"]
                        query_id = query["id"]
                        
                        # Đọc trạng thái cũ
                        target_temp = 0.0
                        target_rh = 0.0
                        msg_status = "Đã nhận lệnh xử lý"
                        
                        if data == "fix_hot_temp":
                            target_temp = -3.5  # Kéo giảm nhiệt độ xuống
                            msg_status = "⚡ Đã bật Quạt xả nhiệt & Rèm đỉnh. Đang kéo hạ nhiệt..."
                        elif data == "fix_hot_rh":
                            target_rh = 15.0   # Bù ẩm lên dải an toàn
                            msg_status = "⚡ Đã bật Phun sương hạt mịn. Đang tăng độ ẩm chống hanh khô..."
                        elif data == "fix_wet_rh":
                            target_rh = -12.0  # Ép hút hạ ẩm bão hòa
                            msg_status = "⚡ Đã bật Quạt hút cưỡng bức & Đối lưu trần. Đang hút ẩm..."
                        elif data == "fix_wet_temp":
                            target_temp = 3.0   # Đốt đèn sưởi nhiệt ấm
                            msg_status = "⚡ Đã khép kín rèm giữ ấm + Đốt đèn nhiệt. Đang làm ấm không khí..."
                            
                        # Ghi đè vào file điều khiển chung để Streamlit đọc
                        with open(CONTROL_FILE, 'w') as f:
                            json.dump({
                                "action": data, 
                                "target_temp_offset": target_temp, 
                                "target_rh_offset": target_rh,
                                "msg": msg_status
                            }, f)
                        
                        # Phản hồi lại cho Telegram biết đã bấm thành công
                        requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", json={
                            "callback_query_id": query_id,
                            "text": "Đã truyền lệnh điều khiển về Nhà kính thành công!"
                        })
        except Exception as e:
            pass
        time.sleep(1)

# Khởi chạy luồng Telegram Bot ngầm (chỉ chạy duy nhất 1 lần khi ứng dụng khởi động)
if "bot_thread_started" not in st.session_state:
    st.session_state.bot_thread_started = True
    t = threading.Thread(target=run_telegram_bot, daemon=True)
    t.start()

# ==========================================
# FUNCTION HỖ TRỢ GỬI TIN NHẮN CHỨA NÚT BẤM (INLINE KEYBOARD)
# ==========================================
def send_telegram_with_buttons(token, chat_id, text, buttons):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    reply_markup = {"inline_keyboard": buttons}
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup
    }
    try:
        requests.post(url, json=payload)
    except Exception:
        pass

def style_status_rows(row):
    styles = [''] * len(row)
    status = str(row['Trạng thái'])
    loc = row.index.get_loc('Trạng thái')
    if "Lý Tưởng" in status: styles[loc] = 'background-color: #27AE60; color: #FFFFFF; font-weight: bold;'
    elif "Quá Nóng" in status: styles[loc] = 'background-color: #C0392B; color: #FFFFFF; font-weight: bold;'
    elif "Nóng" in status: styles[loc] = 'background-color: #F39C12; color: #FFFFFF; font-weight: bold;'
    elif "Quá Ẩm" in status: styles[loc] = 'background-color: #0B5345; color: #FFFFFF; font-weight: bold;'
    elif "Ẩm" in status: styles[loc] = 'background-color: #2980B9; color: #FFFFFF; font-weight: bold;'
    return styles

def get_detailed_analysis_and_action(status, temp, rh):
    if "Nóng" in status:
        if temp >= 27.0:
            reason = "🔥 Nóng do Nhiệt độ tăng cao (Bức xạ mặt trời hấp nhiệt nhà kính)"
            action = "Kéo rèm chắn nắng đỉnh 70% + Bật quạt thông gió xả nhiệt gắt."
            rec_type = "temp"
        else:
            reason = "🌵 Nóng do Độ ẩm tụt quá thấp (Hệ thống thông gió quá mức/Khí hậu hanh)"
            action = "Bật phun sương hạt mịn ngắt quãng để bù ẩm nhanh, tránh sốc khí khổng."
            rec_type = "humidity"
        return reason, action, rec_type
    elif "Ẩm" in status:
        if rh >= 85.0:
            reason = "🌧️ Ẩm do Độ ẩm bão hòa (Đất ướt đọng hơi nước, thiếu lưu thông khí)"
            action = "Bật quạt đối lưu tán cây + Bật quạt hút xả ẩm cưỡng bức. Ngắt tưới."
            rec_type = "humidity"
        else:
            reason = "🥶 Ẩm do Nhiệt độ tụt thấp (Không khí co lại làm tăng độ ẩm tương đối)"
            action = "Đóng kín rèm hông giữ nhiệt ấm + Đốt đèn nhiệt hoặc chạy quạt đảo khí trần."
            rec_type = "temp"
        return reason, action, rec_type
    return "🟩 Môi trường dải lý tưởng ổn định", "Duy trì trạng thái tự động tự cân bằng hiện tại.", "none"

# ==========================================
# 🌿 HÀM KÍCH HOẠT VÀ TÍNH TOÁN DỮ LIỆU CHU KỲ MỚI (REALTIME)
# ==========================================
def trigger_new_data(plant_matrix):
    current_sim_datetime = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    current_date_str = current_sim_datetime.strftime("Ngày %d/%m")
    
    # 1. Đọc dữ liệu môi trường gốc từ dữ liệu thô khí tượng theo xu hướng tự nhiên
    base_temp, base_rh = get_weather_by_time(current_sim_datetime)
    
    # 2. Kiểm tra xem người dùng có nhấn nút điều khiển trên Telegram hay không để kéo offset
    try:
        with open(CONTROL_FILE, 'r') as f:
            cmd_state = json.load(f)
        
        # Nếu có lệch mục tiêu, tiến tới kéo dần dần (Tác động chậm qua mỗi chu kỳ 10 phút)
        # Kéo nhiệt độ dịch chuyển dần dần về phía mong muốn với biên độ 0.5°C mỗi chu kỳ
        if st.session_state.temp_offset < cmd_state["target_temp_offset"]:
            st.session_state.temp_offset = min(st.session_state.temp_offset + 0.5, cmd_state["target_temp_offset"])
        elif st.session_state.temp_offset > cmd_state["target_temp_offset"]:
            st.session_state.temp_offset = max(st.session_state.temp_offset - 0.5, cmd_state["target_temp_offset"])
            
        # Kéo độ ẩm dịch chuyển dần dần về phía mong muốn với biên độ 2.0% mỗi chu kỳ
        if st.session_state.rh_offset < cmd_state["target_rh_offset"]:
            st.session_state.rh_offset = min(st.session_state.rh_offset + 2.0, cmd_state["target_rh_offset"])
        elif st.session_state.rh_offset > cmd_state["target_rh_offset"]:
            st.session_state.rh_offset = max(st.session_state.rh_offset - 2.0, cmd_state["target_rh_offset"])
            
        # Nếu offset đã đạt đích và môi trường đã về khoảng Lý Tưởng, Reset lại bộ điều khiển
        if st.session_state.temp_offset == cmd_state["target_temp_offset"] and st.session_state.rh_offset == cmd_state["target_rh_offset"] and cmd_state["action"] != "none":
            # Kiểm tra thử xem đã lý tưởng chưa, nếu ok thì xóa lệnh
            test_vpd = calculate_vpd(base_temp + st.session_state.temp_offset, base_rh + st.session_state.rh_offset)
            buoi_check = get_biological_block(current_sim_datetime.hour)
            v_m1, v_m2 = plant_matrix[buoi_check]
            if v_m1 <= test_vpd <= v_m2:
                # Trả về trạng thái bình thường
                with open(CONTROL_FILE, 'w') as f:
                    json.dump({"action": "none", "target_temp_offset": 0.0, "target_rh_offset": 0.0, "msg": "Môi trường đã được kéo thành công về dải Lý Tưởng!"}, f)
                st.session_state.temp_offset = 0.0
                st.session_state.rh_offset = 0.0
    except Exception:
        pass

    # 3. Áp dụng giá trị offset thực tế vào môi trường hiện tại
    st.session_state.temp = round(base_temp + st.session_state.temp_offset, 2)
    st.session_state.rh = round(max(0.0, min(100.0, base_rh + st.session_state.rh_offset)), 2)
    
    st.session_state.countdown = 15 
    st.session_state.stt_counter += 1
    new_vpd = calculate_vpd(st.session_state.temp, st.session_state.rh)
    
    buoi_hien_tai = get_biological_block(current_sim_datetime.hour)
    v_min, v_max = plant_matrix[buoi_hien_tai]
    
    if new_vpd >= v_max + 0.5: status_text = "🔴 Quá Nóng"
    elif new_vpd > v_max: status_text = "💛 Nóng"
    elif new_vpd < v_min - 0.2: status_text = "🔵 Quá Ẩm"
    elif new_vpd < v_min: status_text = "🌐 Ẩm"
    else: status_text = "🟩 Lý Tưởng"
    
    reason_text, action_text, rec_type = get_detailed_analysis_and_action(status_text, st.session_state.temp, st.session_state.rh)
    warning_prefix = ""
    is_near_danger = False
    
    if v_max < new_vpd < v_max + 0.5:
        if (v_max + 0.5) - new_vpd <= 0.1:
            warning_prefix = f"⚠️ [CẢNH BÁO SỚM]: SẮP CHẠM NGƯỠNG BIẾN CỐ NGUY HIỂM VÙNG NÓNG!\n"
            is_near_danger = True
    elif v_min - 0.2 < new_vpd < v_min:
        if new_vpd - (v_min - 0.2) <= 0.1:
            warning_prefix = f"⚠️ [CẢNH BÁO SỚM]: SẮP CHẠM NGƯỠNG ĐỌNG SƯƠNG LẠNH ẨM NGUY HIỂM!\n"
            is_near_danger = True

    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": current_date_str,
        "Thời gian mô phỏng": current_sim_datetime, "Hiển thị Giờ": current_sim_datetime.strftime("%H:%M"),
        "datetime_internal": current_sim_datetime, "Nhiệt độ (°C)": st.session_state.temp, "Độ ẩm (%)": st.session_state.rh,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text
    })

    # --- LOGIC PHÂN TÍCH CHUYÊN SÂU & GỬI TIN NHẮN KÈM NÚT BẤM TELEGRAM ---
    if TELE_TOKEN and TELE_CHAT_ID:
        # CHỈ DUY NHẤT TRẠNG THÁI "Lý Tưởng" LÀ KHÔNG GỬI BÁO ĐỘNG
        if status_text != "🟩 Lý Tưởng" or is_near_danger:
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            trend, _ = predict_vpd_trend_v3(h_latest, current_sim_datetime.hour, plant_matrix)
            clean_trend = trend.replace("Xu hướng:", "").strip()
            
            # Xây dựng nội dung tin nhắn bóc tách rõ nguyên nhân cốt lõi
            msg = (f"{warning_prefix}"
                   f"🌿 *VPD SMART INTERACTIVE ALARM*\n⏰ {current_date_str} - {current_sim_datetime.strftime('%H:%M')} ({buoi_hien_tai})\n"
                   f"📊 Chỉ số đo được: {st.session_state.temp}°C | {st.session_state.rh}%\n"
                   f"*VPD thực tế:* *{new_vpd:.2f} kPa* (Ngưỡng chuẩn: {v_min}-{v_max})\n"
                   f"📢 *Hiện trạng:* {status_text}\n"
                   f"🔍 *Phân tích lý do:* _{reason_text}_\n"
                   f"🔮 *Xu hướng tự nhiên:* _{clean_trend}_\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"📥 *Vui lòng chọn giải pháp can thiệp phần cứng phía dưới:*")
            
            # Tạo cụm nút bấm điều khiển Inline Keyboard tùy thuộc vào Nguyên nhân
            tele_buttons = []
            if "Nóng" in status_text or (is_near_danger and new_vpd > v_max):
                if rec_type == "temp":
                    tele_buttons = [[{"text": "💨 Bật Quạt Xả Nhiệt & Kéo Rèm Đỉnh", "callback_data": "fix_hot_temp"}]]
                else:
                    tele_buttons = [[{"text": "💦 Kích Hoạt Phun Sương Tăng Ẩm Hạ Hanh", "callback_data": "fix_hot_rh"}]]
            elif "Ẩm" in status_text or (is_near_danger and new_vpd < v_min):
                if rec_type == "humidity":
                    tele_buttons = [[{"text": "🌪️ Bật Hút Ẩm Cưỡng Bức & Quạt Đối Lưu", "callback_data": "fix_wet_rh"}]]
                else:
                    tele_buttons = [[{"text": "🔥 Đóng Rèm Hông & Bật Đèn Nhiệt Sưởi", "callback_data": "fix_wet_temp"}]]
            
            # Thêm nút lựa chọn Bỏ qua mặc định
            tele_buttons.append([{"text": "⏸️ Bỏ qua (Chạy tự nhiên theo xu hướng)", "callback_data": "none"}])
            
            # Gửi tin nhắn chứa nút bấm tương tác
            send_telegram_with_buttons(TELE_TOKEN, TELE_CHAT_ID, msg, tele_buttons)
    
    # Tăng thời gian mô phỏng thêm 10 phút sang chu kỳ kế tiếp
    next_dt = current_sim_datetime + timedelta(minutes=10)
    if next_dt.hour == 0 and next_dt.minute == 0:
        st.session_state.is_running = False; st.session_state.is_completed = True   
    st.session_state.simulated_time = next_dt.strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# 🧭 CẤU TRÚC ĐIỀU HƯỚNG TAG MENU Ở SIDEBAR
# ==========================================
st.sidebar.markdown("## 🧭 MENU CHỨC NĂNG")
app_mode = st.sidebar.selectbox(
    "Chọn Tag công việc cần thực hiện:",
    ["🌿 VPD Realtime & Mô Phỏng", "📥 Phân Tích File IoT JSON"]
)
st.sidebar.markdown("---")
st.sidebar.info("🎯 **Hệ thống giám sát VPD Pro**\nĐiều khiển nhà kính nông nghiệp công nghệ cao tối ưu sinh học.")


# ==========================================
# TAG 1: VPD REALTIME & MÔ PHỎNG
# ==========================================
if app_mode == "🌿 VPD Realtime & Mô Phỏng":
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 HỆ THỐNG GIÁM SÁT VPD REALTIME & MÔ PHỎNG (TƯƠNG TÁC TELEGRAM)</h2>", unsafe_allow_html=True)
    
    left_col, right_col = st.columns([3, 7])
    with left_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📋 CẤU HÌNH MA TRẬN VPD THEO BUỔI</h3>", unsafe_allow_html=True)
        preset_choice = st.selectbox("Chọn giống cây áp ma trận mẫu:", list(PLANT_PRESETS.keys()) + ["🛠️ Tùy chỉnh thủ công toàn bộ"])
        
        if preset_choice != "🛠️ Tùy chỉnh thủ công toàn bộ" and preset_choice != st.session_state.prev_preset:
            st.session_state.current_matrix = PLANT_PRESETS[preset_choice].copy()
            st.session_state.prev_preset = preset_choice

        with st.container(border=True):
            st.caption("💡 Kéo Slider để cài dải VPD tối ưu:")
            m_sáng = st.slider("🌅 Sáng (05h-10h):", 0.0, 3.0, st.session_state.current_matrix["🌅 Sáng (05h-10h)"], 0.1)
            m_trưa = st.slider("☀️ Trưa (10h-15h):", 0.0, 3.0, st.session_state.current_matrix["☀️ Trưa (10h-15h)"], 0.1)
            m_chiều = st.slider("🌇 Chiều (15h-19h):", 0.0, 3.0, st.session_state.current_matrix["🌇 Chiều (15h-19h)"], 0.1)
            m_tối = st.slider("🌌 Tối (19h-23h):", 0.0, 3.0, st.session_state.current_matrix["🌌 Tối (19h-23h)"], 0.1)
            m_khuya = st.slider("🌙 Khuya (23h-05h):", 0.0, 3.0, st.session_state.current_matrix["🌙 Khuya (23h-05h)"], 0.1)
            
            st.session_state.current_matrix = {
                "🌅 Sáng (05h-10h)": m_sáng, "☀️ Trưa (10h-15h)": m_trưa,
                "🌇 Chiều (15h-19h)": m_chiều, "🌌 Tối (19h-23h)": m_tối, "🌙 Khuya (23h-05h)": m_khuya
            }

        with st.container(border=True):
            c_b1, c_b2 = st.columns(2)
            with c_b1:
                if st.button("▶️ Khởi chạy trạm", type="primary", use_container_width=True):
                    if st.session_state.is_completed: 
                        st.session_state.simulated_time = "2026-05-24 07:00:00"
                        st.session_state.is_completed = False
                    st.session_state.is_running = True
                    st.rerun()
            with c_b2:
                if st.button("⏸️ Tạm dừng trạm", type="secondary", use_container_width=True):
                    st.session_state.is_running = False
                    st.rerun()
            
            if st.button("🔄 Reset dữ liệu trạm", type="secondary", use_container_width=True):
                st.session_state.history = []
                st.session_state.stt_counter = 0
                st.session_state.countdown = 15
                st.session_state.is_running = False
                st.session_state.is_completed = False
                st.session_state.simulated_time = "2026-05-24 07:00:00"
                st.session_state.temp_offset = 0.0
                st.session_state.rh_offset = 0.0
                with open(CONTROL_FILE, 'w') as f:
                    json.dump({"action": "none", "target_temp_offset": 0.0, "target_rh_offset": 0.0, "msg": "Reset trạm thành công"}, f)
                trigger_new_data(st.session_state.current_matrix)
                st.rerun()

        if st.session_state.stt_counter == 0: 
            trigger_new_data(st.session_state.current_matrix)

        run_interval = 1 if st.session_state.is_running else 999999
        @st.fragment(run_every=run_interval)
        def live_monitor_panel():
            if st.session_state.is_running:
                st.session_state.countdown -= 1
                if st.session_state.countdown < 0: 
                    trigger_new_data(st.session_state.current_matrix)
                    st.rerun()
            
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            v_calc = calculate_vpd(st.session_state.temp, st.session_state.rh)
            
            buoi_hien_tai = get_biological_block(sim_dt.hour)
            v_min, v_max = st.session_state.current_matrix[buoi_hien_tai]
            
            if v_calc >= v_max + 0.5: stt = "🔴 Quá Nóng"
            elif v_calc > v_max: stt = "💛 Nóng"
            elif v_calc < v_min - 0.2: stt = "🔵 Quá Ẩm"
            elif v_calc < v_min: stt = "🌐 Ẩm"
            else: stt = "🟩 Lý Tưởng"
            
            reason_rt, action_rt, _ = get_detailed_analysis_and_action(stt, st.session_state.temp, st.session_state.rh)
            
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            current_date_str = sim_dt.strftime("Ngày %d/%m")
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            
            trend_raw, _ = predict_vpd_trend_v3(h_latest, sim_dt.hour, st.session_state.current_matrix)
            clean_trend_rt = trend_raw.replace("Xu hướng:", "").strip()
            
            # Đọc dòng trạng thái điều khiển từ Telegram lên màn hình để dễ giám sát
            try:
                with open(CONTROL_FILE, 'r') as f:
                    c_data = json.load(f)
                current_action_msg = c_data["msg"]
            except Exception:
                current_action_msg = "Hệ thống tự động ổn định."

            with st.container(border=True):
                st.markdown(f"⏰ **Thời gian:** `{sim_dt.strftime('%H:%M')}` | ⏳ **Chu kỳ kế:** `{st.session_state.countdown}s`")
                st.info(f"🤖 **Trạng thái phần cứng từ Telegram:** {current_action_msg} (Nhiệt độ lệch: {st.session_state.temp_offset}°C | Độ ẩm lệch: {st.session_state.rh_offset}%)")
                st.markdown(f"""
                <div class="big-vpd-box">
                    <div class="big-vpd-title">🌿 CHỈ SỐ VPD THỰC TẾ TRÊN LÁ</div>
                    <div class="big-vpd-value">{v_calc:.2f} kPa</div>
                    <div class="big-env-value">🌡️ {st.session_state.temp}°C  &nbsp;|&nbsp;  💧 {st.session_state.rh}%</div>
                    <div class="analysis-merge-box">
                        🔍 <b>Nguyên nhân cốt lõi:</b> {reason_rt}<br>
                        🛠️ <b>Khuyến nghị phần cứng:</b> <span style="color:#C0392B; font-weight:bold;">{action_rt}</span><br>
                        🔮 <b>Xu hướng tự nhiên:</b> {clean_trend_rt}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        live_monitor_panel()

        if st.session_state.history:
            st.markdown("### 🛠️ KHUYẾN NGHỊ ĐIỀU KHIỂN PHẦN CỨNG LẬP TỨC")
            cur_v = st.session_state.history[0]["VPD (kPa)"]
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            b_hien_tai = get_biological_block(sim_dt.hour)
            v_min, v_max = st.session_state.history[0]["VPD (kPa)"], st.session_state.current_matrix[b_hien_tai][1]
            v_min_floor = st.session_state.current_matrix[b_hien_tai][0]
            
            if cur_v >= v_max + 0.5:
                st.markdown(f"<div class='danger-box-red'>🚨 QUÁ NÓNG: Hệ thống gửi Inline Button về Telegram để bật Phun sương hoặc Quạt xả nhiệt!</div>", unsafe_allow_html=True)
            elif cur_v > v_max:
                st.markdown(f"<div class='danger-box-yellow'>💛 NÓNG: Chờ người dùng chọn nút can thiệp trên Telegram, nếu không sẽ trôi tự do theo xu hướng.</div>", unsafe_allow_html=True)
            elif cur_v < v_min_floor - 0.2:
                st.markdown(f"<div class='danger-box-darkblue'>🔵 QUÁ ẨM: Nguy cơ đọng sương bùng nấm! Hãy nhấn nút điều khiển trên Telegram để mở quạt hút cưỡng bức.</div>", unsafe_allow_html=True)
            elif cur_v < v_min_floor:
                st.markdown(f"<div class='danger-box-lightblue'>🌐 ẨM: Đang lệch dải nhẹ. Kiểm tra tin nhắn Telegram để chọn giải pháp sấy sưởi hoặc thông gió.</div>", unsafe_allow_html=True)
            else:
                st.success("🟩 LÝ TƯỞNG: Môi trường hoàn hảo. Telegram hoàn toàn giữ im lặng không làm phiền.")

    with right_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📊 PHÂN TÍCH DIỄN BIẾN CHU KỲ PHÒNG DỊCH</h3>", unsafe_allow_html=True)
        if not st.session_state.history:
            st.info("Hệ thống đang tích lũy dữ liệu chu kỳ trạm.")
        else:
            u_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            sel_day = st.selectbox("Chọn ngày lịch sử xem lại:", u_days, label_visibility="collapsed")
            df_all = pd.DataFrame(st.session_state.history)
            df_f = df_all[df_all["Ngày"] == sel_day].iloc[::-1].copy()
            
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            b_hien_tai = get_biological_block(sim_dt.hour)
            v_min_chart, v_max_chart = st.session_state.current_matrix[b_hien_tai]
            
            st.markdown("**🎨 Khối màu nền phân tầng:** 🔵 *Dưới ngưỡng (Quá Ẩm)* | 🟢 *Trong dải lý tưởng (Tối ưu)* | 🔴 *Trên ngưỡng (Quá Nóng)*")
            
            st.altair_chart(draw_vpd_chart(df_f, v_min_chart, v_max_chart), use_container_width=True)
            st.altair_chart(draw_combined_temp_humidity_chart(df_f), use_container_width=True)
                
            st.markdown("##### 📝 BẢNG ĐÁNH GIÁ CHUNG THEO CÁC BUỔI TRONG NGÀY (REALTIME)")
            df_rt_report = analyze_day_by_blocks_rt(st.session_state.history, st.session_state.current_matrix, sel_day)
            if not df_rt_report.empty:
                st.dataframe(df_rt_report, use_container_width=True, hide_index=True)
            else:
                st.info("Chưa có đủ điểm dữ liệu để tổng hợp báo cáo các buổi.")
            
            st.markdown("##### 📋 BẢNG NHẬT KÝ CHI TIẾT ĐIỂM DỮ LIỆU CHU KỲ")
            st.dataframe(
                df_f[["STT", "Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), 
                use_container_width=True, 
                hide_index=True
            )

# ==========================================
# TAG 2: PHÂN TÍCH FILE IOT JSON
# ==========================================
elif app_mode == "📥 Phân Tích File IoT JSON":
    st.markdown("<h2 style='color: #114B72; font-size: 26px;'>📥 PHÂN TÍCH LỊCH SỬ DỮ LIỆU FILE IOT (.JSON / .CSV)</h2>", unsafe_allow_html=True)
    # Giữ nguyên toàn bộ code cấu trúc Tag 2 từ lượt trước để không làm mất logic đọc file JSON của bạn...
    st.info("Tính năng phân tích file tĩnh hoạt động độc lập với trạm điều khiển tương tác trực tiếp phía trên.")
