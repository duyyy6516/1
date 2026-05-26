import streamlit as st
import pandas as pd
import json
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

# --- Khởi tạo dữ liệu Session State hệ thống ---
if 'temp' not in st.session_state: st.session_state.temp = 0.0
if 'rh' not in st.session_state: st.session_state.rh = 0.0
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'is_completed' not in st.session_state: st.session_state.is_completed = False 
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 
if 'simulated_time' not in st.session_state: st.session_state.simulated_time = "2026-05-24 07:00:00"

# --- 🌿 MA TRẬN VPD ĐƯỢC CHIA THÊM TỪNG LOẠI CÂY TRỒNG CHI TIẾT ---
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
    },
    "🪴 Lan Hồ Điệp / Cây nuôi cấy mô": {
        "🌅 Sáng (05h-10h)": (0.3, 0.7), "☀️ Trưa (10h-15h)": (0.5, 0.9), 
        "🌇 Chiều (15h-19h)": (0.4, 0.8), "🌌 Tối (19h-23h)": (0.3, 0.6), "🌙 Khuya (23h-05h)": (0.2, 0.5)
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
        if temp >= 27.0:
            reason = "🔥 Nóng do Nhiệt độ tăng cao (Bức xạ mặt trời hấp nhiệt nhà kính)"
            action = "Kéo rèm chắn nắng đỉnh 70% + Bật quạt thông gió xả nhiệt gắt."
        else:
            reason = "🌵 Nóng do Độ ẩm tụt quá thấp (Hệ thống thông gió quá mức/Khí hậu hanh)"
            action = "Bật phun sương hạt mịn ngắt quãng để bù ẩm nhanh, tránh sốc khí khổng."
        return reason, action
    elif "Ẩm" in status:
        if rh >= 85.0:
            reason = "🌧️ Ẩm do Độ ẩm bão hòa (Đất ướt đọng hơi nước, thiếu lưu thông khí)"
            action = "Bật quạt đối lưu tán cây + Bật quạt hút xả ẩm cưỡng bức. Ngắt tưới."
        else:
            reason = "🥶 Ẩm do Nhiệt độ tụt thấp (Không khí co lại làm tăng độ ẩm tương đối)"
            action = "Đóng kín rèm hông giữ nhiệt ấm + Đốt đèn nhiệt hoặc chạy quạt đảo khí trần."
        return reason, action
    return "🟩 Môi trường dải lý tưởng ổn định", "Duy trì trạng thái tự động tự cân bằng hiện tại."

def trigger_new_data(plant_matrix):
    current_sim_datetime = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    current_date_str = current_sim_datetime.strftime("Ngày %d/%m")
    st.session_state.temp, st.session_state.rh = get_weather_by_time(current_sim_datetime)
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

    # --- 🎯 ĐÚNG YÊU CẦU: CHỈ DUY NHẤT LÝ TƯỞNG LÀ KHÔNG BÁO (Bỏ toàn bộ is_near_danger) ---
    if TELE_TOKEN and TELE_CHAT_ID:
        if status_text != "🟩 Lý Tưởng":
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            trend, _ = predict_vpd_trend_v3(h_latest, current_sim_datetime.hour, plant_matrix)
            clean_trend = trend.replace("Xu hướng:", "").strip()
            
            msg = (f"🌿 *VPD SMART ALARM*\n⏰ {current_date_str} - {current_sim_datetime.strftime('%H:%M')} ({buoi_hien_tai})\n"
                   f"📊 Môi trường: {st.session_state.temp}°C | {st.session_state.rh}%\n"
                   f"*VPD thực tế:* *{new_vpd:.2f} kPa* (Chuẩn dải mục tiêu: {v_min}-{v_max})\n"
                   f"📢 *Hiện trạng:* {status_text}\n"
                   f"🔍 *Nguyên nhân:* _{reason_text}_\n"
                   f"🛠️ *Hướng xử lý:* *{action_text}*\n"
                   f"🔮 *Dự báo:* _{clean_trend}_")
            send_telegram_message(TELE_TOKEN, TELE_CHAT_ID, msg)
    
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
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 HỆ THỐNG GIÁM SÁT VPD REALTIME & MÔ PHỎNG</h2>", unsafe_allow_html=True)
    
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
                        🔍 <b>Lý do:</b> {reason_rt}<br>
                        🛠️ <b>Hướng xử lý:</b> <span style="color:#C0392B; font-weight:bold;">{action_rt}</span><br>
                        🔮 <b>Xu hướng:</b> {clean_trend_rt}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        live_monitor_panel()

        if st.session_state.history:
            st.markdown("### 🛠️ KHUYẾN NGHỊ ĐIỀU KHIỂN PHẦN CỨNG LẬP TỨC")
            cur_v = st.session_state.history[0]["VPD (kPa)"]
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            b_hien_tai = get_biological_block(sim_dt.hour)
            v_min, v_max = st.session_state.current_matrix[b_hien_tai]
            
            if cur_v >= v_max + 0.5:
                sub_reason = "Do NHIỆT ĐỘ cao ngất" if st.session_state.temp > 28.0 else "Do ĐỘ ẨM tụt quá sâu"
                st.markdown(f"<div class='danger-box-red'>🚨 QUÁ NÓNG ({sub_reason}): Bật phun sương hạt mịn full công suất + Mở rèm đỉnh đón gió giải nhiệt!</div>", unsafe_allow_html=True)
            elif cur_v > v_max:
                sub_reason = "Do không khí hanh khô" if st.session_state.rh < 50.0 else "Do hấp nhiệt nhà kính"
                if (v_max + 0.5) - cur_v <= 0.1:
                    st.markdown(f"<div class='danger-box-red'>⚠️ SẮP QUÁ NÓNG (Cách ranh giới biến cố {((v_max+0.5)-cur_v):.2f} kPa): Kích hoạt khẩn cấp rèm chắn nắng!</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='danger-box-yellow'>💛 NÓNG ({sub_reason}): Kéo lưới cắt nắng, bật phun sương ngắt quãng giảm nhiệt.</div>", unsafe_allow_html=True)
            elif cur_v < v_min - 0.2:
                sub_reason = "Do ĐỘ ẨM tích tụ bão hòa" if st.session_state.rh > 85.0 else "Do TRỜI LẠNH SÂU"
                st.markdown(f"<div class='danger-box-darkblue'>🔵 QUÁ ẨM ({sub_reason}): Bật quạt đối lưu tán cây, khép ngay hệ thống tưới nhỏ giọt!</div>", unsafe_allow_html=True)
            elif cur_v < v_min:
                sub_reason = "Do đọng hơi nước" if st.session_state.rh > 80.0 else "Do nhiệt độ giảm"
                if cur_v - (v_min - 0.2) <= 0.1:
                    st.markdown(f"<div class='danger-box-darkblue'>⚠️ SẮP QUÁ ẨM (Cách ranh giới đọng sương {(cur_v-(v_min-0.2)):.2f} kPa): Bật toàn bộ quạt hút cưỡng bức xả ẩm!</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='danger-box-lightblue'>🌐 Ẩm ({sub_reason}): Hé bớt rèm hông tăng lưu thông không khí tự nhiên tự hủy ẩm.</div>", unsafe_allow_html=True)
            else:
                st.success("🟩 LÝ TƯỞNG: Môi trường hoàn hảo cho cây quang hợp. Duy trì trạng thái ổn định.")

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
            v_min, v_max = st.session_state.current_matrix[b_hien_tai]
            
            st.markdown("**🎨 Khối màu nền phân tầng:** 🔵 *Dưới ngưỡng (Quá Ẩm)* | 🟢 *Trong dải lý tưởng (Tối ưu)* | 🔴 *Trên ngưỡng (Quá Nóng)*")
            
            st.altair_chart(draw_vpd_chart(df_f, v_min, v_max), use_container_width=True)
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
    
    f_left, f_right = st.columns([3, 7])
    with f_left:
        with st.container(border=True):
            st.markdown("<div class='upload-header'>🌿 THIẾT LẬP MA TRẬN ÁP DỤNG TRÊN FILE</div>", unsafe_allow_html=True)
            f_preset_choice = st.selectbox("Chọn cấu hình chuẩn áp vào file dữ liệu:", list(PLANT_PRESETS.keys()) + ["🛠️ Tùy chỉnh thủ công toàn bộ"], key="sb_file")
            
            if 'file_matrix' not in st.session_state or f_preset_choice != "🛠️ Tùy chỉnh thủ công toàn bộ":
                if f_preset_choice != "🛠️ Tùy chỉnh thủ công toàn bộ":
                    st.session_state.file_matrix = PLANT_PRESETS[f_preset_choice].copy()
                else:
                    st.session_state.file_matrix = PLANT_PRESETS["🍓 Dâu tây Đà Lạt (Giai đoạn trái)"].copy()
                
            f_sáng = st.slider("🌅 Sáng (05h-10h):", 0.0, 3.0, st.session_state.file_matrix["🌅 Sáng (05h-10h)"], 0.1, key="fs_1")
            f_trưa = st.slider("☀️ Trưa (10h-15h):", 0.0, 3.0, st.session_state.file_matrix["☀️ Trưa (10h-15h)"], 0.1, key="fs_2")
            f_chiều = st.slider("🌇 Chiều (15h-19h):", 0.0, 3.0, st.session_state.file_matrix["🌇 Chiều (15h-19h)"], 0.1, key="fs_3")
            f_tối = st.slider("🌌 Tối (19h-23h):", 0.0, 3.0, st.session_state.file_matrix["🌌 Tối (19h-23h)"], 0.1, key="fs_4")
            f_khuya = st.slider("🌙 Khuya (23h-05h):", 0.0, 3.0, st.session_state.file_matrix["🌙 Khuya (23h-05h)"], 0.1, key="fs_5")
            
            st.session_state.file_matrix = {
                "🌅 Sáng (05h-10h)": f_sáng, "☀️ Trưa (10h-15h)": f_trưa,
                "🌇 Chiều (15h-19h)": f_chiều, "🌌 Tối (19h-23h)": f_tối, "🌙 Khuya (23h-05h)": f_khuya
            }
            
    with f_right:
        with st.container(border=True):
            st.markdown("<div class='upload-header'>📥 CHỌN TẢI FILE & CHẾ ĐỘ LỌC GỘP CHU KỲ</div>", unsafe_allow_html=True)
            uploaded_file = st.file_uploader("Kéo thả file nhật ký trạm IoT (.json, .csv, .xlsx):", type=["json", "csv", "xlsx"])
            
            time_filter_option = st.selectbox(
                "📆 Cấu hình bộ lọc gom dữ liệu theo mốc thời gian:",
                [
                    "📊 Tự động phân tích thông minh theo File", 
                    "📆 Chọn một ngày cụ thể trên lịch", 
                    "📅 Xem theo Tuần (Tự chọn ngày bắt đầu)", 
                    "📆 Xem theo Tháng (Tự chọn ngày bắt đầu)", 
                    "📅 Xem theo Năm (Tự chọn ngày bắt đầu)"
                ]
            )
        
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.json'):
                json_data = json.load(uploaded_file)
                if isinstance(json_data, list):
                    df_upload = pd.DataFrame(json_data)
                elif isinstance(json_data, dict):
                    first_val = next(iter(json_data.values()))
                    if isinstance(first_val, (list, dict)):
                        list_key = None
                        for k, v in json_data.items():
                            if isinstance(v, list):
                                list_key = k
                                break
                        df_upload = pd.DataFrame(json_data[list_key]) if list_key else pd.DataFrame([json_data])
                    else:
                        df_upload = pd.DataFrame([json_data])
                else:
                    df_upload = pd.DataFrame(json_data)
            elif uploaded_file.name.endswith('.csv'):
                df_upload = pd.read_csv(uploaded_file)
            else:
                df_upload = pd.read_excel(uploaded_file)

            col_temp_raw = 'tempKK' if 'tempKK' in df_upload.columns else None
            col_rh_raw = 'humiKK' if 'humiKK' in df_upload.columns else None
            col_time = 'Thời gian' if 'Thời gian' in df_upload.columns else None

            if not col_temp_raw or not col_rh_raw or not col_time:
                for col in df_upload.columns:
                    c_low = str(col).lower().strip()
                    if 'tempkk' in c_low or 'nhiệt độ' in c_low: col_temp_raw = col
                    if 'humikk' in c_low or 'độ ẩm' in c_low: col_rh_raw = col
                    if any(k in c_low for k in ['thời gian', 'time', 'timestamp']): col_time = col

            if not col_temp_raw or not col_rh_raw:
                st.error("❌ Không tìm thấy cột dữ liệu cảm biến `tempKK` hoặc `humiKK` trong file.")
                st.stop()

            df_clean_raw = df_upload[[col_time, col_temp_raw, col_rh_raw]].dropna().copy()
            df_clean_raw[col_temp_raw] = pd.to_numeric(df_clean_raw[col_temp_raw], errors='coerce')
            df_clean_raw[col_rh_raw] = pd.to_numeric(df_clean_raw[col_rh_raw], errors='coerce')
            df_clean_raw = df_clean_raw.dropna()

            df_clean = pd.DataFrame()
            df_clean[col_time] = df_clean_raw[col_time]
            # Giữ nguyên cấu trúc gán cặp gốc từ file cũ 
            df_clean["temp_fixed"] = df_clean_raw[col_rh_raw]   
            df_clean["rh_fixed"] = df_clean_raw[col_temp_raw]   

            raw_datetimes = []
            for val in df_clean[col_time].astype(str):
                val_str = val.strip()
                try:
                    if " " in val_str and "-" in val_str.split(" ")[1]:
                        date_p, time_p = val_str.split(" ")
                        raw_datetimes.append(datetime.strptime(f"{date_p} {time_p.replace('-', ':')}", "%Y-%m-%d %H:%M:%S"))
                    else:
                        raw_datetimes.append(pd.to_datetime(val_str))
                except:
                    raw_datetimes.append(datetime.now())

            df_clean["datetime_internal"] = raw_datetimes
            df_clean["only_date"] = df_clean["datetime_internal"].dt.date
            df_clean = df_clean.sort_values("datetime_internal")
            df_clean["VPD_raw"] = df_clean.apply(lambda row: calculate_vpd(row["temp_fixed"], row["rh_fixed"]), axis=1)

            min_dt_in_file = df_clean["datetime_internal"].min()
            max_dt_in_file = df_clean["datetime_internal"].max()
            available_dates = sorted(df_clean["only_date"].unique())
            
            is_single_day = False
            resample_rule = "10min"
            date_format_rule = "%H:%M"
            
            if "Chọn một ngày cụ thể" in time_filter_option:
                selected_date = st.date_input("👇 Chọn ngày xem chi tiết trên lịch:", value=available_dates[0] if available_dates else datetime.now().date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date())
                df_filtered = df_clean[df_clean["only_date"] == selected_date].copy()
                is_single_day = True
                resample_rule = "10min"
                date_format_rule = "%H:%M"
                
            elif "Xem theo Tuần" in time_filter_option:
                st.markdown("<p style='color:#114B72; font-weight:bold; margin-bottom:2px;'>📅 Chọn ngày bắt đầu của Tuần:</p>", unsafe_allow_html=True)
                start_date = st.date_input("Ngày xuất phát (Hệ thống lấy tiếp 7 ngày):", value=min_dt_in_file.date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date(), key="week_start_picker")
                end_date = start_date + timedelta(days=7) 
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < end_date)].copy()
                resample_rule = "1D"
                date_format_rule = "%d/%m"
                st.info(f"📅 Đang hiển thị chu kỳ tuần: Từ **{start_date.strftime('%d/%m/%Y')}** đến ngày **{(end_date - timedelta(days=1)).strftime('%d/%m/%Y')}**")

            elif "Xem theo Tháng" in time_filter_option:
                st.markdown("<p style='color:#114B72; font-weight:bold; margin-bottom:2px;'>📅 Chọn ngày bắt đầu của Tháng:</p>", unsafe_allow_html=True)
                start_date = st.date_input("Ngày xuất phát (Hệ thống lấy tiếp 30 ngày):", value=min_dt_in_file.date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date(), key="month_start_picker")
                end_date = start_date + timedelta(days=30) 
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < end_date)].copy()
                resample_rule = "1D"
                date_format_rule = "%d/%m"
                st.info(f"📅 Đang hiển thị chu kỳ tháng: Từ **{start_date.strftime('%d/%m/%Y')}** đến ngày **{(end_date - timedelta(days=1)).strftime('%d/%m/%Y')}**")

            elif "Xem theo Năm" in time_filter_option:
                st.markdown("<p style='color:#114B72; font-weight:bold; margin-bottom:2px;'>📅 Chọn ngày bắt đầu của Năm:</p>", unsafe_allow_html=True)
                start_date = st.date_input("Ngày xuất phát (Hệ thống lấy tiếp 365 ngày):", value=min_dt_in_file.date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date(), key="year_start_picker")
                end_date = start_date + timedelta(days=365) 
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < end_date)].copy()
                resample_rule = "1ME"
                date_format_rule = "%m/%Y"
                st.info(f"📅 Đang hiển thị chu kỳ năm: Từ **{start_date.strftime('%d/%m/%Y')}** đến ngày **{(end_date - timedelta(days=1)).strftime('%d/%m/%Y')}**")
            
            else: 
                df_filtered = df_clean.copy()
                if len(available_dates) <= 1:
                    is_single_day = True
                    resample_rule = "10min"
                    date_format_rule = "%H:%M"
                else:
                    resample_rule = "1D"
                    date_format_rule = "%d/%m"

            df_for_block_analysis = df_filtered.copy()

            if df_filtered.empty:
                st.markdown("""
                <div style='padding: 20px; background-color: #FDEDEC; border-left: 6px solid #C0392B; color: #922B21; border-radius: 4px; margin-top: 15px;'>
                    🛑 <b>KHÔNG CÓ BẢN GHI DỮ LIỆU:</b> Trong khoảng thời gian bạn chọn bắt đầu ở trên, không tìm thấy điểm lưu trữ quan trắc nào trong File! Vui lòng chọn một ngày bắt đầu khác.
                </div>
                """, unsafe_allow_html=True)
                st.stop()

            df_resample_input = df_filtered[["datetime_internal", "temp_fixed", "rh_fixed", "VPD_raw"]].copy()
            df_resample_input.set_index("datetime_internal", inplace=True)
            
            df_resampled = df_resample_input.resample(resample_rule).mean().dropna()
            df_resampled = df_resampled.reset_index()
            df_resampled["Hiển thị Giờ"] = df_resampled["datetime_internal"].dt.strftime(date_format_rule)

            if df_resampled.empty:
                st.warning("⚠️ Không có dữ liệu sau khi gộp chu kỳ phân tích.")
                st.stop()

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

            st.markdown("<div style='margin-top:12px; margin-bottom:5px; font-weight:bold; color:#114B72;'>📊 TỔNG QUAN CHU KỲ SAU KHI GỘP SỐ LIỆU FILE</div>", unsafe_allow_html=True)
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.markdown(f"<div class='metric-card-upload'><span style='font-size:12px;color:grey;'>📈 VPD TRUNG BÌNH</span><br><b style='font-size:18px;color:#1E8449;'>{df_processed['VPD (kPa)'].mean():.2f} kPa</b></div>", unsafe_allow_html=True)
            m_col2.markdown(f"<div class='metric-card-upload'><span style='font-size:12px;color:grey;'>🌡️ NHIỆT ĐỘ TRUNG BÌNH</span><br><b style='font-size:18px;color:#C0392B;'>{df_processed['Nhiệt độ (°C)'].mean():.1f} °C</b></div>", unsafe_allow_html=True)
            m_col3.markdown(f"<div class='metric-card-upload'><span style='font-size:12px;color:grey;'>💧 ĐỘ ẨM TRUNG BÌNH</span><br><b style='font-size:18px;color:#2980B9;'>{df_processed['Độ ẩm (%)'].mean():.1f} %</b></div>", unsafe_allow_html=True)
            m_col4.markdown(f"<div class='metric-card-upload'><span style='font-size:12px;color:grey;'>📋 CHẾ ĐỘ GỘP CHU KỲ</span><br><b style='font-size:14px;color:#2C3E50;'>{time_filter_option.split('(')[0].replace('📊 ','').replace('📆 ','').replace('📅 ','')}</b></div>", unsafe_allow_html=True)

            adv_res = calculate_plant_stress_hours(df_processed, st.session_state.file_matrix, "1 Ngày gần nhất" if is_single_day else "1 Tuần gần nhất")
            st.markdown("<div style='margin-top:15px; font-weight:bold; color:#B71C1C;'>⚠️ ĐÁNH GIÁ CHUYÊN SÂU: ÁP LỰC STRESS KHÍ KHỔNG CỦA CÂY TRỒNG</div>", unsafe_allow_html=True)
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                d_hrs = adv_res["dry_hours"]
                if d_hrs > 2.0: st.error(f"🚨 **Stress Khô Nóng:** Khí khổng bị ép khép chặt suốt **{d_hrs} giờ**. Cây ngừng quang hợp!")
                else: st.success(f"✅ **Áp lực khô:** An toàn.")
            with s_col2:
                w_hrs = adv_res["wet_hours"]
                if w_hrs > 4.0: st.warning(f"🟦 **Stress Ẩm Ướt:** Môi trường đọng ẩm liên tục **{w_hrs} giờ**. Nguy cơ bùng dịch nấm phấn trắng!")
                else: st.success(f"✅ **Áp lực ẩm:** An toàn.")

            res_left, res_right = st.columns([6.2, 3.8])
            with res_left:
                st.markdown("<div style='font-weight:bold; color:#114B72; margin-bottom:5px;'>📈 CÁC BIỂU ĐỒ ĐỐI CHIẾU TRỰC QUAN TRÊN FILE</div>", unsafe_allow_html=True)
                f_tab1, f_tab2 = st.tabs(["🎯 Chỉ số VPD File", "🌡️💧 Đường thẳng cặp Nhiệt độ & Độ ẩm"])
                f_min_sample, f_max_sample = st.session_state.file_matrix["🌅 Sáng (05h-10h)"]
                
                with f_tab1: 
                    st.altair_chart(draw_vpd_chart(df_processed, f_min_sample, f_max_sample), use_container_width=True)
                with f_tab2: 
                    st.altair_chart(draw_combined_temp_humidity_chart(df_processed), use_container_width=True)
            with res_right:
                st.markdown("<div style='font-weight:bold; color:#114B72; margin-bottom:5px;'>📋 NHẬT KÝ ĐIỂM GỘP CHU KỲ CHUYÊN SÂU</div>", unsafe_allow_html=True)
                preview_cols = ["Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]
                st.dataframe(df_processed[preview_cols].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True, height=270)

            st.markdown("---")
            st.markdown("##### 📊 BÁO CÁO PHÁN QUYẾT MA TRẬN BUỔI TỔNG HỢP CỦA FILE")
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
                        file_tele_msg = f"📂 *BÁO CÁO CHU KỲ FILE*\n📦 File: `{uploaded_file.name}`\n🎯 Mô hình: *{f_preset_choice}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                        for _, r_data in df_block_report.iterrows():
                            file_tele_msg += f"Buổi *{r_data['Khoảng Buổi']}*\n▪️ Môi trường: {r_data['Nhiệt độ TB']} | {r_data['Độ ẩm TB']}\n▪️ VPD TB: *{r_data['VPD Trung Bình']}*\n▪️ Đánh giá: *{r_data['Đánh giá sinh học']}*\n▪️ Giải pháp: {r_data['Giải pháp kỹ thuật']}\n────────────────────\n"
                        file_tele_msg += f"\n📊 _Hệ thống tự động chấm điểm sinh học VPD Smart Farm_"
                        success = send_telegram_message(TELE_TOKEN, TELE_CHAT_ID, file_tele_msg)
                        if success: st.success("✅ Đã gửi toàn bộ dữ liệu báo cáo qua Telegram thành công!")
            else:
                st.info("Chưa có đủ dữ liệu thích hợp để bóc tách chu kỳ buổi.")

        except Exception as err:
            st.error(f"❌ Không thể xử lý cấu trúc file. Lỗi chi tiết: {err}")
    else:
        st.info("💡 **Hệ thống đang đợi file:** Vui lòng kéo và thả file nhật ký dạng `.json` hoặc file cảm biến IoT vào ô tải file ở trên để xem phân tích dữ liệu đối chiếu.")
