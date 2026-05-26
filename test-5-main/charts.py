import altair as alt
import pandas as pd

def draw_temperature_chart(df):
    if df.empty: 
        return alt.Chart(pd.DataFrame()).mark_text()
        
    chart = alt.Chart(df).mark_line(color="#FF4B4B", point=True).encode(
        x=alt.X('datetime_internal:T', title="Mốc thời gian", axis=alt.Axis(format="%H:%M")), 
        y=alt.Y("Nhiệt độ (°C):Q", scale=alt.Scale(zero=False), axis=alt.Axis(title="Nhiệt độ (°C)")),
        tooltip=['Ngày', 'Hiển thị Giờ', "Nhiệt độ (°C)"]
    ).properties(height=260).interactive().configure_axisX(
        labelAngle=-45,
        labelOverlap="greedy",  
        labelPadding=8
    ).configure_view(
        strokeOpacity=0       
    )
    return chart

def draw_humidity_chart(df):
    if df.empty: 
        return alt.Chart(pd.DataFrame()).mark_text()
        
    chart = alt.Chart(df).mark_line(color="#0068C9", point=True).encode(
        x=alt.X('datetime_internal:T', title="Mốc thời gian", axis=alt.Axis(format="%H:%M")),
        y=alt.Y("Độ ẩm (%):Q", scale=alt.Scale(zero=False), axis=alt.Axis(title="Độ ẩm (%)")),
        tooltip=['Ngày', 'Hiển thị Giờ', "Độ ẩm (%)"]
    ).properties(height=260).interactive().configure_axisX(
        labelAngle=-45,
        labelOverlap="greedy",
        labelPadding=8
    ).configure_view(
        strokeOpacity=0
    )
    return chart

def draw_vpd_chart(df, vpd_min, vpd_max):
    if len(df) == 0:
        return alt.Chart(df).mark_blank()
        
    try:
        actual_max_vpd = float(df['VPD (kPa)'].max())
    except:
        actual_max_vpd = 2.0
        
    # Thiết lập đỉnh trục Y linh hoạt dựa trên dữ liệu thật
    Y_LIMIT = max(actual_max_vpd + 0.5, 3.0)
    
    # 1. Khối nền màu xanh (Quá ẩm)
    rect_blue = alt.Chart(df).mark_rect(color='#0068C9', opacity=0.15).encode(
        y=alt.Y(datum=0.0),
        y2=alt.Y2(datum=vpd_min)
    )
    
    # 2. Khối nền màu đỏ (Quá khô) - Khống chế độ cao phủ nền để tránh tràn ngập đồ thị
    rect_red = alt.Chart(df).mark_rect(color='#FF4B4B', opacity=0.15).encode(
        y=alt.Y(datum=vpd_max),
        y2=alt.Y2(datum=min(vpd_max + 1.0, Y_LIMIT))
    )
    
    # 3. Đường đồ thị chính màu xanh lá cây đậm - Bật tương tác chuột TRỰC TIẾP tại đây
    line_vpd = alt.Chart(df).mark_line(color="#2E7D32", size=2.5, point=len(df) < 100, clip=True).encode(
        x=alt.X('datetime_internal:T', title="Mốc thời gian", axis=alt.Axis(format="%H:%M")),
        y=alt.Y('VPD (kPa):Q', 
               scale=alt.Scale(domain=[0.0, Y_LIMIT]), 
               axis=alt.Axis(title="Chỉ số VPD (kPa)", grid=True)),
        tooltip=['Ngày', 'Hiển thị Giờ', 'VPD (kPa)', 'Trạng thái']
    ).interactive() 
    
    # Gộp các lớp chồng lên nhau: Dìm rect_blue và rect_red làm nền, line_vpd nằm trên cùng nhận chuột
    chart = alt.layer(
        rect_blue, rect_red, line_vpd
    ).properties(
        height=260
    ).configure_axisX(  
        labelAngle=-45,
        labelOverlap="greedy",
        labelPadding=8
    ).configure_view(
        strokeOpacity=0
    )
    
    return chart

def draw_combined_chart(df):
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_text()

    base = alt.Chart(df).encode(
        x=alt.X('datetime_internal:T', title="Mốc thời gian", axis=alt.Axis(format="%H:%M"))
    )
    
    line_t = base.mark_line(color='#FF4B4B', strokeDash=[3,3]).encode(
        y=alt.Y("Nhiệt độ (°C):Q", axis=alt.Axis(title="Nhiệt độ / Độ ẩm", titleColor='#0068C9')),
        tooltip=['Hiển thị Giờ', "Nhiệt độ (°C)"]
    )
    
    line_r = base.mark_line(color='#0068C9').encode(
        y=alt.Y("Độ ẩm (%):Q"),
        tooltip=['Hiển thị Giờ', "Độ ẩm (%)"]
    )
    
    weather_layer = alt.layer(line_t, line_r)
    
    line_v = base.mark_line(color="#2E7D32", size=3).encode(
        y=alt.Y('VPD (kPa):Q', axis=alt.Axis(title="Áp suất VPD (kPa)", titleColor='#2E7D32'), scale=alt.Scale(domain=[0.0, 3.0], clamp=True)),
        tooltip=['Hiển thị Giờ', 'VPD (kPa)', 'Trạng thái']
    )
    
    chart = alt.layer(weather_layer, line_v).properties(height=260).resolve_scale(
        y='independent'
    ).interactive().configure_axisX(
        labelAngle=-45,
        labelOverlap="greedy",
        labelPadding=8
    ).configure_view(
        strokeOpacity=0
    )
    
    return chart
