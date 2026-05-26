import streamlit as st
import pandas as pd
import json
import os
import threading
import time
from datetime import datetime, timedelta
import requests

from calculations import calculate_vpd
from analytics import (
    analyze_day_by_blocks_rt, 
    predict_vpd_trend_v3, 
    get_biological_block
)
from charts import draw_vpd_chart, draw_combined_temp_humidity_chart

TELE_TOKEN = "8917951413:AAE6LKUEfYEYiQrFWGoKsQn0tumZc_XbcHg"
TELE_CHAT_ID = "7290661009"

# File cục bộ lưu trạng thái liên lạc để khóa bước phản hồi giữa Telegram và Streamlit
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
    
    .big-vpd-box { background-color: #F8F9F9; border: 2px solid #2ECC71; border-radius: 8px; padding: 18px; text-align: center; margin-bottom: 10px; }
    .big-vpd-title { font-size: 14px; color: #7F8C8D; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    .big-vpd-value { font-size: 45px; color: #27AE60; font-weight: 900; line-height: 1.0; margin-top: 5px; margin-bottom: 5px; }
    .big-env-value { font-size: 20px; color: #2C3E50; font-weight: bold; margin-bottom: 12px; }
    
    .analysis-merge-box { background-color: #EAECEE; color: #2C3E50; padding: 12px 15px; border-radius: 6px; font-size: 13.5px; font-weight: 500; text-align: left; border-left: 5px solid #27AE60; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

# Khởi tạo trạng thái file điều khiển nếu chưa tồn tại
if not os.path.exists(CONTROL_FILE):
    with open(CONTROL_FILE, 'w') as f:
        json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "Hệ thống vận hành tự động nền"}, f)

# --- Khởi tạo dữ liệu Session State hệ thống thực tế ---
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 

# Lưu trữ lượng biến đổi thực tế mà phần cứng tác động vào môi trường nhà kính (offset)
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


# =========================================================================
# 🤖 BOT TELEGRAM LẮNG NGHE SỰ KIỆN CLICK PHẢN HỒI REALTIME TỪ XA
# =========================================================================
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
                                json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "⚠️ Người dùng hủy bỏ qua. Trạm chạy theo cảm biến tự nhiên."}, f)
                        else:
                            with open(CONTROL_FILE, 'w') as f:
                                json.dump({
                                    "status": "triggered", "action": data, "step_num": 0, 
                                    "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, 
                                    "msg": "⚡ Đã ghi nhận lệnh từ Telegram! Đang tính toán công suất điều tiết chia bước..."
                                }, f)
                        
                        # Phản hồi lại telegram là đã nhận lệnh thành công
                        requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", json={
                            "callback_query_id": query_id, "text": "Đang thực thi giải pháp phần cứng!"
                        })
        except Exception:
            pass
        time.sleep(1)

# Chạy Bot Telegram ngầm bằng Luồng độc lập (Chỉ chạy một lần duy nhất)
if "bot_thread_started" not in st.session_state:
    st.session_state.bot_thread_started = True
    threading.Thread(target=run_telegram_bot, daemon=True).start()


def send_telegram_with_buttons(token, chat_id, text, buttons):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": buttons}}
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


# =========================================================================
# 🔄 THUẬT TOÁN ĐIỀU TIẾT CHIA BƯỚC THỜI GIAN THỰC (REALTIME SENSOR CYCLE)
# =========================================================================
def process_sensor_cycle(sensor_temp, sensor_rh, plant_matrix):
    now_dt = datetime.now()
    current_date_str = now_dt.strftime("Ngày %d/%m")
    current_hour = now_dt.hour
    
    try:
        with open(CONTROL_FILE, 'r') as f:
            cmd_state = json.load(f)
            
        # 🟩 CHU KỲ T+00: Người quản trị click nút từ xa -> Tính toán lượng Delta cần bù thực tế
        if cmd_state["status"] == "triggered":
            buoi_hien_tai = get_biological_block(current_hour)
            v_min, v_max = plant_matrix[buoi_hien_tai]
            target_vpd_center = (v_min + v_max) / 2.0
            
            best_t_delta = 0.0
            best_h_delta = 0.0
            min_error = 999.0
            
            # Quét dải tìm mức bù tối ưu
            if cmd_state["action"] in ["fix_hot_temp", "fix_wet_temp"]: 
                for t_d in [x * 0.1 for x in range(-200, 200)]:
                    test_vpd = calculate_vpd(sensor_temp + t_d, sensor_rh)
                    if abs(test_vpd - target_vpd_center) < min_error:
                        min_error = abs(test_vpd - target_vpd_center)
                        best_t_delta = t_d
            else: 
                for h_d in [x * 0.5 for x in range(-200, 200)]:
                    test_vpd = calculate_vpd(sensor_temp, max(0.0, min(100.0, sensor_rh + h_d)))
                    if abs(test_vpd - target_vpd_center) < min_error:
                        min_error = abs(test_vpd - target_vpd_center)
                        best_h_delta = h_d
                        
            cmd_state["status"] = "processing"
            cmd_state["step_num"] = 1
            cmd_state["needed_temp_delta"] = best_t_delta
            cmd_state["needed_rh_delta"] = best_h_delta
            cmd_state["msg"] = f"⚙️ Đang xử lý bước 1 (10 phút): Thiết bị đáp ứng 50% hiệu suất..."
            
            st.session_state.temp_offset = best_t_delta / 2.0
            st.session_state.rh_offset = best_h_delta / 2.0
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
                
        # 🟨 CHU KỲ T+10: Hết chu kỳ đầu tiên -> Đẩy 100% công suất để ép lọt dải mục tiêu
        elif cmd_state["status"] == "processing" and cmd_state["step_num"] == 1:
            cmd_state["step_num"] = 2
            cmd_state["msg"] = f"⚙️ Đang xử lý bước 2 (20 phút): Đẩy 100% công suất phần cứng, ép lọt dải Lý Tưởng!"
            
            st.session_state.temp_offset = cmd_state["needed_temp_delta"]
            st.session_state.rh_offset = cmd_state["needed_rh_delta"]
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
                
        # 🟦 CHU KỲ T+20: Hoàn thành can thiệp -> Tắt thiết bị, nhả về tự động nền ổn định
        elif cmd_state["status"] == "processing" and cmd_state["step_num"] == 2:
            cmd_state["status"] = "idle"
            cmd_state["action"] = "none"
            cmd_state["step_num"] = 0
            cmd_state["needed_temp_delta"] = 0.0
            cmd_state["needed_rh_delta"] = 0.0
            cmd_state["msg"] = "✨ Can thiệp hoàn thành: Môi trường cảm biến đã lọt chuẩn dải Lý Tưởng!"
            
            st.session_state.temp_offset = 0.0
            st.session_state.rh_offset = 0.0
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
    except Exception:
        pass

    # Áp dụng lượng thay đổi của phần cứng lên môi trường không khí của trạm
    final_temp = round(sensor_temp + st.session_state.temp_offset, 2)
    final_rh = round(max(0.0, min(100.0, sensor_rh + st.session_state.rh_offset)), 2)
    
    st.session_state.countdown = 15 
    st.session_state.stt_counter += 1
    new_vpd = calculate_vpd(final_temp, final_rh)
    
    buoi_hien_tai = get_biological_block(current_hour)
    v_min, v_max = plant_matrix[buoi_hien_tai]
    
    if new_vpd >= v_max + 0.5: status_text = "🔴 Quá Nóng"
    elif new_vpd > v_max: status_text = "💛 Nóng"
    elif new_vpd < v_min - 0.2: status_text = "🔵 Quá Ẩm"
    elif new_vpd < v_min: status_text = "🌐 Ẩm"
    else: status_text = "🟩 Lý Tưởng"
    
    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": current_date_str,
        "Thời gian mô phỏng": now_dt, "Hiển thị Giờ": now_dt.strftime("%H:%M"),
        "datetime_internal": now_dt, "Nhiệt độ (°C)": final_temp, "Độ ẩm (%)": final_rh,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text
    })

    # --- CƠ CHẾ KHÓA CHỐNG SPAM TELEGRAM: CHỈ BÁO ĐỘNG KHI HỆ THỐNG ĐANG RẢNH (IDLE) ---
    if TELE_TOKEN and TELE_CHAT_ID:
        try:
            with open(CONTROL_FILE, 'r') as f: current_status = json.load(f)["status"]
        except Exception: current_status = "idle"
            
        if current_status == "idle" and status_text != "🟩 Lý Tưởng":
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            trend, _ = predict_vpd_trend_v3(h_latest, current_hour, plant_matrix)
            clean_trend = trend.replace("Xu hướng:", "").strip()
            
            title_block = "⚠️ PHÁT HIỆN BIẾN ĐỘNG"
            reason_text = "Môi trường mất cân bằng dải ổn định."
            tele_buttons = []
            
            # Phân tách nút bấm thông minh dựa vào ngữ cảnh buổi sinh học thực tế
            if "🌅 Sáng" in buoi_hien_tai:
                title_block = "🌅 [CẢNH BÁO VPD SÁNG SỚM - LẠNH ẨM ĐỌNG SƯƠNG]"
                reason_text = "Không khí sáng sớm bão hòa hơi nước, nhiệt độ thấp kìm hãm mạch dẫn rễ cây tích lũy nấm bệnh."
                tele_buttons = [[{"text": "🔥 Đóng Rèm Hông & Bật Đèn Nhiệt Giữ Ấm", "callback_data": "fix_wet_temp"}]]
            elif "☀️ Trưa" in buoi_hien_tai:
                title_block = "☀️ [CẢNH BÁO VPD GIỮA TRƯA - BỨC XẠ NÓNG GẮT]"
                reason_text = "Hiệu ứng lồng kính hấp thụ bức xạ đỉnh điểm, nhiệt độ vọt cao làm cây đóng khí khổng tự vệ."
                tele_buttons = [[{"text": "💨 Kéo Lưới Chặn Nắng + Mở Thông Gió Đỉnh", "callback_data": "fix_hot_temp"}]]
            elif "🌇 Chiều" in buoi_hien_tai:
                title_block = "🌇 [CẢNH BÁO VPD CHIỀU TA - HANH KHÔ SỤT ẨM]"
                reason_text = "Gió hanh cuối ngày cuốn trôi hơi ẩm bề mặt lá, nguy cơ cháy rìa tế bào đỉnh sinh trưởng."
                tele_buttons = [[{"text": "💦 Bật Phun Sương Hạt Mịn Bù Ẩm Ngắt Quãng", "callback_data": "fix_hot_rh"}]]
            elif "🌌 Tối" in buoi_hien_tai:
                title_block = "🌌 [CẢNH BÁO VPD ĐẦU ĐÊM - ẨM TÍCH TỤ ĐỌNG NƯỚC]"
                reason_text = "Ẩm tích tụ cục bộ trong tán cây sau tưới muộn, thiếu lưu thông khí tạo ổ bào tử nấm."
                tele_buttons = [[{"text": "🌪️ Bật Quạt Đối Lưu Tán + Ép Quạt Hút Xả Ẩm", "callback_data": "fix_wet_rh"}]]
            elif "🌙 Khuya" in buoi_hien_tai:
                title_block = "🌙 [CẢNH BÁO VPD ĐÊM KHUYA - SUY GIẢM NHIỆT ĐỘ]"
                reason_text = "Nhiệt độ ban đêm sụt sâu dưới ngưỡng sinh học tối thiểu, cần sưởi nhẹ giữ ấm gốc rễ."
                tele_buttons = [[{"text": "🔥 Bật Hệ Thống Đèn Sưởi Hồng Ngoại Nền", "callback_data": "fix_wet_temp"}]]

            msg = (f"🌿 *{title_block}*\n"
                   f"⏰ Thời gian phát hiện: *{now_dt.strftime('%H:%M:%S')}*\n"
                   f"📊 Thông số cảm biến: {sensor_temp}°C | {sensor_rh}%\n"
                   f"📈 *VPD Hiện Tại:* *{new_vpd:.2f} kPa* (Ngưỡng tối ưu buổi: {v_min}-{v_max})\n"
                   f"📢 *Hiện trạng:* *{status_text}*\n"
                   f"🔍 *Nguyên nhân:* _{reason_text}_\n"
                   f"🔮 *Dự báo:* _{clean_trend}_\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"📲 *Lựa chọn lệnh phản hồi điều khiển thiết bị từ xa:*")
            
            tele_buttons.append([{"text": "⏸️ Bỏ qua (Chạy trôi tự nhiên)", "callback_data": "none"}])
            send_telegram_with_buttons(TELE_TOKEN, TELE_CHAT_ID, msg, tele_buttons)
            
    return final_temp, final_rh


# ==========================================
# 🧭 CẤU TRÚC ĐIỀU HƯỚNG TAG MENU Ở SIDEBAR
# ==========================================
st.sidebar.markdown("## 🧭 MENU CHỨC NĂNG")
app_mode = st.sidebar.selectbox(
    "Chọn Tag công việc cần thực hiện:",
    ["🌿 VPD Realtime & Cảm Biến Real", "📥 Phân Tích File IoT JSON"]
)
st.sidebar.markdown("---")
st.sidebar.info("🎯 **Hệ thống giám sát VPD Pro**\nĐiều khiển nhà kính nông nghiệp công nghệ cao tối ưu sinh học.")


# ==========================================
# TAG 1: VPD REALTIME & CẢM BIẾN REAL THỰC ĐỊA
# ==========================================
if app_mode == "🌿 VPD Realtime & Cảm Biến Real":
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 HỆ THỐNG GIÁM SÁT VPD REALTIME & ĐIỀU KHIỂN CHIA BƯỚC THỰC ĐỊA</h2>", unsafe_allow_html=True)
    
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

        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>🔌 CẤU HÌNH ĐẦU VÀO CẢM BIẾN REALTIME</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            input_temp = st.number_input("🌡️ Nhiệt độ đọc từ Cảm biến thực (°C):", min_value=0.0, max_value=60.0, value=25.0, step=0.1)
            input_rh = st.number_input("💧 Độ ẩm đọc từ Cảm biến thực (%):", min_value=0.0, max_value=100.0, value=85.0, step=0.5)

        with st.container(border=True):
            c_b1, c_b2 = st.columns(2)
            with c_b1:
                if st.button("▶️ Khởi chạy trạm", type="primary", use_container_width=True):
                    st.session_state.is_running = True
                    st.rerun()
            with c_b2:
                if st.button("⏸️ Tạm dừng trạm", type="secondary", use_container_width=True):
                    st.session_state.is_running = False
                    st.rerun()
            
            if st.button("🔄 Reset nhật ký trạm", type="secondary", use_container_width=True):
                st.session_state.history = []; st.session_state.stt_counter = 0; st.session_state.countdown = 15
                st.session_state.is_running = False
                st.session_state.temp_offset = 0.0; st.session_state.rh_offset = 0.0
                with open(CONTROL_FILE, 'w') as f: 
                    json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "Đã reset hoàn toàn trạm về tự động nền"}, f)
                st.rerun()

        run_interval = 1 if st.session_state.is_running else 999999
        @st.fragment(run_every=run_interval)
        def live_monitor_panel():
            if st.session_state.is_running:
                st.session_state.countdown -= 1
                if st.session_state.countdown < 0: 
                    process_sensor_cycle(input_temp, input_rh, st.session_state.current_matrix)
                    st.rerun()
            
            now_time = datetime.now()
            buoi_hien_tai = get_biological_block(now_time.hour)
            v_min, v_max = st.session_state.current_matrix[buoi_hien_tai]
            
            # Tính chỉ số môi trường sau khi đã áp dụng offset điều khiển thiết bị phần cứng thực tế
            disp_temp = round(input_temp + st.session_state.temp_offset, 2)
            disp_rh = round(max(0.0, min(100.0, input_rh + st.session_state.rh_offset)), 2)
            v_calc = calculate_vpd(disp_temp, disp_rh)
            
            if v_calc >= v_max + 0.5: stt = "🔴 Quá Nóng"
            elif v_calc > v_max: stt = "💛 Nóng"
            elif v_calc < v_min - 0.2: stt = "🔵 Quá Ẩm"
            elif v_calc < v_min: stt = "🌐 Ẩm"
            else: stt = "🟩 Lý Tưởng"
            
            try:
                with open(CONTROL_FILE, 'r') as f: current_action_msg = json.load(f)["msg"]
            except Exception: current_action_msg = "Ổn định."

            with st.container(border=True):
                st.markdown(f"⏰ **Giờ hệ thống thực thực địa:** `<span style='color:#C0392B; font-weight:bold; font-size:16px;'>{now_time.strftime('%H:%M:%S')}</span>`", unsafe_allow_html=True)
                st.caption(f"⏳ Quét cảm biến kế: {st.session_state.countdown}s | Bù Nhiệt: {st.session_state.temp_offset:+}°C | Bù Ẩm: {st.session_state.rh_offset:+}%")
                st.warning(f"🤖 **Trạng thái phần cứng từ xa:** {current_action_msg}")
                st.markdown(f"""
                <div class="big-vpd-box">
                    <div class="big-vpd-title">🌿 CHỈ SỐ VPD THỜI THỰC TRÊN LÁ</div>
                    <div class="big-vpd-value">{v_calc:.2f} kPa</div>
                    <div class="big-env-value">🌡️ {disp_temp}°C  &nbsp;|&nbsp;  💧 {disp_rh}%</div>
                    <div class="analysis-merge-box">
                        📌 <b>Hiện trạng dải:</b> {stt}<br>
                        🔍 <b>Giai đoạn sinh học:</b> {buoi_hien_tai} (Dải đích tối ưu: {v_min} - {v_max} kPa)
                    </div>
                </div>
                """, unsafe_allow_html=True)
        live_monitor_panel()

        if st.session_state.history:
            st.markdown("### 🛠️ KHUYẾN NGHỊ ĐIỀU KHIỂN PHẦN CỨNG LẬP TỨC")
            cur_v = st.session_state.history[0]["VPD (kPa)"]
            now_time = datetime.now()
            b_hien_tai = get_biological_block(now_time.hour)
            v_min, v_max = st.session_state.current_matrix[b_hien_tai]
            
            if cur_v >= v_max + 0.5:
                st.markdown("<div class='danger-box-red'>🚨 QUÁ NÓNG: Bật phun sương hạt mịn full công suất + Mở rèm đỉnh đón gió giải nhiệt!</div>", unsafe_allow_html=True)
            elif cur_v > v_max:
                if (v_max + 0.5) - cur_v <= 0.1:
                    st.markdown(f"<div class='danger-box-red'>⚠️ SẮP QUÁ NÓNG (Cách ranh giới biến cố {((v_max+0.5)-cur_v):.2f} kPa): Kích hoạt khẩn cấp rèm chắn nắng!</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='danger-box-yellow'>💛 NÓNG: Kéo lưới cắt nắng, bật phun sương ngắt quãng giảm nhiệt.</div>", unsafe_allow_html=True)
            elif cur_v < v_min - 0.2:
                st.markdown("<div class='danger-box-darkblue'>🔵 QUÁ ẨM: Bật quạt đối lưu tán cây, khép ngay hệ thống tưới nhỏ giọt!</div>", unsafe_allow_html=True)
            elif cur_v < v_min:
                if cur_v - (v_min - 0.2) <= 0.1:
                    st.markdown(f"<div class='danger-box-darkblue'>⚠️ SẮP QUÁ ẨM (Cách ranh giới đọng sương {(cur_v-(v_min-0.2)):.2f} kPa): Bật toàn bộ quạt hút cưỡng bức xả ẩm!</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='danger-box-lightblue'>🌐 Ẩm: Hé bèm hông tăng lưu thông không khí tự nhiên tự hủy ẩm.</div>", unsafe_allow_html=True)
            else:
                st.success("🟩 LÝ TƯỞNG: Môi trường hoàn hảo cho cây quang hợp. Duy trì trạng thái ổn định.")

    with right_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📊 LỊCH SỬ BIẾN ĐỘNG CHU KỲ REALTIME THỜI THỰC</h3>", unsafe_allow_html=True)
        if not st.session_state.history:
            st.info("Trạm đang lắng nghe và tích lũy dòng dữ liệu từ cảm biến thực địa.")
        else:
            df_all = pd.DataFrame(st.session_state.history)
            df_f = df_all.iloc[::-1].copy()
            now_time = datetime.now()
            v_min_chart, v_max_chart = st.session_state.current_matrix[get_biological_block(now_time.hour)]
            
            st.markdown("**🎨 Khối nền đồ thị tầng:** 🔵 *Dưới ngưỡng (Quá Ẩm)* | 🟢 *Dải lý tưởng (Tối ưu)* | 🔴 *Trên ngưỡng (Quá Nóng)*")
            st.altair_chart(draw_vpd_chart(df_f, v_min_chart, v_max_chart), use_container_width=True)
            st.altair_chart(draw_combined_temp_humidity_chart(df_f), use_container_width=True)
                
            st.markdown("##### 📋 NHẬT KÝ CHI TIẾT CÁC CHU KỲ QUÉT QUAN TRẮC THỰC TẾ")
            st.dataframe(
                df_f[["STT", "Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), 
                use_container_width=True, 
                hide_index=True
            )


# ==========================================
# TAG 2: PHÂN TÍCH FILE IOT JSON (FIXED LOGIC TRÁO CỘT)
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
                    list_key = None
                    for k, v in json_data.items():
                        if isinstance(v, list):
                            list_key = k
                            break
                    df_upload = pd.DataFrame(json_data[list_key]) if list_key else pd.DataFrame([json_data])
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
                st.error("❌ Không tìm thấy cột dữ liệu cảm biến nhiệt độ hoặc độ ẩm trong file.")
                st.stop()

            df_clean_raw = df_upload[[col_time, col_temp_raw, col_rh_raw]].dropna().copy()
            df_clean_raw[col_temp_raw] = pd.to_numeric(df_clean_raw[col_temp_raw], errors='coerce')
            df_clean_raw[col_rh_raw] = pd.to_numeric(df_clean_raw[col_rh_raw], errors='coerce')
            df_clean_raw = df_clean_raw.dropna()

            # 🔥 SỬA LẠI ĐÚNG LOGIC BỊ SAI Ở CŨ: Nhiệt độ khớp Nhiệt độ, Độ ẩm khớp Độ ẩm
            df_clean = pd.DataFrame()
            df_clean[col_time] = df_clean_raw[col_time]
            df_clean["temp_fixed"] = df_clean_raw[col_temp_raw]  # Trả lại đúng vị trí cột Nhiệt độ
            df_clean["rh_fixed"] = df_clean_raw[col_rh_raw]     # Trả lại đúng vị trí cột Độ ẩm

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
            
            resample_rule = "10min"
            date_format_rule = "%H:%M"
            
            if "Chọn một ngày cụ thể" in time_filter_option:
                selected_date = st.date_input("👇 Chọn ngày xem chi tiết trên lịch:", value=available_dates[0] if available_dates else datetime.now().date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date())
                df_filtered = df_clean[df_clean["only_date"] == selected_date].copy()
                resample_rule = "10min"
                date_format_rule = "%H:%M"
                
            elif "Xem theo Tuần" in time_filter_option:
                start_date = st.date_input("Ngày xuất phát (Hệ thống lấy tiếp 7 ngày):", value=min_dt_in_file.date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date(), key="week_start_picker")
                end_date = start_date + timedelta(days=7) 
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < end_date)].copy()
                resample_rule = "1D"
                date_format_rule = "%d/%m"

            elif "Xem theo Tháng" in time_filter_option:
                start_date = st.date_input("Ngày xuất phát (Hệ thống lấy tiếp 30 ngày):", value=min_dt_in_file.date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date(), key="month_start_picker")
                end_date = start_date + timedelta(days=30) 
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < end_date)].copy()
                resample_rule = "1D"
                date_format_rule = "%d/%m"

            elif "Xem theo Năm" in time_filter_option:
                start_date = st.date_input("Ngày xuất phát (Hệ thống lấy tiếp 365 ngày):", value=min_dt_in_file.date(), min_value=min_dt_in_file.date(), max_value=max_dt_in_file.date(), key="year_start_picker")
                end_date = start_date + timedelta(days=365) 
                df_filtered = df_clean[(df_clean["only_date"] >= start_date) & (df_clean["only_date"] < end_date)].copy()
                resample_rule = "1ME"
                date_format_rule = "%m/%Y"
            
            else: 
                df_filtered = df_clean.copy()
                if len(available_dates) <= 1:
                    resample_rule = "10min"
                    date_format_rule = "%H:%M"
                else:
                    resample_rule = "1D"
                    date_format_rule = "%d/%m"

            if df_filtered.empty:
                st.markdown("<div style='padding: 20px; background-color: #FDEDEC; border-left: 6px solid #C0392B; color: #922B21; border-radius: 4px; margin-top: 15px;'>🛑 KHÔNG CÓ BẢN GHI DỮ LIỆU TRONG KHOẢNG THỜI GIAN ĐÃ CHỌN</div>", unsafe_allow_html=True)
                st.stop()

            df_resample_input = df_filtered[["datetime_internal", "temp_fixed", "rh_fixed", "VPD_raw"]].copy()
            df_resample_input.set_index("datetime_internal", inplace=True)
            
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
                v = r["VPD (kPa)"]
                if v >= f_max + 0.5: file_status_list.append("🔴 Quá Nóng")
                elif v > f_max: file_status_list.append("💛 Nóng")
                elif v < f_min - 0.2: file_status_list.append("🔵 Quá Ẩm")
                elif v < f_min: file_status_list.append("🌐 Ẩm")
                else: file_status_list.append("🟩 Lý Tưởng")
            df_processed["Trạng thái"] = file_status_list

            st.markdown("### 📊 ĐỒ THỊ BIẾN ĐỘNG DỮ LIỆU TỔNG HỢP TỪ TỆP TIN")
            now_time = datetime.now()
            v_min_f, v_max_f = st.session_state.file_matrix[get_biological_block(now_time.hour)]
            
            st.altair_chart(draw_vpd_chart(df_processed, v_min_f, v_max_f), use_container_width=True)
            st.altair_chart(draw_combined_temp_humidity_chart(df_processed), use_container_width=True)
                
            st.markdown("##### 📋 BẢNG NHẬT KÝ CHI TIẾT TỪNG ĐIỂM DỮ LIỆU LOG FILE")
            st.dataframe(
                df_processed[["Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), 
                use_container_width=True, 
                hide_index=True
            )
        except Exception as e:
            st.error(f"❌ Xảy ra lỗi phân tích định dạng file: {str(e)}")
