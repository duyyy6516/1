import streamlit as st
import pandas as pd
import json
import os
import threading
import time
from datetime import datetime, timedelta
import requests

# Giả định các hàm bổ trợ từ các module cấu trúc của bạn
# Nếu bạn để chung một file, hãy thay thế bằng các hàm tương ứng
try:
    from calculations import calculate_vpd, get_weather_by_time
    from analytics import predict_vpd_trend_v3, get_biological_block
    from charts import draw_vpd_chart, draw_combined_temp_humidity_chart
except ImportError:
    # Các hàm dự phòng (fallback) nếu chạy độc lập một file
    def calculate_vpd(temp, rh):
        # Công thức tính VPD cơ bản
        import math
        es = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
        ea = es * (rh / 100.0)
        return round(es - ea, 2)

    def get_weather_by_time(dt):
        # Hàm mô phỏng thời tiết nền tự nhiên theo giờ để thử nghiệm
        hour = dt.hour
        if 5 <= hour < 10: return 18.0, 92.0   # Sáng sớm: Lạnh ẩm
        elif 10 <= hour < 15: return 31.0, 40.0 # Giữa trưa: Khô nóng
        elif 15 <= hour < 19: return 26.0, 45.0 # Chiều tà: Hanh khô
        elif 19 <= hour < 23: return 20.0, 88.0 # Đầu đêm: Ẩm tích tụ
        else: return 14.0, 95.0                 # Đêm khuya: Lạnh buốt
        
    def get_biological_block(hour):
        if 5 <= hour < 10: return "🌅 Sáng (05h-10h)"
        elif 10 <= hour < 15: return "☀️ Trưa (10h-15h)"
        elif 15 <= hour < 19: return "🌇 Chiều (15h-19h)"
        elif 19 <= hour < 23: return "🌌 Tối (19h-23h)"
        else: return "🌙 Khuya (23h-05h)"

    def predict_vpd_trend_v3(history, hour, matrix):
        return "Xu hướng: Biến động tự nhiên", None
    
    def draw_vpd_chart(df, vmin, vmax): return None
    def draw_combined_temp_humidity_chart(df): return None

# Config Telegram (Vui lòng thay bằng Token và ID thực tế của bạn nếu cần)
TELE_TOKEN = "8917951413:AAE6LKUEfYEYiQrFWGoKsQn0tumZc_XbcHg"
TELE_CHAT_ID = "7290661009"

# File lưu trạng thái liên lạc và khóa bước điều khiển giữa Tele và Streamlit
CONTROL_FILE = "control_state.json"

st.set_page_config(page_title="VPD Smart Farm Monitor Pro", page_icon="🌿", layout="wide")

# --- CSS Giao diện Chuyên nghiệp ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow-y: auto !important; scroll-behavior: smooth; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 1.5rem; padding-right: 1.5rem; }
    
    .big-vpd-box { background-color: #F8F9F9; border: 2px solid #2ECC71; border-radius: 8px; padding: 18px; text-align: center; margin-bottom: 10px; }
    .big-vpd-title { font-size: 14px; color: #7F8C8D; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    .big-vpd-value { font-size: 45px; color: #27AE60; font-weight: 900; line-height: 1.0; margin-top: 5px; margin-bottom: 5px; }
    .big-env-value { font-size: 20px; color: #2C3E50; font-weight: bold; margin-bottom: 12px; }
    
    .analysis-merge-box { background-color: #EAECEE; color: #2C3E50; padding: 12px 15px; border-radius: 6px; font-size: 13.5px; font-weight: 500; text-align: left; border-left: 5px solid #27AE60; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

# Khởi tạo file cấu hình điều khiển hệ thống gốc
if not os.path.exists(CONTROL_FILE):
    with open(CONTROL_FILE, 'w') as f:
        json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "Hệ thống vận hành tự động nền"}, f)

# Khởi tạo toàn bộ các biến State trong phiên làm việc Streamlit
if 'temp' not in st.session_state: st.session_state.temp = 0.0
if 'rh' not in st.session_state: st.session_state.rh = 0.0
if 'countdown' not in st.session_state: st.session_state.countdown = 15 
if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'is_completed' not in st.session_state: st.session_state.is_completed = False 
if 'history' not in st.session_state: st.session_state.history = []
if 'stt_counter' not in st.session_state: st.session_state.stt_counter = 0 
if 'simulated_time' not in st.session_state: st.session_state.simulated_time = "2026-05-24 07:00:00"

# Biến tích lũy độ lệch (offset) thực tế do tác động của phần cứng qua các bước chu kỳ
if 'temp_offset' not in st.session_state: st.session_state.temp_offset = 0.0
if 'rh_offset' not in st.session_state: st.session_state.rh_offset = 0.0

# Ma trận ngưỡng tối ưu cho Dâu Tây Đà Lạt theo thời gian sinh học trong ngày
PLANT_PRESETS = {
    "🍓 Dâu tây Đà Lạt (Giai đoạn trái)": {
        "🌅 Sáng (05h-10h)": (0.5, 0.9), "☀️ Trưa (10h-15h)": (0.7, 1.2), 
        "🌇 Chiều (15h-19h)": (0.6, 1.0), "🌌 Tối (19h-23h)": (0.4, 0.8), "🌙 Khuya (23h-05h)": (0.3, 0.7)
    }
}
if 'current_matrix' not in st.session_state:
    st.session_state.current_matrix = PLANT_PRESETS["🍓 Dâu tây Đà Lạt (Giai đoạn trái)"].copy()


# =========================================================================
# 🤖 LUỒNG CHẠY NGẦM (BACKGROUND THREAD) HỨNG LỆNH CLICK NÚT TELEGRAM 2 CHIỀU
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
                                json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "⚠️ Đã chọn bỏ qua. Trạm chạy trôi tự do theo tự nhiên."}, f)
                        else:
                            # Ghi nhận người dùng vừa chọn giải pháp xử lý -> Chuyển status sang kích hoạt "triggered"
                            with open(CONTROL_FILE, 'w') as f:
                                json.dump({
                                    "status": "triggered", 
                                    "action": data, 
                                    "step_num": 0, 
                                    "needed_temp_delta": 0.0, 
                                    "needed_rh_delta": 0.0, 
                                    "msg": "⚡ Đã tiếp nhận giải pháp xử lý! Đang đồng bộ tính toán công suất điều tiết..."
                                }, f)
                        
                        # Phản hồi lại phía Telegram người dùng để tắt trạng thái loading nút bấm
                        requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/answerCallbackQuery", json={
                            "callback_query_id": query_id, "text": "Đang thực thi giải pháp phần cứng nhà kính!"
                        })
        except Exception:
            pass
        time.sleep(1)

# Đảm bảo luồng ngầm Telegram Bot chỉ khởi tạo duy nhất 1 lần tránh lỗi xung đột cổng
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


# =========================================================================
# 🔄 THUẬT TOÁN ĐIỀU TIẾT TOÁN HỌC CHIA BƯỚC VÀ ĐIỀU KIỆN KHÓA ANTI-SPAM TELEGRAM
# =========================================================================
def trigger_new_data(plant_matrix):
    current_sim_datetime = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
    current_date_str = current_sim_datetime.strftime("Ngày %d/%m")
    current_hour = current_sim_datetime.hour
    
    # 1. Đọc dữ liệu thô từ môi trường nền tự nhiên khí hậu ngoài trời
    base_temp, base_rh = get_weather_by_time(current_sim_datetime)
    
    try:
        with open(CONTROL_FILE, 'r') as f:
            cmd_state = json.load(f)
            
        # 🟢 BƯỚC THỜI ĐIỂM TÊN BIẾN CỐ (Ví dụ: 07h00, 11h00, v.v.) - BẮT ĐẦU NHẬN LỆNH
        if cmd_state["status"] == "triggered":
            buoi_hien_tai = get_biological_block(current_hour)
            v_min, v_max = plant_matrix[buoi_hien_tai]
            # Mục tiêu toán học: Tính toán để ép chỉ số VPD rơi vào chính giữa trung tâm dải Lý Tưởng từng buổi
            target_vpd_center = (v_min + v_max) / 2.0
            
            best_t_delta = 0.0
            best_h_delta = 0.0
            min_error = 999.0
            
            # Quét dải tìm nghiệm tối ưu dựa trên cấu hình kênh tác động của nút bấm
            if cmd_state["action"] in ["fix_hot_temp", "fix_wet_temp"]: 
                # Kênh tác động Nhiệt độ (Kéo lưới hạ nhiệt hoặc Bật sưởi ấm hồng ngoại)
                for t_d in [x * 0.1 for x in range(-200, 200)]:
                    test_vpd = calculate_vpd(base_temp + t_d, base_rh)
                    if abs(test_vpd - target_vpd_center) < min_error:
                        min_error = abs(test_vpd - target_vpd_center)
                        best_t_delta = t_d
            else: 
                # Kênh tác động Độ ẩm (Bật quạt thông gió xả ẩm hoặc phun sương áp lực cao)
                for h_d in [x * 0.5 for x in range(-200, 200)]:
                    test_vpd = calculate_vpd(base_temp, max(0.0, min(100.0, base_rh + h_d)))
                    if abs(test_vpd - target_vpd_center) < min_error:
                        min_error = abs(test_vpd - target_vpd_center)
                        best_h_delta = h_d
                        
            # Lưu các tham số Delta chuẩn xác vừa quét được vào file trạng thái điều khiển chia bước
            cmd_state["status"] = "processing"
            cmd_state["step_num"] = 1
            cmd_state["needed_temp_delta"] = best_t_delta
            cmd_state["needed_rh_delta"] = best_h_delta
            cmd_state["msg"] = f"⚙️ Đang xử lý chu kỳ 1 (Sau 10 phút): Áp dụng 50% hiệu năng phần cứng..."
            
            # Tiến hành thực thi ngay 50% chặng đường sửa sai cho chu kỳ đầu tiên
            st.session_state.temp_offset = best_t_delta / 2.0
            st.session_state.rh_offset = best_h_delta / 2.0
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
                
        # 🟡 BƯỚC CHU KỲ TRUNG GIAN (Sau 10 phút - Ví dụ: 07h10, 11h10) - KHÓA HOÀN TOÀN LỰA CHỌN TELE
        elif cmd_state["status"] == "processing" and cmd_state["step_num"] == 1:
            cmd_state["step_num"] = 2
            cmd_state["msg"] = f"⚙️ Đang xử lý chu kỳ 2 (Sau 20 phút): Đẩy tối đa 100% công suất để ép lọt vùng Lý Tưởng!"
            
            # Đẩy toàn bộ 100% lượng Delta cần bù đã tính toán ở mốc ban đầu để ép cán đích
            st.session_state.temp_offset = cmd_state["needed_temp_delta"]
            st.session_state.rh_offset = cmd_state["needed_rh_delta"]
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
                
        # 🔵 BƯỚC CÁN ĐÍCH AN TOÀN (Sau 20 phút - Ví dụ: 07h20, 11h20) - RESET HOÀN THÀNH
        elif cmd_state["status"] == "processing" and cmd_state["step_num"] == 2:
            cmd_state["status"] = "idle"
            cmd_state["action"] = "none"
            cmd_state["step_num"] = 0
            cmd_state["needed_temp_delta"] = 0.0
            cmd_state["needed_rh_delta"] = 0.0
            cmd_state["msg"] = "✨ Can thiệp hoàn thành xuất sắc! Môi trường đã nằm gọn gàng trong dải Lý Tưởng."
            
            # Thu hồi offset, trả hệ thống về chạy tự động ổn định theo nền thời tiết sạch
            st.session_state.temp_offset = 0.0
            st.session_state.rh_offset = 0.0
            
            with open(CONTROL_FILE, 'w') as f:
                json.dump(cmd_state, f)
    except Exception:
        pass

    # 2. Cập nhật các thông số cảm biến thực tế trên giao diện dựa trên Offset điều tiết phần cứng
    st.session_state.temp = round(base_temp + st.session_state.temp_offset, 2)
    st.session_state.rh = round(max(0.0, min(100.0, base_rh + st.session_state.rh_offset)), 2)
    
    st.session_state.countdown = 15 
    st.session_state.stt_counter += 1
    new_vpd = calculate_vpd(st.session_state.temp, st.session_state.rh)
    
    buoi_hien_tai = get_biological_block(current_hour)
    v_min, v_max = plant_matrix[buoi_hien_tai]
    
    # Định nghĩa nhãn trạng thái trực quan
    if new_vpd >= v_max + 0.5: status_text = "🔴 Quá Nóng"
    elif new_vpd > v_max: status_text = "💛 Nóng"
    elif new_vpd < v_min - 0.2: status_text = "🔵 Quá Ẩm"
    elif new_vpd < v_min: status_text = "🌐 Ẩm"
    else: status_text = "🟩 Lý Tưởng"
    
    # Khởi tạo lý do mặc định dự phòng nếu hàm phân tích phân rã
    reason_text = "Môi trường có sự biến động nhẹ."
    
    # Ghi nhận bản ghi lịch sử chu kỳ mô phỏng đẩy lên đầu danh sách hiển thị bảng biểu
    st.session_state.history.insert(0, {
        "STT": st.session_state.stt_counter, "Ngày": current_date_str,
        "Thời gian mô phỏng": current_sim_datetime, "Hiển thị Giờ": current_sim_datetime.strftime("%H:%M"),
        "datetime_internal": current_sim_datetime, "Nhiệt độ (°C)": st.session_state.temp, "Độ ẩm (%)": st.session_state.rh,
        "VPD (kPa)": round(new_vpd, 2), "Trạng thái": status_text
    })

    # =========================================================================
    # 🔇 THIẾT LẬP KỊCH BẢN 5 BUỔI VÀ CƠ CHẾ PHONG TỎA ANTI-SPAM TRÊN TELEGRAM
    # =========================================================================
    if TELE_TOKEN and TELE_CHAT_ID:
        try:
            with open(CONTROL_FILE, 'r') as f: current_status = json.load(f)["status"]
        except Exception: current_status = "idle"
            
        # ⛔ ĐIỀU KIỆN CỐT LÕI: Chỉ nhắn tin khi hệ thống ở trạng thái rảnh (idle) và có biến cố lệch dải.
        # Khi đang ở trạng thái xử lý chia bước (mốc T+10 phút), Telegram sẽ bị KHÓA CÂM hoàn toàn, không đưa ra thêm lựa chọn.
        if current_status == "idle" and status_text != "🟩 Lý Tưởng":
            unique_days = sorted(list(set([r["Ngày"] for r in st.session_state.history])), reverse=True)
            h_latest = [r for r in st.session_state.history if r["Ngày"] == (unique_days[0] if unique_days else current_date_str)]
            trend, _ = predict_vpd_trend_v3(h_latest, current_hour, plant_matrix)
            clean_trend = trend.replace("Xu hướng:", "").strip()
            
            title_block = "⚠️ BIẾN CỐ MÔI TRƯỜNG"
            tele_buttons = []
            
            # --- PHÂN CHIA CHI TIẾT 5 KỊCH BẢN ĐẶC TRƯNG TRONG NGÀY THEO Ý BẠN ---
            if "🌅 Sáng" in buoi_hien_tai:
                title_block = "🌅 [CẢNH BÁO VPD SÁNG SỚM - LẠNH ẨM ĐỌNG SƯƠNG]"
                reason_text = "🥶 Không khí sáng sớm bão hòa hơi sương, nhiệt độ tụt sâu làm nghẽn mạch thoát nước của lá dâu."
                tele_buttons = [[{"text": "🔥 Đóng Rèm Hông & Bật Đèn Nhiệt Giữ Ấm", "callback_data": "fix_wet_temp"}]]
                
            elif "☀️ Trưa" in buoi_hien_tai:
                title_block = "☀️ [CẢNH BÁO VPD GIỮA TRƯA - BỨC XẠ KHÔ NÓNG]"
                reason_text = "🔥 Bức xạ mặt trời thiêu đốt đỉnh nhà kính, nhiệt độ tăng vọt vượt ngưỡng chịu đựng khiến cây stress gắt."
                tele_buttons = [[{"text": "💨 Kích Hoạt Kéo Lưới Chặn Nắng Giảm Nhiệt", "callback_data": "fix_hot_temp"}]]
                
            elif "🌇 Chiều" in buoi_hien_tai:
                title_block = "🌇 [CẢNH BÁO VPD CHIỀU TA - HANH KHÔ SỤT ẨM]"
                reason_text = "🌵 Nắng quái chiều muộn kèm gió hông đẩy mạnh làm sụt độ ẩm không khí, lá dâu dễ bị cháy rìa."
                tele_buttons = [[{"text": "💦 Kích Hoạt Hệ Thống Phun Sương Tăng Ẩm Mịn", "callback_data": "fix_hot_rh"}]]
                
            elif "🌌 Tối" in buoi_hien_tai:
                title_block = "🌌 [CẢNH BÁO VPD ĐẦU ĐÊM - ĐỘ ẨM TÍCH TỤ]"
                reason_text = "🌧️ Hơi nước tích tụ nhanh khi tắt nắng, nguy cơ đọng sương bề mặt lá tạo môi trường cho nấm bùng phát."
                tele_buttons = [[{"text": "🌪️ Bật Quạt Hút Ép Hạ Ẩm Cưỡng Bức", "callback_data": "fix_wet_rh"}]]
                
            elif "🌙 Khuya" in buoi_hien_tai:
                title_block = "🌙 [CẢNH BÁO VPD ĐÊM KHUYA - SUY KIỆT NHIỆT ĐỘ]"
                reason_text = "❄️ Sương muối và nhiệt độ sụt sâu ban đêm, cần kích hoạt hệ thống sưởi ấm giữ nhiệt nền."
                tele_buttons = [[{"text": "🔥 Bật Cụm Đèn Nhiệt Hồng Ngoại Giữ Ấm Đêm", "callback_data": "fix_wet_temp"}]]

            # Thiết lập cấu trúc nội dung Markdown gửi về điện thoại qua Telegram Telegram
            msg = (f"🌿 *{title_block}*\n"
                   f"⏰ {current_date_str} - Giờ trạm: *{current_sim_datetime.strftime('%H:%M')}*\n"
                   f"📊 Sensor: {st.session_state.temp}°C | {st.session_state.rh}%\n"
                   f"📈 *VPD đo được:* *{new_vpd:.2f} kPa* (Khoảng chuẩn buổi: {v_min}-{v_max})\n"
                   f"📢 *Tình trạng:* *{status_text}*\n"
                   f"🔍 *Nguyên nhân:* _{reason_text}_\n"
                   f"🔮 *Xu hướng tự nhiên:* _{clean_trend}_\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"📲 *Vui lòng nhấn chọn giải pháp phần cứng tối ưu dưới đây để xử lý:*")
            
            tele_buttons.append([{"text": "⏸️ Bỏ qua (Chạy trôi tự do theo thời tiết)", "callback_data": "none"}])
            send_telegram_with_buttons(TELE_TOKEN, TELE_CHAT_ID, msg, tele_buttons)
            
    # Tịnh tiến chu kỳ thời gian giả lập thêm 10 phút sang chu kỳ tiếp theo
    next_dt = current_sim_datetime + timedelta(minutes=10)
    if next_dt.hour == 0 and next_dt.minute == 0: st.session_state.is_running = False; st.session_state.is_completed = True   
    st.session_state.simulated_time = next_dt.strftime("%Y-%m-%d %H:%M:%S")


# =========================================================================
# 💻 GIAO DIỆN ĐIỀU KHIỂN STREAMLIT 
# =========================================================================
st.sidebar.markdown("## 🧭 MENU CHỨC NĂNG")
app_mode = st.sidebar.selectbox("Chọn Tag công việc cần thực hiện:", ["🌿 VPD Realtime & Mô Phỏng", "📥 Phân Tích File IoT JSON"])
st.sidebar.markdown("---")

if app_mode == "🌿 VPD Realtime & Mô Phỏng":
    st.markdown("<h2 style='color: #1E8449; font-size: 26px;'>🌿 HỆ THỐNG GIÁM SÁT VPD REALTIME & ĐIỀU KHIỂN CHIA BƯỚC ĐÚNG TIẾN ĐỘ</h2>", unsafe_allow_html=True)
    
    left_col, right_col = st.columns([3, 7])
    with left_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📋 CẤU HÌNH MA TRẬN PHÂN BUỔI</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            st.caption("💡 Tinh chỉnh cận dưới dải tối ưu của Buổi Sáng:")
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
            
            if st.button("🔄 Reset dữ liệu trạm mô phỏng", type="secondary", use_container_width=True):
                st.session_state.history = []; st.session_state.stt_counter = 0; st.session_state.countdown = 15
                st.session_state.is_running = False; st.session_state.is_completed = False
                st.session_state.simulated_time = "2026-05-24 07:00:00"
                st.session_state.temp_offset = 0.0; st.session_state.rh_offset = 0.0
                with open(CONTROL_FILE, 'w') as f: 
                    json.dump({"status": "idle", "action": "none", "step_num": 0, "needed_temp_delta": 0.0, "needed_rh_delta": 0.0, "msg": "Reset trạm mô phỏng thành công"}, f)
                trigger_new_data(st.session_state.current_matrix)
                st.rerun()

        if st.session_state.stt_counter == 0: 
            trigger_new_data(st.session_state.current_matrix)

        # Cài đặt phân mảnh thời gian đếm ngược tự động cập nhật
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
            
            try:
                with open(CONTROL_FILE, 'r') as f: current_action_msg = json.load(f)["msg"]
            except Exception: current_action_msg = "Ổn định tự động nền."

            with st.container(border=True):
                st.markdown(f"⏰ **Thời gian mô phỏng Giờ Trạm:** `<span style='color:#C0392B; font-weight:bold; font-size:16px;'>{sim_dt.strftime('%H:%M')}</span>`", unsafe_allow_html=True)
                st.caption(f"⏳ Vòng lặp đếm ngược: {st.session_state.countdown}s | Bù nhiệt: {st.session_state.temp_offset:+}°C | Bù ẩm: {st.session_state.rh_offset:+}%")
                st.warning(f"🤖 **Trạng thái điều khiển phần cứng:** {current_action_msg}")
                st.markdown(f"""
                <div class="big-vpd-box">
                    <div class="big-vpd-title">🌿 CHỈ SỐ VPD THỰC TẾ TRÊN BỀ MẶT LÁ</div>
                    <div class="big-vpd-value">{v_calc:.2f} kPa</div>
                    <div class="big-env-value">🌡️ {st.session_state.temp}°C  &nbsp;|&nbsp;  💧 {st.session_state.rh}%</div>
                    <div class="analysis-merge-box">
                        📌 <b>Hiện trạng:</b> {stt}<br>
                        🔍 <b>Kịch bản buổi:</b> {get_biological_block(sim_dt.hour)} (Chuẩn tối ưu: {v_min} - {v_max} kPa)
                    </div>
                </div>
                """, unsafe_allow_html=True)
        live_monitor_panel()

    with right_col:
        st.markdown("<h3 style='color: #1E8449; font-size: 17px;'>📊 BIỂU ĐỒ DIỄN BIẾN MÔI TRƯỜNG NHÀ KÍNH KHI ĐƯỢC ĐIỀU CHỈNH CHIA BƯỚC</h3>", unsafe_allow_html=True)
        if st.session_state.history:
            df_all = pd.DataFrame(st.session_state.history)
            df_f = df_all.iloc[::-1].copy()
            sim_dt = datetime.strptime(st.session_state.simulated_time, "%Y-%m-%d %H:%M:%S")
            v_min_chart, v_max_chart = st.session_state.current_matrix[get_biological_block(sim_dt.hour)]
            
            # Khởi tạo vẽ đồ thị nếu module đồ thị có sẵn
            try:
                st.altair_chart(draw_vpd_chart(df_f, v_min_chart, v_max_chart), use_container_width=True)
                st.altair_chart(draw_combined_temp_humidity_chart(df_f), use_container_width=True)
            except Exception:
                st.caption("📊 [Biểu đồ Altair trực quan diễn biến sẽ hiển thị tại đây khi tích hợp đầy đủ file charts.py]")
            
            st.dataframe(df_f[["STT", "Hiển thị Giờ", "Nhiệt độ (°C)", "Độ ẩm (%)", "VPD (kPa)", "Trạng thái"]].style.apply(style_status_rows, axis=1), use_container_width=True, hide_index=True)
            
elif app_mode == "📥 Phân Tích File IoT JSON":
    st.info("Chức năng phân tích dữ liệu tĩnh từ tệp nhật ký IoT của bạn.")
