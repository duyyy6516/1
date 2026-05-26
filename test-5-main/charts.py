import altair as alt
import pandas as pd

def draw_vpd_chart(df, v_min, v_max):
    """
    Biểu đồ 1: Thể hiện đường thực tế VPD và dải giới hạn mục tiêu của cây
    - Dưới ngưỡng (Quá Ẩm): Khối nền Màu Xanh dương
    - Trong ngưỡng (Lý tưởng): Khối nền Màu Xanh lá
    - Trên ngưỡng (Quá Nóng): Khối nền Màu Đỏ
    """
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()

    # Tạo các cột biên để Altair đổ vùng màu phẳng (Rect) không bị lỗi hệ thống
    df_zone = df.copy()
    df_zone['zero'] = 0.0
    df_zone['v_min'] = v_min
    df_zone['v_max'] = v_max
    df_zone['max_limit'] = 2.5

    base_zone = alt.Chart(df_zone).encode(
        x=alt.X('Hiển thị Giờ:O', title='Thời gian chi tiết trong ngày', axis=alt.Axis(labelAngle=-90))
    )

    # 1. Khối nền DƯỚI NGƯỠNG (Quá Ẩm) - Màu Xanh dương
    zone_under = base_zone.mark_rect(opacity=0.25, color='#2980B9').encode(
        y=alt.Y('zero:Q'),
        y2=alt.Y2('v_min:Q')
    )

    # 2. Khối nền TRONG NGƯỠNG (Lý tưởng) - Màu Xanh lá
    zone_ideal = base_zone.mark_rect(opacity=0.3, color='#27AE60').encode(
        y=alt.Y('v_min:Q'),
        y2=alt.Y2('v_max:Q')
    )

    # 3. Khối nền TRÊN NGƯỠNG (Khô Nóng) - Màu Đỏ
    zone_over = base_zone.mark_rect(opacity=0.25, color='#C0392B').encode(
        y=alt.Y('v_max:Q'),
        y2=alt.Y2('max_limit:Q')
    )

    # 4. Đường line thực tế dữ liệu VPD màu xám đen đậm nổi bật
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

    # Node tròn dữ liệu tương tác xem Tooltip
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

    return alt.layer(zone_under, zone_ideal, zone_over, vpd_line, vpd_points).properties(
        width='container',
        height=320
    )


def draw_combined_temp_humidity_chart(df):
    """
    Biểu đồ 2: 2 ĐƯỜNG THẲNG lồng vào nhau, cùng xuất phát vẽ từ lề bên TRÁI của biểu đồ (Trục X chung).
    - Trục Y bên trái: Tự động scale theo Nhiệt độ để đường uốn lượn rõ nét.
    - Trục Y bên phải: Tự động scale theo Độ ẩm để thấy rõ đỉnh/đáy biến động.
    """
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()

    # Khởi tạo trục X chung cho cả hai đường dữ liệu
    base = alt.Chart(df).encode(
        x=alt.X('Hiển thị Giờ:O', 
                title='Mốc chu kỳ thời gian', 
                axis=alt.Axis(labelAngle=-90, labelFontSize=11))
    )

    # 1. ĐƯỜNG NHIỆT ĐỘ MÔI TRƯỜNG (°C) - Định vị trục Y hiển thị ở bên TRÁI
    temp_line = base.mark_line(
        color='#DC143C', 
        strokeWidth=3,
        interpolate='monotone'
    ).encode(
        y=alt.Y('Nhiệt độ (°C):Q', 
                title='Nhiệt độ môi trường (°C)',
                scale=alt.Scale(domain=[df['Nhiệt độ (°C)'].min() - 1, df['Nhiệt độ (°C)'].max() + 1]),
                axis=alt.Axis(titleColor='#DC143C', orient='left', grid=True, gridDash=[3,3]))
    )

    temp_points = base.mark_point(
        color='#DC143C', 
        fill='#FFFFFF', 
        size=40,
        shape='square'  # Node hình vuông màu đỏ cho Nhiệt độ
    ).encode(y=alt.Y('Nhiệt độ (°C):Q'))

    # 2. ĐƯỜNG ĐỘ ẨM KHÔNG KHÍ (%) - Định vị trục Y hiển thị ở bên PHẢI
    humidity_line = base.mark_line(
        color='#3498DB', 
        strokeWidth=2.5,
        interpolate='monotone'
    ).encode(
        y=alt.Y('Độ ẩm (%):Q', 
                title='Độ ẩm không khí (%)',
                scale=alt.Scale(domain=[df['Độ ẩm (%)'].min() - 5, min(100, df['Độ ẩm (%)'].max() + 5)]),
                axis=alt.Axis(titleColor='#3498DB', orient='right', grid=False))
    )
    
    humidity_points = base.mark_point(
        color='#3498DB', 
        fill='#FFFFFF', 
        size=35,
        shape='circle'  # Node hình tròn màu xanh cho Độ ẩm
    ).encode(y=alt.Y('Độ ẩm (%):Q'))

    # Gộp 2 lớp: Giữ trục độc lập (independent) nhưng xuất phát đồng thời từ trục X lề trái
    return alt.layer(
        alt.layer(temp_line, temp_points),
        alt.layer(humidity_line, humidity_points)
    ).resolve_scale(
        y='independent'
    ).properties(
        width='container',
        height=220
    )
