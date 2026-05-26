import streamlit as st
import pandas as pd
import json
import requests
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

# --- Thiết lập giao diện CSS chuẩn - Sửa lỗi che khuất tiêu đề ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow-y: auto !important; scroll-behavior: smooth; }
    .block-container { padding-top: 3.5rem !important; padding-bottom: 2rem; padding-left: 1.5rem; padding-right: 1.5rem; }
    
    .danger-box-red { padding: 12px; background-color: #C0392B; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-yellow { padding: 12px; background-color: #F39C12; border-left: 6px solid #17202A; color: #FFFFFF; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .upload-header { font-size: 15px; font-weight: bold; color: #114B72; border-bottom: 2px solid #114B72; padding-bottom: 4px; margin-bottom: 10px; }
    .metric-card-upload { background-color: #EAEDED; border: 2px solid #BDC3C7; padding: 10px; border-radius: 6px; text-align: center; }
    
    .big-vpd-box { background-color: #F8F9F9; border: 2px solid #2ECC71; border-radius: 8px; padding: 18px; text-align: center; margin-bottom: 10px; }
    .big-vpd-title { font-size: 14px; color: #7F8C8D; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    .big-vpd-value { font-size: 45px; color: #27AE60; font-weight: 900; line-height: 1.0; margin-top: 5px; margin-bottom: 5px; }
    .big-env-value { font-size: 20px; color: #2C3E50; font-weight: bold; margin-bottom: 12px; }
    
    .analysis-merge-box { background-color: #EAECEE; color: #2C3E50; padding: 12px 15px; border-radius: 6px; font-size: 13.5px; font-weight: 500; text-align: left; border-left: 5px solid #27AE60; line-height: 1.6; }
    
    .tele-status-active { background-color: #E8F8F5; color: #117A65; padding: 10px; border-left: 4px solid #1ABC9C; border-radius: 4px; font-weight: bold; margin-top: 5px; font-size: 13px;}
    </style>
    """, unsafe_allow_html=True)

# --- Khởi tạo dữ liệu Session State hệ thống ---
if 'temp' not in st.session_state: st.session_state.temp = 0.0
if 'rh' not in st.session_state: st.session_state.rh = 0.0
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'is_completed' not in st.session_state: st.session_state.is_completed = False 
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 
if 'simulated_time' not in st.session_state: st.session_state.simulated_time = "2026-05-24 07:00:00"

# Quản lý phản hồi Telegram và thông báo log trên Web
if 'last_update_id' not in st.session_state: st.session_state.last_update_id = 0
if 'tele_intervention_log' not in st.session_state: st.session_state.tele_intervention_log = "Chưa nhận lệnh điều khiển từ Telegram."
if 'forced_trend' not in st.session_state: st.session_state.forced_trend = None

PLANT_PRESETS = {
    "🍓 Dâu tây Đà Lạt (Giai đoạn trái)": {
        "🌅 Sáng (05h-10h)": (0.5, 0.9), "☀️ Trưa (10h-15h)": (0.7, 1.2), 
        "🌇 Chiều (15h-19h)": (0.6, 1.0), "🌌 Tối (19h-23h)": (0.4, 0.8), "🌙 Khuya (23h-05h)": (0.3, 0.7)
    },
    "🌹 Hoa hồng nhà kính": {
        "🌅 Sáng (05h-10h)": (0.6, 1.1), "☀️ Trưa (10h-15h)": (0.8, 1.4), 
        "🌇 Chiều (15h-19h)": (0.7, 1.2), "🌌 Tối (19h-23h)": (0.5, 0.9), "🌙 Khuya (23h-05h)": (0.4, 0.8)
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
    if "Nóng" in status:
        if temp >= 27.0: return "🔥 LỖI NHIỆT ĐỘ: Trời quá nóng gắt.", "Kéo rèm lưới chắn nắng + Bật quạt thông gió công suất cao."
        else: return "🌵 LỖI ĐỘ ẨM: Không khí quá khô hanh.", "Bật hệ thống phun sương hạt mịn bù ẩm khẩn cấp."
    elif "Ẩm" in status:
        if rh >= 85.0: return "🌧️ LỖI ĐỘ ẨM: Không khí quá ẩm ướt bí bách.", "Bật quạt đối lưu đảo gió + Mở quạt hút xả ẩm."
        else: return "🥶 LỖI NHIỆT ĐỘ: Trời lạnh sâu làm co ẩm.", "Đóng kín rèm giữ ấm + Bật đèn sưởi nhiệt."
    return "🟩 Môi trường hoàn hảo", "Môi trường đang đẹp, không cần can thiệp."

# --- Hàm gửi tin nhắn Telegram tích hợp Nút bấm tương tác (Inline Keyboard) ---
def send_telegram_with_buttons(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🛠️ Đã bật can thiệp phần cứng", "callback_data": "HARDWARE_ACTIVATED"},
                    {"text": "✅ Bỏ qua", "callback_data": "IGNORE_ALERT"}
                ]
            ]
        }
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.json()
    except:
        return None

# --- Hàm check dữ liệu phản hồi (Long Polling) từ người dùng trên Telegram ---
def check_telegram_feedback():
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/getUpdates"
    params = {"offset": st.session_state.last_update_id + 1, "timeout": 1}
    try:
        response = requests.get(url, params=params, timeout=3).json()
        if "result" in response:
            for update in response["result"]:
                st.session_state.last_update_id = update["update_id"]
                if "callback_query" in update:
                    data = update["callback_query"]["data"]
                    chat_id = str(update["callback_query"]["message"]["chat"]["id"])
                    
                    if chat_id == TELE_CHAT_ID:
                        if data == "HARDWARE_ACTIVATED":
                            st.session_state.forced_trend = "OPTIMIZE"
                            st.session_state.tele_intervention_log = f"⚡ [{datetime.now().strftime('%H:%M:%S')}] Đã nhận lệnh can thiệp từ Tele! Đang ép luồng IoT giảm tải."
                            # Trả lời Telegram xác nhận thành công
                            requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", json={"callback_query_id": update["callback_query"]["id"], "text": "🚀 Đã kích hoạt phản hồi IoT trên Web!"})
                        elif data == "IGNORE_ALERT":
                            st.session_state.tele_intervention_log = f"💤 [{datetime.now().strftime('%H:%M:%S')}] Nhà vườn bấm bỏ qua cảnh báo trên Telegram."
                            requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", json={"callback_query_id": update["callback_query"]["id"], "text": "Đã ghi nhận bỏ qua."})
    except:
        pass

def trigger_new_data(plant_matrix):
    # Trước khi tạo dữ liệu mới, quét kiểm tra xem người dùng có bấm nút trên Tele không
    check_telegram_feedback()
    
    current_sim_datetime = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    current_date_str = current_sim_datetime.strftime("Ngày %d/%m")
    
    base_temp, base_rh = get_weather_by_time(current_sim_datetime)
    
    # --- 🔄 VÒNG PHẢN HỒI THEO LỆNH TỪ TELEGRAM ---
    if st.session_state.forced_trend == "OPTIMIZE":
        # Xác định chu kỳ trước đó bị Nóng hay Ẩm để ép dữ liệu chạy ngược lại
        if st.session_state.history and "Ẩm" in st.session_state.history[0]["Trạng thái"]:
            # Đang Quá Ẩm -> Ép giảm mạnh độ ẩm, tăng nhiệt độ
            st.session_state.temp = round(base_temp + 2.0, 1)
            st.session_state.rh = round(max(base_rh - 25.0, 55.0), 1)
        else:
            # Đang Quá Nóng -> Ép giảm mạnh nhiệt độ, tăng bù ẩm (Giống như phun sương tưới nước)
            st.session_state.temp = round(base_temp - 5.0, 1)
            st.session_state.rh = round(min(base_rh + 20.0, 75.0), 1)
        
        # Reset lệnh ép sau khi đã phản hồi thành công vào chu kỳ số liệu này
        st.session_state.forced_trend = None
    else:
        # Nếu không có can thiệp từ xa, số liệu lấy tự nhiên theo thời tiết nhà kính mặc định
        st.session_state.temp, st.session_state.rh = base_temp, base_rh

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
    
    reason_text, action_text = get_detailed_analysis_and_action(status_text, st.session_state.temp, st.session_state.rh)

    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": current_date_str,
        "Thời gian mô phỏng": current_sim_datetime, "Hiển thị Giờ": current_sim_datetime.strftime("%H:%M"),
        "datetime_internal": current_sim_datetime, "Nhiệt độ (°C)": st.session_state.temp, "Độ ẩm (%)": st.session_state.rh,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text
    })

    # Nếu phát hiện lỗi lệch chuẩn -> Gửi tin nhắn chứa nút bấm tương tác qua Telegram luôn
    if TELE_TOKEN and TELE_CHAT_ID and status_text != "🟩 Lý Tưởng":
        unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
        h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
        trend, _ = predict_vpd_trend_v3(h_latest, current_sim_datetime.hour, plant_matrix)
        clean_trend = trend.replace("Xu hướng:", "").strip()
        
        msg = (f"⚠️ *PHÁT HIỆN LỆCH CHUẨN SINH HỌC*\n⏰ Thời gian: {current_date_str} - {current_sim_datetime.strftime('%H:%M')} ({buoi_hien_tai})\n"
               f"📊 Thiết bị đo: {st.session_state.temp}°C | Độ ẩm {st.session_state.rh}%\n"
               f"📉 *VPD Thực Tế:* *{new_vpd:.2f} kPa* (Ngưỡng chuẩn: {v_min}-{v_max})\n"
               f"📢 *Tình trạng:* {status_text}\n"
               f"🛠 *Hành động khuyên dùng:* *{action_text}*\n"
               f"🔮 _Chọn nút bấm bên dưới để gửi lệnh phản hồi phần cứng về Web:_")
        send_telegram_with_buttons(TELE_TOKEN, TELE_CHAT_ID, msg)
    
    next_dt = current_sim_datetime + timedelta(minutes=10)
    if next_dt.hour == 0 and next_dt.minute == 0:
        st.session_state.is_running = False; st.session_state.is_completed = True   
    st.session_state.simulated_time = next_dt.strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# 🧭 MENU ĐIỀU HƯỚNG
# ==========================================
st.sidebar.markdown("## 🧭 MENU CHỨC NĂNG")
app_mode = st.sidebar.selectbox("Chọn Tag công việc cần thực hiện:", ["🌿 VPD Realtime & Mô Phỏng", "📥 Phân Tích File IoT JSON"])

if app_mode == "🌿 VPD Realtime & Mô Phỏng":
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 HỆ THỐNG GIÁM SÁT VPD REALTIME & MÔ PHỎNG</h2>", unsafe_allow_html=True)
    
    left_col, right_col = st.columns([3, 7])
    with left_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📋 CẤU HÌNH MA TRẬN VPD THEO BUỔI</h3>", unsafe_allow_html=True)
        preset_choice = st.selectbox("Chọn giống cây áp ma trận mẫu:", list(PLANT_PRESETS.keys()))
        
        if preset_choice != st.session_state.prev_preset:
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
            
            with st.container(border=True):
                st.markdown(f"⏰ **Thời gian:** `{sim_dt.strftime('%H:%M')}` | ⏳ **Chu kỳ kế:** `{st.session_state.countdown}s`")
                st.markdown(f"""
                <div class="big-vpd-box">
                    <div class="big-vpd-title">🌿 CHỈ SỐ VPD THỰC TẾ TRÊN LÁ</div>
                    <div class="big-vpd-value">{v_calc:.2f} kPa</div>
                    <div class="big-env-value">🌡️ {st.session_state.temp}°C  &nbsp;|&nbsp;  💧 {st.session_state.rh}%</div>
                    <div class="analysis-merge-box">
                        🔍 <b>Nguyên nhân nhà vườn:</b> {reason_rt}<br>
                        🛠️ <b>Cách xử lý ngay:</b> <span style="color:#C0392B; font-weight:bold;">{action_rt}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Hiển thị nhật ký bắt tương tác từ xa Telegram ngay trên màn hình Web
                st.markdown(f"<div class='tele-status-active'>🤖 Trạng thái tương tác Telegram:<br><span style='font-weight:normal;color:#2C3E50;'>{st.session_state.tele_intervention_log}</span></div>", unsafe_allow_html=True)
                
        live_monitor_panel()

    with right_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📊 PHÂN TÍCH DIỄN BIẾN CHU KỲ PHÒNG DỊCH</h3>", unsafe_allow_html=True)
        if st.session_state.history:
            u_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            sel_day = st.selectbox("Chọn ngày lịch sử xem lại:", u_days, label_visibility="collapsed")
            df_all = pd.DataFrame(st.session_state.history)
            df_f = df_all[df_all["Ngày"] == sel_day].iloc[::-1].copy()
            
            st.altair_chart(draw_vpd_chart(df_f, 0.5, 1.2), use_container_width=True)
            st.altair_chart(draw_combined_temp_humidity_chart(df_f), use_container_width=True)
            
            st.markdown("##### 📋 BẢNG NHẬT KÝ CHI TIẾT ĐIỂM DỮ LIỆU CHU KỲ")
            st.dataframe(df_f[["STT", "Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True)
