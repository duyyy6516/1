import altair as alt
import pandas as pd

def draw_vpd_chart(df, v_min, v_max):
    """
    Biểu đồ 1: Đường diễn biến chỉ số VPD thực tế chạy trên nền 3 khối màu Solid phân tầng:
    - Dưới ngưỡng (Quá Ẩm): Màu Xanh dương
    - Trong ngưỡng (Lý tưởng): Màu Xanh lá
    - Trên ngưỡng (Quá Nóng): Màu Đỏ
    """
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()

    # Thêm các cột giả định biên độ trần/sàn quantitative để Altair dựng vùng màu (Rect) không bị lỗi Schema
    df_zone = df.copy()
    df_zone['zero'] = 0.0
    df_zone['v_min'] = v_min
    df_zone['v_max'] = v_max
    df_zone['max_limit'] = 2.5

    # Lớp cơ sở định vị tọa độ thời gian X
    base_zone = alt.Chart(df_zone).encode(
        x=alt.X('Hiển thị Giờ:O', title='Thời gian chi tiết trong ngày')
    )

    # 1. Khối nền DƯỚI NGƯỠNG - Màu Xanh dương (#2980B9)
    zone_under = base_zone.mark_rect(opacity=0.3, color='#2980B9').encode(
        y=alt.Y('zero:Q'),
        y2=alt.Y2('v_min:Q')
    )

    # 2. Khối nền TRONG NGƯỠNG LÝ TƯỞNG - Màu Xanh lá (#27AE60)
    zone_ideal = base_zone.mark_rect(opacity=0.35, color='#27AE60').encode(
        y=alt.Y('v_min:Q'),
        y2=alt.Y2('v_max:Q')
    )

    # 3. Khối nền TRÊN NGƯỠNG - Màu Đỏ (#C0392B)
    zone_over = base_zone.mark_rect(opacity=0.3, color='#C0392B').encode(
        y=alt.Y('v_max:Q'),
        y2=alt.Y2('max_limit:Q')
    )

    # 4. Đường line dữ liệu VPD thực tế màu xám đen đậm để nổi bật trên 3 nền màu
    vpd_line = base_zone.mark_line(
        color='#17202A', 
        strokeWidth=3, 
        interpolate='monotone'
    ).encode(
        y=alt.Y('VPD (kPa):Q', 
                title='Chỉ số VPD (kPa)', 
                scale=alt.Scale(domain=[0.0, 2.5]),
                axis=alt.Axis(grid=True, gridDash=[3,3], gridColor='#EAEAEA'))
    )

    # Node điểm tròn dữ liệu tích hợp Tooltip soi cứu thông minh
    vpd_points = base_zone.mark_point(
        color='#17202A', 
        fill='#FFFFFF', 
        size=65, 
        strokeWidth=2
    ).encode(
        y=alt.Y('VPD (kPa):Q'),
        tooltip=[
            alt.Tooltip('Hiển thị Giờ:O', title='Thời gian'),
            alt.Tooltip('Nhiệt độ (°C):Q', title='Nhiệt độ (°C)'),
            alt.Tooltip('Độ ẩm (%):Q', title='Độ ẩm (%)'),
            alt.Tooltip('VPD (kPa):Q', title='Chỉ số VPD'),
            alt.Tooltip('Trạng thái:N', title='Đánh giá')
        ]
    )

    # Gộp 3 khối màu nền phân tầng và đường dữ liệu vào thành 1 biểu đồ
    return alt.layer(zone_under, zone_ideal, zone_over, vpd_line, vpd_points).properties(
        width='container',
        height=320
    )


def draw_combined_temp_humidity_chart(df):
    """
    Biểu đồ 2: Hệ thống trục kép lồng ghép 2 ĐƯỜNG THẲNG (Line Chart) song hành song song:
    - Đường Nhiệt độ (°C): Màu đỏ Crimson vạch lề trái
    - Đường Độ ẩm (%): Màu xanh Skyblue vạch lề phải
    """
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()

    base = alt.Chart(df).encode(
        x=alt.X('Hiển thị Giờ:O', title='Mốc chu kỳ thời gian', axis=alt.Axis(labelAngle=-90, labelFontSize=11))
    )

    # 1. ĐƯỜNG ĐỘ ẨM KHÔNG KHÍ (%)
    humidity_line = base.mark_line(
        color='#3498DB', 
        strokeWidth=2.5,
        interpolate='monotone'
    ).encode(
        y=alt.Y('Độ ẩm (%):Q', 
                title='Độ ẩm không khí (%)',
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(titleColor='#3498DB', orient='right', grid=False))
    )
    
    humidity_points = base.mark_point(
        color='#3498DB', 
        fill='#FFFFFF', 
        size=30
    ).encode(y=alt.Y('Độ ẩm (%):Q'))

    # 2. ĐƯỜNG NHIỆT ĐỘ MÔI TRƯỜNG (°C)
    temp_line = base.mark_line(
        color='#DC143C', 
        strokeWidth=3,
        interpolate='monotone'
    ).encode(
        y=alt.Y('Nhiệt độ (°C):Q', 
                title='Nhiệt độ môi trường (°C)',
                scale=alt.Scale(domain=[df['Nhiệt độ (°C)'].min() - 2, df['Nhiệt độ (°C)'].max() + 2]),
                axis=alt.Axis(titleColor='#DC143C', orient='left', grid=True, gridDash=[3,3]))
    )

    temp_points = base.mark_point(
        color='#DC143C', 
        fill='#FFFFFF', 
        size=35
    ).encode(y=alt.Y('Nhiệt độ (°C):Q'))

    # Hòa trộn 2 trục đồ thị tuyến tính lồng nhau độc lập quy mô dữ liệu
    return alt.layer(
        alt.layer(humidity_line, humidity_points),
        alt.layer(temp_line, temp_points)
    ).resolve_scale(
        y='independent'
    ).properties(
        width='container',
        height=220
    )
