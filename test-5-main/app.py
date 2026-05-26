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

# File lưu trạng thái liên lạc 2 chiều giữa Tele và Streamlit
CONTROL_FILE = "control_state.json"

st.set_page_config(page_title="VPD Smart Farm Monitor Pro", page_icon="🌿", layout="wide")

# --- CSS Giao diện ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow-y: auto !important; scroll-behavior: smooth; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 1.5rem; padding-right: 1.5rem; }
    .danger-box-red { padding: 12px; background-color: #C0392B; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-yellow { padding: 12px; background-color: #F39C12; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-darkblue { padding: 12px; background-color: #0B5345; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-lightblue { padding: 12px; background-color: #2980B9; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    
    .big-vpd-box { background-color: #F8F9F9; border: 2px solid #2ECC71; border-radius: 8px; padding: 18px; text-align: center; margin-bottom: 10px; }
    .big-vpd-title { font-size: 14px; color: #7F8C8D; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    .big-vpd-value { font-size: 45px; color: #27AE60; font-weight: 900; line-height: 1.0; margin-top: 5px; margin-bottom: 5px; }
    .big-env-value { font-size: 20px; color: #2C3E50; font-weight: bold; margin-bottom: 12px; }
    
    .analysis-merge-box { background-color: #EAECEE; color: #2C3E50; padding: 12px 15px; border-radius: 6px; font-size: 13.5px; font-weight: 500; text-align: left; border-left: 5px solid #27AE60; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

# Khởi tạo file điều khiển gốc
if not os.path.exists(CONTROL_FILE):
    with open(CONTROL_FILE, 'w') as f:
        json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "Hệ thống vận hành tự nhiên"}, f)

# Khởi tạo các biến Session State
if 'temp' not in st.session_state: st.session_state.temp = 0.0
if 'rh' not in st.session_state: st.session_state.rh = 0.0
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'is_completed' not in st.session_state: st.session_state.is_completed = False 
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 
if 'simulated_time' not in st.session_state: st.session_state.simulated_time = "2026-05-24 07:00:00"

# Biến lưu trữ độ lệch tích lũy qua các chu kỳ can thiệp phần cứng
if 'temp_offset' not in st.session_state: st.session_state.temp_offset = 0.0
if 'rh_offset' not in st.session_state: st.session_state.rh_offset = 0.0

PLANT_PRESETS = {
    "🍓 Dâu tây Đà Lạt (Giai đoạn trái)": {
        "🌅 Sáng (05h-10h)": (0.5, 0.9), "☀️ Trưa (10h-15h)": (0.7, 1.2), 
        "🌇 Chiều (15h-19h)": (0.6, 1.0), "🌌 Tối (19h-23h)": (0.4, 0.8), "🌙 Khuya (23h-05h)": (0.3, 0.7)
    }
}
if 'current_matrix' not in st.session_state:
    st.session_state.current_matrix = PLANT_PRESETS["🍓 Dâu tây Đà Lạt (Giai đoạn trái)"].copy()

# ==========================================
# 🤖 LUỒNG HỨNG SỰ KIỆN CLICK NÚT TELEGRAM BẬT CHẾ ĐỘ PHẢN HỒI LẬP TỨC
# ==========================================
def run_telegram_bot():
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELE_TOKEN}/getUpdates?timeout=10"
            if offset: url += f"&offset={offset}"
            res = requests.get(url).json()
            if "result" in res:
                for update in res["result"]:
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        query = update["callback_query"]
                        data = query["data"]
                        query_id = query["id"]
                        
                        if data == "none":
                            with open(CONTROL_FILE, 'w') as f:
                                json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "⚠️ Đã chọn bỏ qua. Trạm chạy trôi tự do theo tự nhiên."}, f)
                        else:
                            # Ghi nhận người dùng vừa chọn giải pháp xử lý -> Kích hoạt trạng thái "triggered"
                            # Streamlit chu kỳ tới sẽ dựa vào đây để tính toán chính xác Delta cần bù
                            with open(CONTROL_FILE, 'w') as f:
                                json.dump({
                                    "status": "triggered", 
                                    "action": data, 
                                    "step_num": 0, 
                                    "needed_temp_delta": 0.0, 
                                    "needed_rh_delta": 0.0, 
                                    "msg": "⚡ Đã tiếp nhận lệnh từ Telegram! Đang tính toán công suất phần cứng để hồi phục dứt điểm..."
                                }, f)
                        
                        requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", json={
                            "callback_query_id": query_id, "text": "Hệ thống nhà kính đang thực thi giải pháp!"
                        })
        except Exception:
            pass
        time.sleep(1)

if "bot_thread_started" not in st.session_state:
    st.session_state.bot_thread_started = True
    threading.Thread(target=run_telegram_bot, daemon=True).start()

def send_telegram_with_buttons(token, chat_id, text, buttons):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try: requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": buttons}})
    except Exception: pass

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
        if temp >= 27.0: return "🔥 Nóng bực do bức xạ hấp nhiệt cao", "Bật Quạt Xả Nhiệt & Kéo Rèm Đỉnh Chắn Nắng", "temp"
        else: return "🌵 Khô hanh tụt độ ẩm trầm trọng", "Kích Hoạt Phun Sương Mịn Bù Ẩm Tức Thì", "humidity"
    elif "Ẩm" in status:
        if rh >= 85.0: return "🌧️ Lạnh ẩm bão hòa hơi nước tích tụ", "Mở Quạt Hút Khô Ép Hạ Ẩm Cưỡng Bức", "humidity"
        else: return "🥶 Lạnh giá sâu khiến không khí co lại", "Khép Rèm Hông & Bật Đèn Sưởi Hồng Ngoại", "temp"
    return "🟩 Môi trường dải lý tưởng ổn định", "Duy trì tự động tự cân bằng ổn định.", "none"

# ==========================================
# 🔄 THUẬT TOÁN ĐIỀU TIẾT TOÁN HỌC ĐỘC QUYỀN - ÉP ĐÍCH CHÍNH XÁC SAU ĐÚNG 20 PHÚT
# ==========================================
def trigger_new_data(plant_matrix):
    current_sim_datetime = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    current_date_str = current_sim_datetime.strftime("Ngày %d/%m")
    
    # Đọc dữ liệu môi trường nền (Xu hướng biến đổi thời tiết tự nhiên)
    base_temp, base_rh = get_weather_by_time(current_sim_datetime)
    
    try:
        with open(CONTROL_FILE, 'r') as f:
            cmd_state = json.load(f)
            
        # 🟢 BƯỚC THỜI ĐIỂM T7:00 - NGƯỜI DÙNG VỪA BẤM NÚT ĐIỀU KHIỂN
        if cmd_state["status"] == "triggered":
            buoi_hien_tai = get_biological_block(current_sim_datetime.hour)
            v_min, v_max = plant_matrix[buoi_hien_tai]
            # Tính toán Điểm vàng trung tâm lý tưởng (Target VPD lý tưởng nhất)
            target_vpd_center = (v_min + v_max) / 2.0
            
            # Khởi tạo các giá trị giả định ban đầu để quét dải tìm nghiệm tối ưu
            best_t_delta = 0.0
            best_h_delta = 0.0
            min_error = 999.0
            
            # Quét tìm giải pháp phần cứng tối ưu đưa VPD về chính xác tâm lý tưởng
            if cmd_state["action"] in ["fix_hot_temp", "fix_wet_temp"]: # Tác động kênh Nhiệt
                for t_d in [x * 0.1 for x in range(-100, 100)]:
                    test_vpd = calculate_vpd(base_temp + t_d, base_rh)
                    if abs(test_vpd - target_vpd_center) < min_error:
                        min_error = abs(test_vpd - target_vpd_center)
                        best_t_delta = t_d
            else: # Tác động kênh Độ ẩm
                for h_d in [x * 0.5 for x in range(-100, 100)]:
                    test_vpd = calculate_vpd(base_temp, max(0.0, min(100.0, base_rh + h_d)))
                    if abs(test_vpd - target_vpd_center) < min_error:
                        min_error = abs(test_vpd - target_vpd_center)
                        best_h_delta = h_d
                        
            # Lưu lại thông số Delta chính xác cần bù vào cấu hình để thực thi 2 bước
            cmd_state["status"] = "processing"
            cmd_state["step_num"] = 1
            cmd_state["needed_temp_delta"] = best_t_delta
            cmd_state["needed_rh_delta"] = best_h_delta
            cmd_state["msg"] = f"⚙️ Đang thực thi chu kỳ 1 (7h10): Thiết bị chạy 50% công suất..."
            
            # Áp dụng 50% chặng đường ngay cho chu kỳ này
            st.session_state.temp_offset = best_t_delta / 2.0
            st.session_state.rh_offset = best_h_delta / 2.0
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
                
        # 🟡 BƯỚC THỜI ĐIỂM T7:10 - CHU KỲ TRUNG GIAN (ĐANG ĐIỀU CHỈNH)
        elif cmd_state["status"] == "processing" and cmd_state["step_num"] == 1:
            cmd_state["step_num"] = 2
            cmd_state["msg"] = f"⚙️ Đang thực thi chu kỳ 2 (7h20): Đẩy tối đa 100% công suất để ép lọt vùng Lý Tưởng!"
            
            # Áp dụng 100% chặng đường lệch để ép môi trường cán đích
            st.session_state.temp_offset = cmd_state["needed_temp_delta"]
            st.session_state.rh_offset = cmd_state["needed_rh_delta"]
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
                
        # 🔵 BƯỚC THỜI ĐIỂM T7:20 - ĐÃ CÁN ĐÍCH VÀ HOÀN THÀNH XỬ LÝ
        elif cmd_state["status"] == "processing" and cmd_state["step_num"] == 2:
            # Thu hồi lệnh, reset trạng thái để hệ thống quay lại chạy tự động nền
            cmd_state["status"] = "idle"
            cmd_state["action"] = "none"
            cmd_state["step_num"] = 0
            cmd_state["needed_temp_delta"] = 0.0
            cmd_state["needed_rh_delta"] = 0.0
            cmd_state["msg"] = "✨ Đã cán mốc 7h20: Môi trường được đưa về khoảng Lý Tưởng thành công dứt điểm!"
            
            st.session_state.temp_offset = 0.0
            st.session_state.rh_offset = 0.0
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
    except Exception:
        pass

    # Thiết lập giá trị môi trường thực tế sau khi đã áp dụng thuật toán chia bước offset
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

    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": current_date_str,
        "Thời gian mô phỏng": current_sim_datetime, "Hiển thị Giờ": current_sim_datetime.strftime("%H:%M"),
        "datetime_internal": current_sim_datetime, "Nhiệt độ (°C)": st.session_state.temp, "Độ ẩm (%)": st.session_state.rh,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text
    })

    # ==========================================
    # 🔇 CƠ CHẾ KHÓA ANTI-SPAM TELEGRAM KHI ĐANG CAN THIỆP PHẦN CỨNG
    # ==========================================
    if TELE_TOKEN and TELE_CHAT_ID:
        try:
            with open(CONTROL_FILE, 'r') as f: current_status = json.load(f)["status"]
        except Exception: current_status = "idle"
            
        # CHỈ GỬI TIN NHẮN KHI LỆCH DẢI VÀ HỆ THỐNG ĐANG Ở TRẠNG THÁI RẢNH RỖI (IDLE)
        # Nếu đang ở trạng thái "processing" (tức là mốc 7h10, 7h20), lệnh này BỊ KHÓA, không gửi giải pháp lên Tele nữa.
        if current_status == "idle" and status_text != "🟩 Lý Tưởng":
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            trend, _ = predict_vpd_trend_v3(h_latest, current_sim_datetime.hour, plant_matrix)
            clean_trend = trend.replace("Xu hướng:", "").strip()
            
            msg = (f"🌿 *CẢNH BÁO LỆCH CHUẨN VPD NHÀ KÍNH*\n⏰ {current_date_str} - Giờ trạm: *{current_sim_datetime.strftime('%H:%M')}*\n"
                   f"📊 Sensor: {st.session_state.temp}°C | {st.session_state.rh}%\n"
                   f"📈 *VPD đo được:* *{new_vpd:.2f} kPa* (Khoảng chuẩn: {v_min}-{v_max})\n"
                   f"📢 *Tình trạng:* *{status_text}*\n"
                   f"🔍 *Lý do:* _{reason_text}_\n"
                   f"🔮 *Xu hướng tự nhiên:* _{clean_trend}_\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"📲 *Vui lòng nhấn chọn giải pháp phần cứng tức thời dưới đây:*")
            
            tele_buttons = []
            if "Nóng" in status_text:
                if rec_type == "temp": tele_buttons = [[{"text": "💨 Kích Hoạt Quạt Thông Gió Xả Nhiệt Gắt", "callback_data": "fix_hot_temp"}]]
                else: tele_buttons = [[{"text": "💦 Kích Hoạt Hệ Thống Phun Sương Tăng Ẩm", "callback_data": "fix_hot_rh"}]]
            elif "Ẩm" in status_text:
                if rec_type == "humidity": tele_buttons = [[{"text": "🌪️ Bật Quạt Hút Ép Hạ Ẩm Cưỡng Bức", "callback_data": "fix_wet_rh"}]]
                else: tele_buttons = [[{"text": "🔥 Đóng Rèm Hông & Bật Đèn Nhiệt Giữ Ấm", "callback_data": "fix_wet_temp"}]]
            
            tele_buttons.append([{"text": "⏸️ Bỏ qua (Chạy trôi tự do theo thời tiết)", "callback_data": "none"}])
            send_telegram_with_buttons(TELE_TOKEN, TELE_CHAT_ID, msg, tele_buttons)
    
    # Tịnh tiến thời gian mô phỏng thêm 10 phút sang chu kỳ kế tiếp
    next_dt = current_sim_datetime + timedelta(minutes=10)
    if next_dt.hour == 0 and next_dt.minute == 0: st.session_state.is_running = False; st.session_state.is_completed = True   
    st.session_state.simulated_time = next_dt.strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# GIAO DIỆN STREAMLIT CHÍNH
# ==========================================
st.sidebar.markdown("## 🧭 MENU CHỨC NĂNG")
app_mode = st.sidebar.selectbox("Chọn Tag công việc cần thực hiện:", ["🌿 VPD Realtime & Mô Phỏng", "📥 Phân Tích File IoT JSON"])
st.sidebar.markdown("---")

if app_mode == "🌿 VPD Realtime & Mô Phỏng":
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 GIÁM SÁT VPD REALTIME VÀ ĐIỀU KHIỂN CHIA BƯỚC ĐÚNG TIẾN ĐỘ</h2>", unsafe_allow_html=True)
    
    left_col, right_col = st.columns([3, 7])
    with left_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📋 CẤU HÌNH MA TRẬN</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            m_sáng = st.slider("🌅 Sáng (05h-10h):", 0.0, 3.0, st.session_state.current_matrix["🌅 Sáng (05h-10h)"], 0.1)
            st.session_state.current_matrix["🌅 Sáng (05h-10h)"] = m_sáng

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
                st.session_state.history = []; st.session_state.stt_counter = 0; st.session_state.countdown = 15
                st.session_state.is_running = False; st.session_state.is_completed = False
                st.session_state.simulated_time = "2026-05-24 07:00:00"
                st.session_state.temp_offset = 0.0; st.session_state.rh_offset = 0.0
                with open(CONTROL_FILE, 'w') as f: json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "Reset trạm thành công"}, f)
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
            stt = "🟩 Lý Tưởng"
            v_min, v_max = st.session_state.current_matrix[get_biological_block(sim_dt.hour)]
            if v_calc >= v_max + 0.5: stt = "🔴 Quá Nóng"
            elif v_calc > v_max: stt = "💛 Nóng"
            elif v_calc < v_min - 0.2: stt = "🔵 Quá Ẩm"
            elif v_calc < v_min: stt = "🌐 Ẩm"
            
            reason_rt, action_rt, _ = get_detailed_analysis_and_action(stt, st.session_state.temp, st.session_state.rh)
            
            try:
                with open(CONTROL_FILE, 'r') as f: current_action_msg = json.load(f)["msg"]
            except Exception: current_action_msg = "Ổn định."

            with st.container(border=True):
                st.markdown(f"⏰ **Thời gian mô phỏng Giờ Trạm:** `<span style='color:#C0392B; font-weight:bold; font-size:16px;'>{sim_dt.strftime('%H:%M')}</span>`", unsafe_allow_html=True)
                st.caption(f"⏳ Đếm ngược chu kỳ: {st.session_state.countdown}s | Bù nhiệt: {st.session_state.temp_offset}°C | Bù ẩm: {st.session_state.rh_offset}%")
                st.warning(f"🤖 **Trạng thái phần cứng:** {current_action_msg}")
                st.markdown(f"""
                <div class="big-vpd-box">
                    <div class="big-vpd-title">🌿 CHỈ SỐ VPD THỰC TẾ TRÊN LÁ</div>
                    <div class="big-vpd-value">{v_calc:.2f} kPa</div>
                    <div class="big-env-value">🌡️ {st.session_state.temp}°C  &nbsp;|&nbsp;  💧 {st.session_state.rh}%</div>
                    <div class="analysis-merge-box">
                        📌 <b>Hiện trạng:</b> {stt}<br>
                        🔍 <b>Lý do chi tiết:</b> {reason_rt}<br>
                        🛠️ <b>Giải pháp áp dụng:</b> {action_rt}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        live_monitor_panel()

    with right_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📊 BIỂU ĐỒ DIỄN BIẾN MÔI TRƯỜNG NHÀ KÍNH KHI ĐƯỢC ĐIỀU CHỈNH</h3>", unsafe_allow_html=True)
        if st.session_state.history:
            df_all = pd.DataFrame(st.session_state.history)
            df_f = df_all.iloc[::-1].copy()
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            v_min_chart, v_max_chart = st.session_state.current_matrix[get_biological_block(sim_dt.hour)]
            
            st.altair_chart(draw_vpd_chart(df_f, v_min_chart, v_max_chart), use_container_width=True)
            st.altair_chart(draw_combined_temp_humidity_chart(df_f), use_container_width=True)
            st.dataframe(df_f[["STT", "Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True)
