import math
import numpy as np

def calculate_vpd(temp, humidity):
    """
    Công thức tính Áp suất hơi hụt (VPD) tiêu chuẩn từ Nhiệt độ và Độ ẩm tương đối.
    """
    # Tính VPsat (Áp suất hơi bão hòa) bằng phương trình Tetens
    vp_sat = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    # Tính VPair (Áp suất hơi thực tế trong không khí)
    vp_air = vp_sat * (humidity / 100.0)
    # Độ hụt áp suất hơi gánh chịu
    vpd = vp_sat - vp_air
    return round(vpd, 2)

def get_weather_by_time(dt_obj):
    """
    Giả lập dữ liệu thời tiết biến thiên hình sin thực tế theo giờ tại nhà kính Đà Lạt.
    """
    hour = dt_obj.hour + dt_obj.minute / 60.0
    
    # Nhiệt độ đạt cực tiểu lúc 5h sáng, cực đại lúc 13h30 trưa
    temp = 18.0 + 7.5 * math.sin((hour - 8.0) * math.pi / 12.0)
    # Thêm chút nhiễu hạt nhỏ ngẫu nhiên cho thật
    temp += np.random.uniform(-0.4, 0.4)
    
    # Độ ẩm tỷ lệ nghịch với nhiệt độ không khí
    rh = 82.0 - 25.0 * math.sin((hour - 8.0) * math.pi / 12.0)
    rh += np.random.uniform(-1.5, 1.5)
    
    # Khống chế chặn lề dữ liệu an toàn sinh học
    if rh > 100.0: rh = 100.0
    if rh < 20.0: rh = 20.0
    
    return round(temp, 1), round(rh, 1)
