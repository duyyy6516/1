import streamlit as st
import pandas as pd
import json
import requests
import math
from datetime import datetime, timedelta

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

TELE_TOKEN = "8917951413:AAE6LKUEfYEYiQrFWGoKsQn0tumZc_XbcHg"
TELE_CHAT_ID = "7290661009"

st.set_page_config(page_title="VPD Smart Farm Monitor Pro", page_icon="🌿", layout="wide")

# --- Thiết lập giao diện CSS chuẩn ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow-y: auto !important; scroll-behavior: smooth; }
    .block-container { padding-top: 3.5rem !important; padding-bottom: 2rem; padding-left: 1.5rem; padding-right: 1.5rem; }
    
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
    .tele-status-box { background-color: #E8F8F5; color: #117A65; padding: 10px; border-left: 4px solid #1ABC9C; border-radius: 4px; font-weight: bold; margin-top: 8px; font-size: 13px; line-height: 1.4; }
    </style>
    """, unsafe_allow_html=True)

# --- Khởi tạo dữ liệu Session State ---
if 'temp' not in st.session_state: st.session_state.temp = 0.0
if 'rh' not in st.session_state: st.session_state.rh = 0.0
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'is_completed' not in st.session_state: st.session_state.is_completed = False 
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 
if 'simulated_time' not in st.session_state: st.session_state.simulated_time = "2026-05-24 07:00:00"

if 'last_update_id' not in st.session_state: st.session_state.last_update_id = 0
if 'tele_intervention_log' not in st.session_state: st.session_state.tele_intervention_log = "Chưa nhận lệnh điều khiển nào từ Telegram."
if 'forced_trend' not in st.session_state: st.session_state.forced_trend = None

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
    },
    "🥬 Rau cải / Xà lách thủy canh": {
        "🌅 Sáng (05h-10h)": (0.4, 0.8), "☀️ Trưa (10h-15h)": (0.6, 1.1), 
        "🌇 Chiều (15h-19h)": (0.5, 0.9), "🌌 Tối (19h-23h)": (0.4, 0.7), "🌙 Khuya (23h-05h)": (0.3, 0.6)
    },
    "🍉 Dưa lưới / Dưa leo nhà màng": {
        "🌅 Sáng (05h-10h)": (0.7, 1.2), "☀️ Trưa (10h-15h)": (0.9, 1.6), 
        "🌇 Chiều (15h-19h)": (0.8, 1.3), "🌌 Tối (19h-23h)": (0.6, 1.0), "🌙 Khuya (23h-05h)": (0.5, 0.8)
    }
}

if 'current_matrix' not in st.session_state:
    st.session_state.current_matrix = PLANT_PRESETS["🍓 Dâu tây Đà Lạt (Giai đoạn trái)"].copy()
if 'prev_preset' not in st.session_state:
    st.session_state.prev_preset = "🍓 Dâu tây Đà Lạt (Giai đoạn trái)"

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
    if status == "🔴 Quá Nóng":
        return "🔥 LỖI QUÁ NÓNG: Nhiệt độ vượt ngưỡng cực hạn, bức xạ mặt trời quá lớn.", "HÀNH ĐỘNG: Đóng lưới cắt nắng 100% + Mở quạt hút tối đa + Bật phun sương làm mát nền."
    elif status == "💛 Nóng":
        return "🌵 LỖI NÓNG: Không khí hanh khô nhẹ, VPD dịch chuyển lên cao.", "HÀNH ĐỘNG: Bật hệ thống phun sương hạt mịn theo chu kỳ ngắn để bổ sung ẩm."
    elif status == "🔵 Quá Ẩm":
        return "🌧️ LỖI QUÁ ẨM: Độ ẩm không khí bão hòa (>90%), đọng sương bề mặt lá.", "HÀNH ĐỘNG: CƯỠNG BỨC TẮT TƯỚI NƯỚC + Bật quạt đối lưu liên tục + Mở cửa thông gió xả ẩm."
    elif status == "🌐 Ẩm":
        return "🥶 LỖI ẨM: Không khí hơi bí gió, cây thoát hơi nước kém.", "HÀNH ĐỘNG: Bật quạt đảo gió nội bộ nhà màng để làm thoáng gốc cây."
    return "🟩 Môi trường hoàn hảo", "Môi trường đang đẹp, không cần can thiệp."

def send_telegram_with_inline_buttons(token, chat_id, text, action_type):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": f"🛠️ Kích hoạt: {action_type}", "callback_data": f"SET_{action_type}"},
                    {"text": "✅ Bỏ qua lỗi", "callback_data": "IGNORE_ALERT"}
                ]
            ]
        }
    }
    try: requests.post(url, json=payload, timeout=3)
    except: pass

def check_telegram_feedback():
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/getUpdates"
    params = {"offset": st.session_state.last_update_id + 1, "timeout": 1}
    try:
        response = requests.get(url, params=params, timeout=2).json()
        if "result" in response:
            for update in response["result"]:
                st.session_state.last_update_id = update["update_id"]
                if "callback_query" in update:
                    data = str(update["callback_query"]["data"])
                    chat_id = str(update["callback_query"]["message"]["chat"]["id"])
                    
                    if chat_id == TELE_CHAT_ID:
                        if data.startswith("SET_"):
                            action_name = data.replace("SET_", "")
                            st.session_state.forced_trend = action_name
                            st.session_state.tele_intervention_log = f"⚡ [{datetime.now().strftime('%H:%M:%S')}] Nhận lệnh Telegram: Duy trì chế độ [{action_name}] cho tới khi hết lỗi."
                            requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", 
                                          json={"callback_query_id": update["callback_query"]["id"], "text": f"Đã khóa lệnh thực thi: {action_name}"})
                        elif data == "IGNORE_ALERT":
                            st.session_state.forced_trend = None
                            st.session_state.tele_intervention_log = f"💤 [{datetime.now().strftime('%H:%M:%S')}] Nhà vườn bấm hủy can thiệp lỗi từ xa."
                            requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", 
                                          json={"callback_query_id": update["callback_query"]["id"], "text": "Đã hủy bỏ lệnh."})
    except: pass

# --- THUẬT TOÁN ĐIỀU KHIỂN KHÓA LỆNH CHU KỲ LIÊN TỤC VÀ CHỐNG SPAM TELEGRAM ---
def trigger_new_data(plant_matrix):
    check_telegram_feedback()
    
    current_sim_datetime = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    current_date_str = current_sim_datetime.strftime("Ngày %d/%m")
    base_temp, base_rh = get_weather_by_time(current_sim_datetime)
    
    buoi_hien_tai = get_biological_block(current_sim_datetime.hour)
    v_min, v_max = plant_matrix[buoi_hien_tai]
    target_vpd = (v_min + v_max) / 2.0  # Tâm dải Lý Tưởng để ép chỉ số về chuẩn nhất
    
    # 🌟 KIỂM TRA ĐẦU CHU KỲ: Nếu đang có lệnh ép, tính toán xem chu kỳ trước đã đạt Lý Tưởng chưa?
    if st.session_state.forced_trend and st.session_state.history:
        last_recorded_vpd = st.session_state.history[0]["VPD (kPa)"]
        if v_min <= last_recorded_vpd <= v_max:
            # Nếu đã lọt vào vùng lý tưởng thành công, tiến hành giải phóng hệ thống
            st.session_state.forced_trend = None
            st.session_state.tele_intervention_log += f" -> 🎉 Lúc {current_sim_datetime.strftime('%H:%M')}: Chỉ số đạt chuẩn lý tưởng ({last_recorded_vpd} kPa). Đã ngắt chế độ ép lệnh!"

    # Thực thi tính toán Nhiệt độ và Độ ẩm dựa trên cờ trạng thái
    if st.session_state.forced_trend:
        cmd = st.session_state.forced_trend
        
        # Mặc định tự động tính toán tịnh tiến để đưa môi trường lên dải lý tưởng mà không cần hỏi lại
        if cmd in ["Xả ẩm toàn diện", "Bật quạt đối lưu"]:
            st.session_state.temp = round(base_temp + 2.5, 1)
            vps = 0.61078 * math.exp((17.27 * st.session_state.temp) / (st.session_state.temp + 237.3))
            calculated_rh = ((vps - target_vpd) / vps) * 100.0
            st.session_state.rh = round(max(min(calculated_rh, 70.0), 48.0), 1)
            
        elif cmd in ["Hạ nhiệt khẩn cấp", "Phun sương bù ẩm"]:
            st.session_state.temp = round(base_temp - 4.5, 1)
            vps = 0.61078 * math.exp((17.27 * st.session_state.temp) / (st.session_state.temp + 237.3))
            calculated_rh = ((vps - target_vpd) / vps) * 100.0
            st.session_state.rh = round(max(min(calculated_rh, 82.0), 55.0), 1)
    else:
        # Nếu không có lệnh can thiệp nào đang chạy duy trì, hệ thống lấy khí hậu tự nhiên
        st.session_state.temp, st.session_state.rh = base_temp, base_rh

    st.session_state.countdown = 15 
    st.session_state.stt_counter += 1
    new_vpd = calculate_vpd(st.session_state.temp, st.session_state.rh)
    
    if new_vpd >= v_max + 0.5: status_text = "🔴 Quá Nóng"
    elif new_vpd > v_max: status_text = "💛 Nóng"
    elif new_vpd < v_min - 0.2: status_text = "🔵 Quá Ẩm"
    elif new_vpd < v_min: status_text = "🌐 Ẩm"
    else: status_text = "🟩 Lý Tưởng"
    
    reason_text, action_text = get_detailed_analysis_and_action(status_text, st.session_state.temp, st.session_state.rh)

    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": current_date_str,
        "Thời gian mô phỏng": current_sim_datetime, "Hiển thị Giờ": current_sim_datetime.strftime("%H:%M"),
        "datetime_internal": current_sim_datetime, "Nhiệt độ (°C)": st.session_state.temp, "Độ ẩm (%)": st.session_state.rh,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text
    })

    # 🛑 KHÓA TIN NHẮN SPAM: Chỉ nhắn Telegram nếu có lỗi VÀ hệ thống hoàn toàn CHƯA CÓ LỆNH ÉP nào trước đó
    if status_text != "🟩 Lý Tưởng" and not st.session_state.forced_trend:
        tele_action_tag = "Bật quạt đối lưu"
        if status_text == "🔴 Quá Nóng": tele_action_tag = "Hạ nhiệt khẩn cấp"
        elif status_text == "💛 Nóng": tele_action_tag = "Phun sương bù ẩm"
        elif status_text == "🔵 Quá Ẩm": tele_action_tag = "Xả ẩm toàn diện"
        
        msg = (f"⚠️ *LỆCH CHUẨN KHÍ HẬU VƯỜN*\n⏰ Thời gian: {current_date_str} - {current_sim_datetime.strftime('%H:%M')} ({buoi_hien_tai})\n"
               f"📊 Cảm biến: {st.session_state.temp}°C | {st.session_state.rh}%\n"
               f"📉 *VPD Thực Tế:* *{new_vpd:.2f} kPa* (Chuẩn dải: {v_min}-{v_max})\n"
               f"📢 *Hiện trạng:* {status_text}\n"
               f"📥 *Bấm nút kích hoạt hệ thống ứng phó duy trì:*")
        send_telegram_with_inline_buttons(TELE_TOKEN, TELE_CHAT_ID, msg, tele_action_tag)
    
    next_dt = current_sim_datetime + timedelta(minutes=10)
    if next_dt.hour == 0 and next_dt.minute == 0:
        st.session_state.is_running = False; st.session_state.is_completed = True   
    st.session_state.simulated_time = next_dt.strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# GIAO DIỆN CHÍNH STREAMLIT
# ==========================================
st.sidebar.markdown("## 🧭 MENU CHỨC NĂNG")
app_mode = st.sidebar.selectbox("Chọn Tag công việc cần thực hiện:", ["🌿 VPD Realtime & Mô Phỏng", "📥 Phân Tích File IoT JSON"])
st.sidebar.markdown("---")
st.sidebar.info("🎯 **Hệ thống giám sát VPD Pro**\nĐiều khiển nhà kính nông nghiệp công nghệ cao tối ưu sinh học.")

if app_mode == "🌿 VPD Realtime & Mô Phỏng":
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 HỆ THỐNG GIÁM SÁT VPD REALTIME & MÔ PHỎNG</h2>", unsafe_allow_html=True)
    left_col, right_col = st.columns([3, 7])
    
    with left_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📋 CẤU HÌNH MA TRẬN VPD THEO BUỔI</h3>", unsafe_allow_html=True)
        preset_choice = st.selectbox("Chọn giống cây áp ma trận mẫu:", list(PLANT_PRESETS.keys()) + ["🛠️ Tùy chỉnh thủ công toàn bộ"])
        
        if preset_choice != "🛠️ Tùy chỉnh thủ công toàn bộ" and preset_choice != st.session_state.prev_preset:
            st.session_state.current_matrix = PLANT_PRESETS[preset_choice].copy()
            st.session_state.prev_preset = preset_choice

        with st.container(border=True):
            m_sáng = st.slider("🌅 Sáng (05h-10h):", 0.0, 3.0, st.session_state.current_matrix["🌅 Sáng (05h-10h)"], 0.1)
            m_trưa = st.slider("☀️ Trưa (10h-15h):", 0.0, 3.0, st.session_state.current_matrix["☀️ Trưa (10h-15h)"], 0.1)
            m_chiều = st.slider("🌇 Chiều (15h-19h):", 0.0, 3.0, st.session_state.current_matrix["🌇 Chiều (15h-19h)"], 0.1)
            m_tối = st.slider("🌌 Tối (19h-23h):", 0.0, 3.0, st.session_state.current_matrix["🌌 Tối (19h-23h)"], 0.1)
            m_khuya = st.slider("🌙 Khuya (23h-05h):", 0.0, 3.0, st.session_state.current_matrix["🌙 Khuya (23h-05h)"], 0.1)
            st.session_state.current_matrix = {"🌅 Sáng (05h-10h)": m_sáng, "☀️ Trưa (10h-15h)": m_trưa, "🌇 Chiều (15h-19h)": m_chiều, "🌌 Tối (19h-23h)": m_tối, "🌙 Khuya (23h-05h)": m_khuya}

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
            
            reason_rt, action_rt = get_detailed_analysis_and_action(stt, st.session_state.temp, st.session_state.rh)
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            current_date_str = sim_dt.strftime("Ngày %d/%m")
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            trend_raw, _ = predict_vpd_trend_v3(h_latest, sim_dt.hour, st.session_state.current_matrix)
            clean_trend_rt = trend_raw.replace("Xu hướng:", "").strip()
            
            with st.container(border=True):
                st.markdown(f"⏰ **Thời gian:** `{sim_dt.strftime('%H:%M')}` | ⏳ **Chu kỳ kế:** `{st.session_state.countdown}s`")
                st.markdown(f"""
                <div class="big-vpd-box">
                    <div class="big-vpd-title">🌿 CHỈ SỐ VPD THỰC TẾ TRÊN LÁ</div>
                    <div class="big-vpd-value">{v_calc:.2f} kPa</div>
                    <div class="big-env-value">🌡️ {st.session_state.temp}°C  &nbsp;|&nbsp;  💧 {st.session_state.rh}%</div>
                    <div class="analysis-merge-box">
                        🔍 <b>Hiện trạng vườn:</b> {stt}<br>
                        🔍 <b>Nguyên nhân sinh học:</b> {reason_rt}<br>
                        🛠️ <b>Cách xử lý ngay:</b> <span style="color:#C0392B; font-weight:bold;">{action_rt}</span><br>
                        🔮 <b>Xu hướng:</b> {clean_trend_rt}
                    </div>
                    <div class="tele-status-box">
                        🤖 Nhật ký đồng bộ lệnh Telegram từ xa:<br>
                        <span style="font-weight:normal; color:#2C3E50;">{st.session_state.tele_intervention_log}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        live_monitor_panel()

    with right_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📊 PHÂN TÍCH DIỄN BIẾN CHU KỲ PHÒNG DỊCH</h3>", unsafe_allow_html=True)
        if st.session_state.history:
            u_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            sel_day = st.selectbox("Chọn ngày lịch sử xem lại:", u_days, label_visibility="collapsed")
            df_all = pd.DataFrame(st.session_state.history)
            df_f = df_all[df_all["Ngày"] == sel_day].iloc[::-1].copy()
            
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            b_hien_tai = get_biological_block(sim_dt.hour)
            v_min, v_max = st.session_state.current_matrix[b_hien_tai]
            
            st.markdown("**🎨 Khối màu nền phân tầng:** 🔵 *Quá Ẩm* | 🟢 *Lý Tưởng* | 🔴 *Quá Nóng*")
            st.altair_chart(draw_vpd_chart(df_f, v_min, v_max), use_container_width=True)
            st.altair_chart(draw_combined_temp_humidity_chart(df_f), use_container_width=True)
            
            st.markdown("##### 📝 BẢNG ĐÁNH GIÁ CHUNG THEO CÁC BUỔI TRONG NGÀY (REALTIME)")
            df_rt_report = analyze_day_by_blocks_rt(st.session_state.history, st.session_state.current_matrix, sel_day)
            if not df_rt_report.empty: st.dataframe(df_rt_report, use_container_width=True, hide_index=True)
            
            st.markdown("##### 📋 BẢNG NHẬT KÝ CHI TIẾT ĐIỂM DỮ LIỆU CHU KỲ")
            st.dataframe(df_f[["STT", "Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True)

# ==========================================
# TAG 2: PHÂN TÍCH FILE IOT JSON & CSV
# ==========================================
elif app_mode == "📥 Phân Tích File IoT JSON":
    st.markdown("<h2 style='color: #114B72; font-size: 26px;'>📥 PHÂN TÍCH LỊCH SỬ DỮ LIỆU FILE IOT (.JSON / .CSV)</h2>", unsafe_allow_html=True)
    f_left, f_right = st.columns([3, 7])
    with f_left:
        with st.container(border=True):
            st.markdown("<div class='upload-header'>🌿 THIẾT LẬP MA TRẬN ÁP DỤNG TRÊN FILE</div>", unsafe_allow_html=True)
            f_preset_choice = st.selectbox("Chọn cấu hình chuẩn áp vào file dữ liệu:", list(PLANT_PRESETS.keys()) + ["🛠️ Tùy chỉnh thủ công toàn bộ"], key="sb_file")
            if 'file_matrix' not in st.session_state or f_preset_choice != "🛠️ Tùy chỉnh thủ công toàn bộ":
                if f_preset_choice != "🛠️ Tùy chỉnh thủ công toàn bộ": st.session_state.file_matrix = PLANT_PRESETS[f_preset_choice].copy()
                else: st.session_state.file_matrix = PLANT_PRESETS["🍓 Dâu tây Đà Lạt (Giai đoạn trái)"].copy()
            f_sáng = st.slider("🌅 Sáng (05h-10h):", 0.0, 3.0, st.session_state.file_matrix["🌅 Sáng (05h-10h)"], 0.1, key="fs_1")
            f_trưa = st.slider("☀️ Trưa (10h-15h):", 0.0, 3.0, st.session_state.file_matrix["☀️ Trưa (10h-15h)"], 0.1, key="fs_2")
            f_chiều = st.slider("🌇 Chiều (15h-19h):", 0.0, 3.0, st.session_state.file_matrix["🌇 Chiều (15h-19h)"], 0.1, key="fs_3")
            f_tối = st.slider("🌌 Tối (19h-23h):", 0.0, 3.0, st.session_state.file_matrix["🌌 Tối (19h-23h)"], 0.1, key="fs_4")
            f_khuya = st.slider("🌙 Khuya (23h-05h):", 0.0, 3.0, st.session_state.file_matrix["🌙 Khuya (23h-05h)"], 0.1, key="fs_5")
            st.session_state.file_matrix = {"🌅 Sáng (05h-10h)": f_sáng, "☀️ Trưa (10h-15h)": f_trưa, "🌇 Chiều (15h-19h)": f_chiều, "🌌 Tối (19h-23h)": f_tối, "🌙 Khuya (23h-05h)": f_khuya}
            
    with f_right:
        with st.container(border=True):
            st.markdown("<div class='upload-header'>📥 CHỌN TẢI FILE & CHẾ ĐỘ LỌC GỘP CHU KỲ</div>", unsafe_allow_html=True)
            uploaded_file = st.file_uploader("Kéo thả file nhật ký trạm IoT (.json, .csv, .xlsx):", type=["json", "csv", "xlsx"])
            time_filter_option = st.selectbox("📆 Cấu hình bộ lọc gom dữ liệu theo mốc thời gian:", ["📊 Tự động phân tích thông minh theo File", "📆 Chọn một ngày cụ thể trên lịch", "📅 Xem theo Tuần (Tự chọn ngày bắt đầu)", "📆 Xem theo Tháng (Tự chọn ngày bắt đầu)"])
        
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.json'):
                json_data = json.load(uploaded_file)
                if isinstance(json_data, list): df_upload = pd.DataFrame(json_data)
                elif isinstance(json_data, dict):
                    list_key = None
                    for k, v in json_data.items():
                        if isinstance(v, list): list_key = k; break
                    df_upload = pd.DataFrame(json_data[list_key]) if list_key else pd.DataFrame([json_data])
            elif uploaded_file.name.endswith('.csv'): df_upload = pd.read_csv(uploaded_file)
            else: df_upload = pd.read_excel(uploaded_file)

            col_temp_raw = 'tempKK' if 'tempKK' in df_upload.columns else None
            col_rh_raw = 'humiKK' if 'humiKK' in df_upload.columns else None
            col_time = 'Thời gian' if 'Thời gian' in df_upload.columns else None

            if not col_temp_raw or not col_rh_raw or not col_time:
                for col in df_upload.columns:
                    c_low = str(col).lower().strip()
                    if 'tempkk' in c_low or 'nhiệt độ' in c_low: col_temp_raw = col
                    if 'humikk' in c_low or 'độ ẩm' in c_low: col_rh_raw = col
                    if any(k in c_low for k in ['thời gian', 'time', 'timestamp']): col_time = col

            df_clean_raw = df_upload[[col_time, col_temp_raw, col_rh_raw]].dropna().copy()
            df_clean_raw[col_temp_raw] = pd.to_numeric(df_clean_raw[col_temp_raw], errors='coerce')
            df_clean_raw[col_rh_raw] = pd.to_numeric(df_clean_raw[col_rh_raw], errors='coerce')
            
            df_clean = pd.DataFrame()
            df_clean[col_time] = df_clean_raw[col_time]
            df_clean["temp_fixed"] = df_clean_raw[col_temp_raw]   
            df_clean["rh_fixed"] = df_clean_raw[col_rh_raw]   

            raw_datetimes = []
            for val in df_clean[col_time].astype(str):
                try: raw_datetimes.append(pd.to_datetime(val.strip()))
                except: raw_datetimes.append(datetime.now())

            df_clean["datetime_internal"] = raw_datetimes
            df_clean["only_date"] = df_clean["datetime_internal"].dt.date
            df_clean = df_clean.sort_values("datetime_internal")
            df_clean["VPD_raw"] = df_clean.apply(lambda row: calculate_vpd(row["temp_fixed"], row["rh_fixed"]), axis=1)

            available_dates = sorted(df_clean["only_date"].unique())
            is_single_day = False; resample_rule = "10min"; date_format_rule = "%H:%M"
            
            if "Chọn một ngày cụ thể" in time_filter_option:
                selected_date = st.date_input("👇 Chọn ngày xem chi tiết trên lịch:", value=available_dates[0] if available_dates else datetime.now().date())
                df_filtered = df_clean[df_clean["only_date"] == selected_date].copy()
                is_single_day = True
            elif "Xem theo Tuần" in time_filter_option:
                start_date = st.date_input("Ngày xuất phát tuần:", value=min(available_dates))
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < start_date + timedelta(days=7))].copy()
                resample_rule = "1D"; date_format_rule = "%d/%m"
            else:
                df_filtered = df_clean.copy()
                if len(available_dates) > 1: resample_rule = "1D"; date_format_rule = "%d/%m"

            df_for_block_analysis = df_filtered.copy()
            df_resample_input = df_filtered[["datetime_internal", "temp_fixed", "rh_fixed", "VPD_raw"]].set_index("datetime_internal")
            df_resampled = df_resample_input.resample(resample_rule).mean().dropna().reset_index()
            df_resampled["Hiển thị Giờ"] = df_resampled["datetime_internal"].dt.strftime(date_format_rule)

            df_processed = pd.DataFrame()
            df_processed["datetime_internal"] = df_resampled["datetime_internal"]
            df_processed["Nhiệt độ (°C)"] = df_resampled["temp_fixed"].round(2)
            df_processed["Độ ẩm (%)"] = df_resampled["rh_fixed"].round(2)
            df_processed["VPD (kPa)"] = df_resampled["VPD_raw"].round(2)
            df_processed["Hiển thị Giờ"] = df_resampled["Hiển thị Giờ"]
            df_processed["Ngày"] = "Dữ liệu File"
            
            file_status_list = []
            for _, r in df_processed.iterrows():
                b_name = get_biological_block(r["datetime_internal"].hour)
                f_min, f_max = st.session_state.file_matrix[b_name]
                if r["VPD (kPa)"] >= f_max + 0.5: file_status_list.append("🔴 Quá Nóng")
                elif r["VPD (kPa)"] > f_max: file_status_list.append("💛 Nóng")
                elif r["VPD (kPa)"] < f_min - 0.2: file_status_list.append("🔵 Quá Ẩm")
                elif r["VPD (kPa)"] < f_min: file_status_list.append("🌐 Ẩm")
                else: file_status_list.append("🟩 Lý Tưởng")
            df_processed["Trạng thái"] = file_status_list

            m_col1, m_col2, m_col3 = st.columns(3)
            m_col1.markdown(f"<div class='metric-card-upload'>📈 VPD TRUNG BÌNH<br><b style='font-size:18px;color:#1E8449;'>{df_processed['VPD (kPa)'].mean():.2f} kPa</b></div>", unsafe_allow_html=True)
            m_col2.markdown(f"<div class='metric-card-upload'>🌡️ NHIỆT ĐỘ TRUNG BÌNH<br><b style='font-size:18px;color:#C0392B;'>{df_processed['Nhiệt độ (°C)'].mean():.1f} °C</b></div>", unsafe_allow_html=True)
            m_col3.markdown(f"<div class='metric-card-upload'>💧 ĐỘ ẨM TRUNG BÌNH<br><b style='font-size:18px;color:#2980B9;'>{df_processed['Độ ẩm (%)'].mean():.1f} %</b></div>", unsafe_allow_html=True)

            res_left, res_right = st.columns([6.5, 3.5])
            with res_left:
                f_min_sample, f_max_sample = st.session_state.file_matrix["🌅 Sáng (05h-10h)"]
                st.altair_chart(draw_vpd_chart(df_processed, f_min_sample, f_max_sample), use_container_width=True)
            with res_right:
                st.dataframe(df_processed[["Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True, height=260)

            st.markdown("---")
            if not df_for_block_analysis.empty:
                df_for_block_analysis["Nhiệt độ (°C)"] = df_for_block_analysis["temp_fixed"]
                df_for_block_analysis["Độ ẩm (%)"] = df_for_block_analysis["rh_fixed"]
                df_for_block_analysis["VPD (kPa)"] = df_for_block_analysis["VPD_raw"]
                df_for_block_analysis["Hiển thị Giờ"] = df_for_block_analysis["datetime_internal"].dt.strftime("%H:%M")
                df_for_block_analysis["Ngày"] = "Dữ liệu File"
                
                stt_raw_list = []
                for _, r_b in df_for_block_analysis.iterrows():
                    b_n = get_biological_block(r_b["datetime_internal"].hour)
                    f_mi, f_ma = st.session_state.file_matrix[b_n]
                    if r_b["VPD (kPa)"] >= f_ma + 0.5: stt_raw_list.append("🔴 Quá Nóng")
                    elif r_b["VPD (kPa)"] > f_ma: stt_raw_list.append("💛 Nóng")
                    elif r_b["VPD (kPa)"] < f_mi - 0.2: stt_raw_list.append("🔵 Quá Ẩm")
                    elif r_b["VPD (kPa)"] < f_mi: stt_raw_list.append("🌐 Ẩm")
                    else: stt_raw_list.append("🟩 Lý Tưởng")
                df_for_block_analysis["Trạng thái"] = stt_raw_list

                df_block_report = analyze_day_by_blocks_rt(df_for_block_analysis.to_dict('records'), st.session_state.file_matrix, "Dữ liệu File")
                st.dataframe(df_block_report, use_container_width=True, hide_index=True)
                
                if st.button("📤 Gửi báo cáo ma trận qua Telegram", type="primary", key="btn_send_file_tele"):
                    if TELE_TOKEN and TELE_CHAT_ID:
                        file_tele_msg = f"📂 *BÁO CÁO CHU KỲ FILE*\\n📦 File: `{uploaded_file.name}`\\n🎯 Mô hình: *{f_preset_choice}*\\n━━━━━━━━━━━━━━━━━━━━\\n\\n"
                        for _, r_data in df_block_report.iterrows():
                            file_tele_msg += f"Buổi *{r_data['Khoảng Buổi']}*\\n▪️ Môi trường: {r_data['Nhiệt độ TB']} | {r_data['Độ ẩm TB']}\\n▪️ VPD TB: *{r_data['VPD Trung Bình']}*\\n▪️ Đánh giá: *{r_data['Đánh giá sinh học']}*\\n▪️ Giải pháp: {r_data['Giải pháp kỹ thuật']}\\n────────────────────\\n"
                        file_tele_msg += f"\\n📊 _Hệ thống tự động chấm điểm sinh học VPD Smart Farm_"
                        success = send_telegram_message(TELE_TOKEN, TELE_CHAT_ID, file_tele_msg)
                        if success: st.success("✅ Đã gửi toàn bộ dữ liệu báo cáo qua Telegram thành công!")
            else:
                st.info("Chưa có đủ dữ liệu thích hợp để bóc tách chu kỳ buổi.")

        except Exception as err:
            st.error(f"❌ Không thể xử lý file dữ liệu. Lỗi chi tiết: {err}")
