import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from calculations import calculate_vpd, get_weather_by_time
    from services import send_telegram_message, get_quick_solution
    from analytics import (
        analyze_day_by_blocks_rt, 
        predict_vpd_trend_v3, 
        calculate_plant_stress_hours
    )
    from charts import (
        draw_vpd_chart,
        draw_temp_humidity_combo_chart
    )
except ModuleNotFoundError as e:
    st.error(f"❌ Không tìm thấy module bổ trợ: {e.name}")
    st.stop()

st.set_page_config(page_title="VPD Farm Analytics", page_icon="🌿", layout="wide")

# CẤU TRÚC NGƯỠNG VPD ĐỘNG THEO THỜI ĐIỂM
DANH_SACH_CAY = {
    "🍓 Dâu tây Đà Lạt (Hoa / Trái)": {
        "Sang": (0.6, 0.9), "Trua": (0.8, 1.2), "Chieu": (0.7, 1.0), "Dem": (0.4, 0.7)
    },
    "🍓 Dâu tây Đà Lạt (Giai đoạn ngó/cây con)": {
        "Sang": (0.4, 0.6), "Trua": (0.5, 0.8), "Chieu": (0.4, 0.7), "Dem": (0.3, 0.5)
    },
    "🌹 Hoa hồng nhà kính (Đà Lạt)": {
        "Sang": (0.7, 1.1), "Trua": (0.9, 1.4), "Chieu": (0.8, 1.2), "Dem": (0.5, 0.8)
    },
    "🌼 Hoa cúc / Hoa đồng tiền": {
        "Sang": (0.6, 1.0), "Trua": (0.8, 1.3), "Chieu": (0.7, 1.1), "Dem": (0.4, 0.8)
    },
    "🍅 Cà chua bi / 🫑 Ớt chuông Palermo": {
        "Sang": (0.7, 1.2), "Trua": (0.9, 1.5), "Chieu": (0.8, 1.3), "Dem": (0.5, 0.9)
    },
    "🥦 Súp lơ xanh / Bắp cabbage baby": {
        "Sang": (0.5, 0.8), "Trua": (0.6, 1.1), "Chieu": (0.5, 0.9), "Dem": (0.4, 0.6)
    },
    "🥬 Xà lách Thủy canh (Lô lô, Romaine)": {
        "Sang": (0.4, 0.7), "Trua": (0.6, 1.0), "Chieu": (0.5, 0.8), "Dem": (0.3, 0.6)
    },
    "🌱 Cây giống trong vườn ươm": {
        "Sang": (0.3, 0.5), "Trua": (0.4, 0.7), "Chieu": (0.3, 0.6), "Dem": (0.2, 0.4)
    },
    "🛠️ Tùy chỉnh thủ công ngưỡng riêng": {
        "Sang": (0.6, 1.1), "Trua": (0.8, 1.4), "Chieu": (0.7, 1.2), "Dem": (0.5, 0.9)
    }
}
plant_list_keys = list(DANH_SACH_CAY.keys())

# Khởi tạo Session State
CHAU_HINH_MAC_DINH = {
    "temp": 24.0, "rh": 75.0, "countdown": 15,
    "is_running": False, "is_completed": False, "history": [],
    "stt_counter": 0, "plant_idx": 0,
    "h_sang": 5, "h_trua": 10, "h_chieu": 15, "h_dem": 19,
    "custom_sang": (0.6, 1.1), "custom_trua": (0.8, 1.4), "custom_chieu": (0.7, 1.2), "custom_dem": (0.5, 0.9),
    "simulated_time": "2026-05-24 07:00:00", "file_plant_idx": 0,
    "file_custom_sang": (0.6, 1.1), "file_custom_trua": (0.8, 1.4), "file_custom_chieu": (0.7, 1.2), "file_custom_dem": (0.5, 0.9),
    "tele_token_input": st.secrets.get("TELE_TOKEN", ""), 
    "tele_chat_id_input": st.secrets.get("TELE_CHAT_ID", "")
}
for key, val in CHAU_HINH_MAC_DINH.items():
    if key not in st.session_state:
        st.session_state[key] = val

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow-y: auto !important; scroll-behavior: smooth; }
    .block-container { padding: 2rem 1.5rem 4rem 1.5rem; }
    .danger-box-red { padding: 12px; background-color: #FFEBEE; border-left: 6px solid #FF1744; color: #B71C1C; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .danger-box-blue { padding: 12px; background-color: #E3F2FD; border-left: 6px solid #2979FF; color: #0D47A1; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
    .upload-header { font-size: 16px; font-weight: bold; color: #1A5276; border-bottom: 2px solid #D4E6F1; padding-bottom: 5px; margin-bottom: 12px; }
    .metric-card-upload { background-color: #F4F6F7; border: 1px solid #E5E7E9; padding: 10px; border-radius: 6px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- HÀM UTILS LOGIC ---
def get_time_block_key(hour):
    hs = st.session_state.h_sang
    ht = st.session_state.h_trua
    hc = st.session_state.h_chieu
    hd = st.session_state.h_dem
    if hs <= hour < ht: return "Sang"
    elif ht <= hour < hc: return "Trua"
    elif hc <= hour < hd: return "Chieu"
    else: return "Dem"

def get_current_vpd_range(plant_name, hour, is_file=False):
    if plant_name == "🛠️ Tùy chỉnh thủ công ngưỡng riêng":
        pfx = "file_custom_" if is_file else "custom_"
        blk = get_time_block_key(hour).lower()
        return st.session_state[f"{pfx}{blk}"]
    else:
        blk = get_time_block_key(hour)
        return DANH_SACH_CAY[plant_name][blk]

def style_status_rows(row):
    styles = [''] * len(row)
    try:
        idx = row.index.get_loc('Trạng thái')
        status = str(row['Trạng thái'])
        if "Lý tưởng" in status: styles[idx] = 'background-color: #E8F5E9; color: #1B5E20; font-weight: bold;'
        elif "Quá khô" in status: styles[idx] = 'background-color: #FFEBEE; color: #B71C1C; font-weight: bold;'
        elif "Quá ẩm" in status: styles[idx] = 'background-color: #E3F2FD; color: #0D47A1; font-weight: bold;'
    except KeyError: pass
    return styles

def setup_next_day():
    current_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    if current_dt.hour == 0 and current_dt.minute == 0:
        next_dt = current_dt + timedelta(hours=7)
    else:
        next_dt = current_dt + timedelta(days=1)
        next_dt = next_dt.replace(hour=7, minute=0, second=0)
    st.session_state.simulated_time = next_dt.strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.is_completed = False
    st.session_state.countdown = 15

def trigger_new_data():
    cur_sim = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    day_str = cur_sim.strftime("Ngày %d/%m")
    
    st.session_state.temp, st.session_state.rh = get_weather_by_time(cur_sim)
    st.session_state.countdown = 15 
    st.session_state.stt_counter += 1
    
    t_val, h_val = st.session_state.temp, st.session_state.rh
    new_vpd = calculate_vpd(t_val, h_val)
    
    cur_plant = plant_list_keys[st.session_state.plant_idx]
    v_min, v_max = get_current_vpd_range(cur_plant, cur_sim.hour, is_file=False)
    
    if new_vpd < v_min: status_text, tele_status = "⚠️ Quá ẩm", "🟦 QUÁ ẨM"
    elif new_vpd <= v_max: status_text, tele_status = "✅ Lý tưởng", "🟩 LÝ TƯỞNG"
    else: status_text, tele_status = "🚨 Quá khô", "🟥 QUÁ KHÔ"
    
    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": day_str,
        "Thời gian mô phỏng": cur_sim, "Hiển thị Giờ": cur_sim.strftime("%H:%M"),
        "datetime_internal": cur_sim, "Nhiệt độ (°C)": t_val, "Độ ẩm (%)": h_val,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text,
        "V_Min": v_min, "V_Max": v_max
    })
    
    t_token = st.session_state.tele_token_input
    t_chat_id = st.session_state.tele_chat_id_input
    if t_token and t_chat_id:
        try:
            sol = get_quick_solution(new_vpd, v_min, v_max, cur_sim.hour)
            u_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            lat_day = u_days[0] if u_days else day_str
            hist_lat = [r for r in st.session_state.history if r["Ngày"] == lat_day]
            trend, t_type = predict_vpd_trend_v3(hist_lat, cur_sim.hour, v_min, v_max)
            pfx = "🚨 [CẢNH BÁO SỚM] " if "CẢNH BÁO SỚM" in trend else ""
            
            msg = (
                f"🌿 **HỆ THỐNG VPD ĐÀ LẠT REALTIME**\n"
                f"⏰ {day_str} - {cur_sim.strftime('%H:%M')} (Khung: {get_time_block_key(cur_sim.hour)})\n"
                f"📊 Môi trường: {t_val}°C | {h_val}%\n"
                f"🎯 Ngưỡng động: {v_min:.1f} - {v_max:.1f} kPa\n\n"
                f"**1️⃣ Hiện trạng:** **{new_vpd:.2f} kPa** — {tele_status}\n"
                f"**2️⃣ Biện pháp:** *{sol}*\n"
                f"**3️⃣ Dự báo:** {pfx}*{trend}*"
            )
            send_telegram_message(t_token, t_chat_id, msg)
        except Exception: pass 
    
    nxt_sim = cur_sim + timedelta(minutes=10)
    if nxt_sim.hour == 0 and nxt_sim.minute == 0:
        st.session_state.is_running = False     
        st.session_state.is_completed = True   
    st.session_state.simulated_time = nxt_sim.strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# I. ĐIỀU CHỈNH GIAO DIỆN SIDEBAR TOÀN CỤC
# ==========================================
with st.sidebar:
    st.header("⚙️ CẤU HÌNH HỆ THỐNG")
    
    # 1. Trạm điều hành Realtime
    st.markdown("### 🤖 TRẠM ĐIỀU HÀNH")
    cb1, cb2 = st.columns(2)
    with cb1:
        if st.button("▶️ Bắt đầu", type="primary", use_container_width=True, disabled=st.session_state.is_running):
            if st.session_state.is_completed: setup_next_day()
            st.session_state.is_running = True
            if st.session_state.stt_counter == 0: trigger_new_data()
            st.rerun()
    with cb2:
        if st.button("⏸️ Tạm dừng", type="secondary", use_container_width=True, disabled=not st.session_state.is_running):
            st.session_state.is_running = False
            st.rerun()
            
    st.markdown("---")
    
    # 2. Lựa chọn loại cây trồng mô phỏng chính
    opt = st.selectbox("Chọn loại cây trồng", plant_list_keys, index=st.session_state.plant_idx, disabled=st.session_state.is_running)
    st.session_state.plant_idx = plant_list_keys.index(opt)
    
    # 3. Hộp thông tin mở rộng chứa các cài đặt sâu phân theo tabs
    with st.expander("⚙️ Tùy chỉnh Ngưỡng VPD & Cảnh báo", expanded=True):
        tab_nguong, tab_chuky, tab_tele = st.tabs(["Ngưỡng Cảnh Báo", "Chu Kỳ Thời Gian", "Cảnh báo Telegram"])
        
        with tab_nguong:
            is_custom = (opt == "🛠️ Tùy chỉnh thủ công ngưỡng riêng")
            
            # SÁNG
            st.markdown("**🌅 Khung Sáng**")
            c1, c2 = st.columns(2)
            with c1:
                v_min_s = st.number_input("Min Sáng", value=st.session_state.custom_sang[0] if is_custom else DANH_SACH_CAY[opt]["Sang"][0], step=0.1, format="%.1f", disabled=not is_custom, key="ns_min")
            with c2:
                v_max_s = st.number_input("Max Sáng", value=st.session_state.custom_sang[1] if is_custom else DANH_SACH_CAY[opt]["Sang"][1], step=0.1, format="%.1f", disabled=not is_custom, key="ns_max")
            
            # TRƯA
            st.markdown("**☀️ Khung Trưa**")
            c3, c4 = st.columns(2)
            with c3:
                v_min_t = st.number_input("Min Trưa", value=st.session_state.custom_trua[0] if is_custom else DANH_SACH_CAY[opt]["Trua"][0], step=0.1, format="%.1f", disabled=not is_custom, key="nt_min")
            with c4:
                v_max_t = st.number_input("Max Trưa", value=st.session_state.custom_trua[1] if is_custom else DANH_SACH_CAY[opt]["Trua"][1], step=0.1, format="%.1f", disabled=not is_custom, key="nt_max")
            
            # CHIỀU
            st.markdown("**🌇 Khung Chiều**")
            c5, c6 = st.columns(2)
            with c5:
                v_min_c = st.number_input("Min Chiều", value=st.session_state.custom_chieu[0] if is_custom else DANH_SACH_CAY[opt]["Chieu"][0], step=0.1, format="%.1f", disabled=not is_custom, key="nc_min")
            with c6:
                v_max_c = st.number_input("Max Chiều", value=st.session_state.custom_chieu[1] if is_custom else DANH_SACH_CAY[opt]["Chieu"][1], step=0.1, format="%.1f", disabled=not is_custom, key="nc_max")
                
            # ĐÊM
            st.markdown("**🌙 Khung Đêm**")
            c7, c8 = st.columns(2)
            with c7:
                v_min_d = st.number_input("Min Đêm", value=st.session_state.custom_dem[0] if is_custom else DANH_SACH_CAY[opt]["Dem"][0], step=0.1, format="%.1f", disabled=not is_custom, key="nd_min")
            with c8:
                v_max_d = st.number_input("Max Đêm", value=st.session_state.custom_dem[1] if is_custom else DANH_SACH_CAY[opt]["Dem"][1], step=0.1, format="%.1f", disabled=not is_custom, key="nd_max")
            
            if is_custom:
                st.session_state.custom_sang = (v_min_s, v_max_s)
                st.session_state.custom_trua = (v_min_t, v_max_t)
                st.session_state.custom_chieu = (v_min_c, v_max_c)
                st.session_state.custom_dem = (v_min_d, v_max_d)

        with tab_chuky:
            st.markdown("**⏱️ Định nghĩa mốc bắt đầu (Giờ)**")
            st.session_state.h_sang = st.slider("Bắt đầu Sáng:", 4, 8, st.session_state.h_sang)
            st.session_state.h_trua = st.slider("Bắt đầu Trưa:", 9, 12, st.session_state.h_trua)
            st.session_state.h_chieu = st.slider("Bắt đầu Chiều:", 13, 17, st.session_state.h_chieu)
            st.session_state.h_dem = st.slider("Bắt đầu Đêm:", 18, 22, st.session_state.h_dem)
            
        with tab_tele:
            st.markdown("**🔗 API Gateway Telegram**")
            st.session_state.tele_token_input = st.text_input("Bot Token:", value=st.session_state.tele_token_input, type="password")
            st.session_state.tele_chat_id_input = st.text_input("Chat ID nhận:", value=st.session_state.tele_chat_id_input)


# ==========================================
# II. KHÔNG GIAN GIAO DIỆN CHÍNH (MAIN VIEW)
# ==========================================
def render_realtime_analytics_panel():
    if not st.session_state.history:
        st.info("Chưa có số liệu lưu trữ trong phiên này.")
        return
        
    u_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
    f1, f2 = st.columns([8, 2])
    with f1:
        sel_day = st.selectbox("Lọc ngày dữ liệu:", u_days, label_visibility="collapsed")
    with f2:
        if st.button("🗑️ Reset All", use_container_width=True):
            st.session_state.update({"stt_counter": 0, "history": [], "simulated_time": "2026-05-24 07:00:00", "is_completed": False, "is_running": False})
            st.rerun()

    df_all = pd.DataFrame(st.session_state.history)
    df_f = df_all[df_all["Ngày"] == sel_day].iloc[::-1].copy()
    
    v_min_avg = df_f["V_Min"].mean() if "V_Min" in df_f.columns else 0.8
    v_max_avg = df_f["V_Max"].mean() if "V_Max" in df_f.columns else 1.2

    t1, t2, t3 = st.tabs(["📈 Biểu đồ biến thiên", "📊 Thống kê phiên buổi", "📋 Nhật ký số liệu chi tiết"])
    with t1:
        st.markdown("##### 🎯 Chỉ số Áp suất Hơi nước thâm hụt (VPD - kPa)")
        st.altair_chart(draw_vpd_chart(df_f, v_min_avg, v_max_avg), use_container_width=True)
        st.markdown("##### 🌡️💧 Tương quan biến thiên Nhiệt độ & Độ ẩm")
        st.altair_chart(draw_temp_humidity_combo_chart(df_f), use_container_width=True)
    with t2:
        st.dataframe(analyze_day_by_blocks_rt(st.session_state.history, v_min_avg, v_max_avg, sel_day), use_container_width=True, hide_index=True)
    with t3:
        df_f["Thời gian"] = df_f["Hiển thị Giờ"]
        st.dataframe(df_f[["STT", "Thời gian", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True)


@st.fragment(run_every=(1 if st.session_state.is_running else None))
def live_monitor():
    cur_plant = plant_list_keys[st.session_state.plant_idx]
    c_sim = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    v_min, v_max = get_current_vpd_range(cur_plant, c_sim.hour, is_file=False)

    if st.session_state.is_running:
        st.session_state.countdown -= 1
        if st.session_state.countdown < 0: 
            trigger_new_data()
            st.rerun()
            
    # Hiển thị tiêu đề động dựa trên chu kỳ thời gian
    st.header("📊 TỔNG QUAN VPD THỰC TẾ")
    st.caption(f"📌 Đang theo dõi mô hình: **{cur_plant}** | Khung giờ hiện tại: **{get_time_block_key(c_sim.hour)}** ({c_sim.strftime('Ngày %d/%m — %H:%M')})")
    
    if st.session_state.is_running: 
        st.caption(f"⏳ Tự động cập nhật số liệu sau: **{st.session_state.countdown} giây**")
    elif st.session_state.is_completed: 
        st.success("🏁 Hệ thống đã hoàn thành chu kỳ mô phỏng ngày!")

    # Thiết lập 3 Metric Cards hiển thị dữ liệu chính nằm ngang song song
    col1, col2, col3 = st.columns(3)
    
    v_res = calculate_vpd(st.session_state.temp, st.session_state.rh)
    
    if st.session_state.stt_counter == 0:
        col1.metric("Nhiệt độ", "-- °C")
        col2.metric("Độ ẩm", "-- %")
        col3.metric("VPD (kPa)", "--", delta="Chờ kích hoạt")
    else:
        lbl = "🟩 Lý tưởng" if v_min <= v_res <= v_max else ("🟦 Quá ẩm" if v_res < v_min else "🚨 Quá khô")
        col1.metric("Nhiệt độ", f"{st.session_state.temp:.1f} °C")
        col2.metric("Độ ẩm", f"{st.session_state.rh:.1f} %")
        col3.metric("VPD (kPa)", f"{v_res:.2f}", delta=lbl)
        
    # Khối hiển thị lệnh điều hành và cảnh báo sớm nâng cao
    if st.session_state.stt_counter > 0:
        with st.container(border=True):
            st.markdown("<p style='color:#2E7D32;font-weight:bold;margin-bottom:2px;'>🎯 TRUNG TÂM ĐIỀU HÀNH & GIẢI PHÁP REALTIME</p>", unsafe_allow_html=True)
            u_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            hist_lat = [r for r in st.session_state.history if r["Ngày"] == (u_days[0] if u_days else c_sim.strftime("Ngày %d/%m"))]
            trnd, t_tp = predict_vpd_trend_v3(hist_lat, c_sim.hour, v_min, v_max)
            
            if t_tp == "danger_red": st.markdown(f"<div class='danger-box-red'>🚨 {trnd}</div>", unsafe_allow_html=True)
            elif t_tp == "danger_blue": st.markdown(f"<div class='danger-box-blue'>🚨 {trnd}</div>", unsafe_allow_html=True)
            
            st.markdown(f"Ngưỡng chuẩn tối ưu: `{v_min} - {v_max} kPa`")
            st.markdown(f"**💡 Khuyến nghị xử lý nông học:** _{get_quick_solution(v_res, v_min, v_max, c_sim.hour)}_")
            if t_tp not in ["danger_red", "danger_blue"]: st.markdown(f"**🔮 Xu hướng dự báo:** {trnd}")


# Thiết lập các tab chức năng lớn ngoài vùng làm việc chính
tab_future, tab_past = st.tabs(["🔮 XEM DỰ BÁO & THEO DÕI TƯƠNG LAI", "📁 TẢI FILE & PHÂN TÍCH LỊCH SỬ"])

with tab_future:
    live_monitor()
    st.markdown("---")
    render_realtime_analytics_panel()

with tab_past:
    st.markdown("<h3 style='color:#1A5276;font-size:19px;'>📁 PHÂN TÍCH FILE IOT NHÀ KÍNH</h3>", unsafe_allow_html=True)
    tl, tr = st.columns(2)
    with tl:
        with st.container(border=True):
            st.markdown("<div class='upload-header'>🌿 1. CẤU HÌNH LOẠI CÂY TRỒNG VÀO FILE</div>", unsafe_allow_html=True)
            f_opt = st.selectbox("Chọn mô hình cây trồng áp dụng cho file:", plant_list_keys, index=st.session_state.file_plant_idx)
            st.session_state.file_plant_idx = plant_list_keys.index(f_opt)
            
            if f_opt == "🛠️ Tùy chỉnh thủ công ngưỡng riêng":
                st.session_state.file_custom_sang = st.slider("File - Sáng:", 0.0, 3.0, st.session_state.file_custom_sang, 0.1)
                st.session_state.file_custom_trua = st.slider("File - Trưa:", 0.0, 3.0, st.session_state.file_custom_trua, 0.1)
                st.session_state.file_custom_chieu = st.slider("File - Chiều:", 0.0, 3.0, st.session_state.file_custom_chieu, 0.1)
                st.session_state.file_custom_dem = st.slider("File - Đêm:", 0.0, 3.0, st.session_state.file_custom_dem, 0.1)
            else:
                f_tree = DANH_SACH_CAY[f_opt]
                st.markdown(f"🔹 Ngưỡng động áp dụng: **Sáng** `{f_tree['Sang']}` | **Trưa** `{f_tree['Trua']}` | **Chiều** `{f_tree['Chieu']}` | **Đêm** `{f_tree['Dem']}`")
    with tr:
        with st.container(border=True):
            st.markdown("<div class='upload-header'>📥 2. TẢI DỮ LIỆU ĐẦU VÀO CỦA TRẠM</div>", unsafe_allow_html=True)
            u_file = st.file_uploader("Kéo thả file IoT tại đây:", type=["json", "csv", "xlsx"], label_visibility="collapsed")
            t_filter = st.selectbox("📆 Chế độ lọc dữ liệu thời gian:", ["📊 Xem toàn bộ dữ liệu gốc", "📆 Tự chọn ngày cụ thể", "🗓️ Chọn 1 tháng (29 ngày)", "📅 Chọn 1 tuần (6 ngày)", "⏱️ 1 Ngày gần nhất (Gom 10p)", "📅 1 Tuần gần nhất (Gom ngày)", "🗓️ 1 Tháng gần nhất (Gom ngày)"])

    if u_file:
        try:
            if u_file.name.endswith('.json'):
                j_data = json.load(u_file)
                df_up = pd.DataFrame([j_data]) if isinstance(j_data, dict) and not isinstance(list(j_data.values())[0], (dict, list)) else pd.DataFrame(j_data)
            elif u_file.name.endswith('.csv'): 
                df_up = pd.read_csv(u_file)
            else: 
                df_up = pd.read_excel(u_file)
                
            c_t, c_h, c_time = None, None, None
            for c in df_up.columns:
                cl = str(c).lower().strip()
                if 'tempkk' in cl: c_t = c
                if 'humikk' in cl: c_h = c
                if any(k in cl for k in ['thời gian', 'time', 'gio', 'date', 'timestamp', 'created_at']): c_time = c

            if not c_t:
                for c in df_up.columns:
                    cl = str(c).lower().strip()
                    if any(k in cl for k in ['temp', 'nhiet', 't°', 'temperature']): c_t = c
            if not c_h:
                for c in df_up.columns:
                    cl = str(c).lower().strip()
                    if any(k in cl for k in ['rh', 'hum', 'do am', 'humidity']): c_h = c

            if not c_t and len(df_up.columns) > 0: c_t = df_up.columns[0]
            if not c_h and len(df_up.columns) > 1: c_h = df_up.columns[1]
            if not c_time and len(df_up.columns) > 2: c_time = df_up.columns[2]

            df_up[c_time] = pd.to_datetime(df_up[c_time].astype(str).str.replace('-', ':').str.strip(), errors='coerce')
            df_up[c_time] = df_up[c_time].fillna(datetime.now())

            df_rc = pd.DataFrame()
            df_rc["datetime_internal"] = df_up[c_time]
            df_rc["Nhiệt độ (°C)"] = pd.to_numeric(df_up[c_t], errors='coerce').apply(lambda x: x / 10.0 if pd.notna(x) and x >= 45.0 else x)
            df_rc["Độ ẩm (%)"] = pd.to_numeric(df_up[c_h], errors='coerce').apply(lambda x: x / 10.0 if pd.notna(x) and x > 100.0 else x)
            df_rc = df_rc[df_rc["Độ ẩm (%)"] > 1.0].dropna().sort_values("datetime_internal")

            if len(df_rc) > 0:
                df_rc["VPD_raw"] = df_rc.apply(lambda r: calculate_vpd(r["Nhiệt độ (°C)"], r["Độ ẩm (%)"]), axis=1)
                df_rc["only_date"] = df_rc["datetime_internal"].dt.date
                av_dates = sorted(df_rc["only_date"].unique())
                
                if "Tự chọn ngày cụ thể" in t_filter:
                    s_date = st.date_input("👇 Chọn ngày xem:", value=av_dates[-1] if av_dates else datetime.now().date())
                    df_rc = df_rc[df_rc["only_date"] == s_date]
                elif "29 ngày" in t_filter:
                    st_d = st.date_input("👇 Ngày bắt đầu chu kỳ:", value=av_dates[0] if av_dates else datetime.now().date())
                    df_rc = df_rc[(df_rc["only_date"] >= st_d) & (df_rc["only_date"] <= st_d + timedelta(days=29))]
                elif "6 ngày" in t_filter:
                    st_d = st.date_input("👇 Ngày bắt đầu tuần:", value=av_dates[0] if av_dates else datetime.now().date())
                    df_rc = df_rc[(df_rc["only_date"] >= st_d) & (df_rc["only_date"] <= st_d + timedelta(days=6))]
                elif "Xem toàn bộ dữ liệu gốc" in t_filter: 
                    pass
                else:
                    m_time = df_rc["datetime_internal"].max()
                    if "1 Ngày gần nhất" in t_filter: df_rc = df_rc[df_rc["datetime_internal"] >= (m_time - timedelta(days=1))]
                    elif "1 Tuần gần nhất" in t_filter: df_rc = df_rc[df_rc["datetime_internal"] >= (m_time - timedelta(days=7))]
                    elif "1 Tháng gần nhất" in t_filter: df_rc = df_rc[df_rc["datetime_internal"] >= (m_time - timedelta(days=30))]

            df_f_blk = df_rc.copy()

            if len(df_rc) > 0:
                u_days_f = df_rc["only_date"].nunique()
                df_rs = df_rc[["datetime_internal", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD_raw"]].copy().set_index("datetime_internal")
                
                if any(k in t_filter for k in ["1 Tuần gần nhất", "1 Tháng gần nhất", "ngày"]):
                    df_rs = df_rs.resample("1D").mean().dropna()
                elif "Xem toàn bộ dữ liệu gốc" in t_filter:
                    df_rs = df_rs.resample("1h" if u_days_f > 2 else "10min").mean().dropna()
                elif "1 Ngày gần nhất" in t_filter:
                    df_rs = df_rs.resample("10min").mean().dropna()
                
                df_rs["datetime_internal"] = df_rs.index
                fmt = "%d/%m %H:%M" if (any(k in t_filter for k in ["1 Tuần gần nhất", "1 Tháng gần nhất", "ngày"]) or ("Xem toàn bộ dữ liệu gốc" in t_filter and u_days_f > 2)) else "%H:%M"
                df_rs["Hiển thị Giờ"] = df_rs["datetime_internal"].dt.strftime(fmt)
                df_rs.reset_index(drop=True, inplace=True)
            else:
                u_days_f = 0
                df_rs = pd.DataFrame(columns=["datetime_internal", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD_raw", "Hiển thị Giờ"])

            if not df_rs.empty:
                df_p = pd.DataFrame()
                df_p["datetime_internal"] = df_rs["datetime_internal"]
                df_p["Nhiệt độ (°C)"] = df_rs["Nhiệt độ (°C)"].round(2)
                df_p["Độ ẩm (%)"] = df_rs["Độ ẩm (%)"].round(2)
                df_p["Hiển thị Giờ"] = df_rs["Hiển thị Giờ"]
                df_p["VPD (kPa)"] = df_rs["VPD_raw"].round(2) if u_days_f > 2 else df_rs.apply(lambda r: round(calculate_vpd(r["Nhiệt độ (°C)"], r["Độ ẩm (%)"]), 2), axis=1)
                df_p["Ngày"] = "Dữ liệu File"
                
                def check_file_status(row):
                    h = row["datetime_internal"].hour
                    v = row["VPD (kPa)"]
                    v_min, v_max = get_current_vpd_range(f_opt, h, is_file=True)
                    if v < v_min: return "⚠️ Quá ẩm"
                    elif v <= v_max: return "✅ Lý tưởng"
                    return "🚨 Quá khô"
                
                df_p["Trạng thái"] = df_p.apply(check_file_status, axis=1)
                
                st.markdown("<div style='margin-top:15px;margin-bottom:5px;font-weight:bold;color:#1A5276;'>📊 TỔNG QUAN CHU KỲ GỘP</div>", unsafe_allow_html=True)
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.markdown(f"<div class='metric-card-upload'><span>📈 VPD TB CHU KỲ</span><br><b style='font-size:18px;color:#2E7D32;'>{df_p['VPD (kPa)'].mean():.2f} kPa</b></div>", unsafe_allow_html=True)
                mc2.markdown(f"<div class='metric-card-upload'><span>🌡️ NHIỆT ĐỘ TB</span><br><b style='font-size:18px;color:#FF4B4B;'>{df_p['Nhiệt độ (°C)'].mean():.1f} °C</b></div>", unsafe_allow_html=True)
                mc3.markdown(f"<div class='metric-card-upload'><span>💧 ĐỘ ẨM TB</span><br><b style='font-size:18px;color:#0068C9;'>{df_p['Độ ẩm (%)'].mean():.1f} %</b></div>", unsafe_allow_html=True)
                mc4.markdown(f"<div class='metric-card-upload'><span>📋 SỐ ĐIỂM DỮ LIỆU</span><br><b style='font-size:18px;color:#5D6D7E;'>{len(df_p)} điểm</b></div>", unsafe_allow_html=True)

                f_min_avg = df_p["datetime_internal"].dt.hour.apply(lambda h: get_current_vpd_range(f_opt, h, is_file=True)[0]).mean()
                f_max_avg = df_p["datetime_internal"].dt.hour.apply(lambda h: get_current_vpd_range(f_opt, h, is_file=True)[1]).mean()
                str_res = calculate_plant_stress_hours(df_p, f_min_avg, f_max_avg, t_filter)
                
                st.markdown("<div style='margin-top:10px;font-weight:bold;color:#B71C1C;'>⚠️ ĐÁNH GIÁ CHUYÊN SÂU ÁP LỰC CÂY TRỒNG</div>", unsafe_allow_html=True)
                sc_l, sc_r = st.columns(2)
                if str_res["dry_hours"] > 2.0: sc_l.error(f"🚨 **Stress Khô Nóng:** Bị đóng khí khổng suốt **{str_res['dry_hours']} giờ**.")
                else: sc_l.success(f"✅ **Áp lực khô:** An toàn ({str_res['dry_hours']} giờ).")
                if str_res["wet_hours"] > 4.0: sc_r.warning(f"🟦 **Stress Ẩm:** Tích tụ ẩm cao liên tục **{str_res['wet_hours']} giờ**.")
                else: sc_r.success(f"✅ **Áp lực ẩm:** An toàn ({str_res['wet_hours']} giờ).")

                rl, rr = st.columns([6.5, 3.5])
                with rl:
                    st.markdown("#### 📊 BIỂU ĐỒ CHU KỲ PHÂN TẦNG")
                    st.markdown("##### 🎯 Chỉ số VPD (kPa)")
                    st.altair_chart(draw_vpd_chart(df_p, f_min_avg, f_max_avg), use_container_width=True)
                    
                    st.markdown("##### 🌡️💧 Biến thiên Nhiệt độ & Độ ẩm")
                    st.altair_chart(draw_temp_humidity_combo_chart(df_p), use_container_width=True)

                with rr:
                    st.markdown("##### 📋 NHẬT KÝ THEO DÕI ĐIỂM GỘP CHU KỲ")
                    df_tc = df_p[["Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].copy()
                    for c in ["Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)"]: df_tc[c] = df_tc[c].apply(lambda x: f"{float(x):.2f}")
                    st.dataframe(df_tc.style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True, height=290)
                    st.download_button("📥 Xuất báo cáo chu kỳ (.csv)", data=df_p.to_csv(index=False).encode('utf-8'), file_name="vpd_report.csv", mime="text/csv", use_container_width=True)

                st.markdown("---")
                st.markdown("##### 📊 BÁO CÁO PHÂN TÍCH TỔNG HỢP THEO BUỔI CHU KỲ")
                if len(df_f_blk) > 0:
                    df_f_blk["Hour"] = df_f_blk["datetime_internal"].dt.hour
                    
                    def b_assign(h):
                        hs = st.session_state.h_sang
                        ht = st.session_state.h_trua
                        hc = st.session_state.h_chieu
                        hd = st.session_state.h_dem
                        if hs <= h < ht: return "🌅 Sáng"
                        if ht <= h < hc: return "☀️ Trưa"
                        if hc <= h < hd: return "🌇 Chiều"
                        return "🌙 Đêm/Khuya"
                        
                    df_f_blk["Buổi"] = df_f_blk["Hour"].apply(b_assign)
                    b_sum = df_f_blk.groupby("Buổi").agg({"Nhiệt độ (°C)": "mean", "Độ ẩm (%)": "mean", "VPD_raw": "mean"}).reindex(["🌅 Sáng", "☀️ Trưa", "🌇 Chiều", "🌙 Đêm/Khuya"]).dropna(how="all").reset_index()
                    b_sum.columns = ["Khoảng thời gian", "Nhiệt độ TB (°C)", "Độ ẩm TB (%)", "VPD TB (kPa)"]
                    for c in ["Nhiệt độ TB (°C)", "Độ ẩm TB (%)", "VPD TB (kPa)"]: b_sum[c] = b_sum[c].round(2)
                    
                    def evaluate_block_row(row):
                        name = row["Khoảng thời gian"]
                        vpd = row["VPD TB (kPa)"]
                        rep_hour = st.session_state.h_sang if "Sáng" in name else (st.session_state.h_trua if "Trưa" in name else (st.session_state.h_chieu if "Chiều" in name else st.session_state.h_dem))
                        v_min, v_max = get_current_vpd_range(f_opt, rep_hour, is_file=True)
                        if vpd < v_min: return "🟦 Quá ẩm"
                        elif vpd <= v_max: return "🟩 Lý tưởng"
                        return "🟥 Quá khô"
                        
                    b_sum["Đánh giá"] = b_sum.apply(evaluate_block_row, axis=1)
                    st.dataframe(b_sum, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ Không có dữ liệu hợp lệ trong file tải lên.")
        except Exception as file_err:
            st.error(f"❌ Lỗi xử lý hoặc sai cấu trúc file: {str(file_err)}")
