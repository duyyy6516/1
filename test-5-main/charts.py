import altair as alt
import pandas as pd

def draw_vpd_chart(df, v_min, v_max):
    """
    Biểu đồ 1: Thể hiện đường thực tế VPD và dải giới hạn mục tiêu của cây
    """
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()

    # Cấu hình trục ngang thời gian chi tiết
    base_data = alt.Chart(df).encode(
        x=alt.X('Hiển thị Giờ:O', 
                title='Thời gian chi tiết trong toàn bộ ngày',
                axis=alt.Axis(labelAngle=-90, labelColor='#2C3E50', titleColor='#2C3E50', labelFontSize=11))
    )

    # Đường line xu hướng dữ liệu thực tế
    vpd_line = base_data.mark_line(
        color='#27AE60', 
        strokeWidth=3, 
        interpolate='monotone'
    ).encode(
        y=alt.Y('VPD (kPa):Q', 
                title='Chỉ số VPD (kPa)', 
                scale=alt.Scale(domain=[0.0, 2.5]),
                axis=alt.Axis(grid=True, gridDash=[3,3], gridColor='#EAEAEA'))
    )

    # Điểm tròn nút dữ liệu hỗ trợ Tooltip tương tác
    vpd_points = base_data.mark_point(
        color='#27AE60', 
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

    # Vạch đứt cảnh báo sàn cạn dưới (v_min)
    rule_min = alt.Chart(pd.DataFrame({'y': [v_min]})).mark_rule(
        color='#E67E22', 
        strokeWidth=1.5, 
        strokeDash=[4, 4]
    ).encode(y='y:Q')

    # Vạch đứt cảnh báo trần cạn trên (v_max)
    rule_max = alt.Chart(pd.DataFrame({'y': [v_max]})).mark_rule(
        color='#C0392B', 
        strokeWidth=1.5, 
        strokeDash=[4, 4]
    ).encode(y='y:Q')

    # Chồng layer xuất bản biểu đồ phẳng
    return alt.layer(vpd_line, vpd_points, rule_min, rule_max).properties(width='container', height=320)


def draw_combined_temp_humidity_chart(df):
    """
    Biểu đồ 2: Trục kép độc lập lồng ghép cột Độ ẩm (%) và đường Nhiệt độ (°C)
    """
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()

    base = alt.Chart(df).encode(
        x=alt.X('Hiển thị Giờ:O', title='Mốc chu kỳ thời gian', axis=alt.Axis(labelAngle=-90, labelFontSize=11))
    )

    # Cột xanh lam mờ biểu thị ẩm độ
    humidity_bar = base.mark_bar(
        color='#3498DB', 
        opacity=0.35, 
        size=14
    ).encode(
        y=alt.Y('Độ ẩm (%):Q', 
                title='Độ ẩm không khí (%)',
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(titleColor='#3498DB', orient='right', grid=False))
    )

    # Đường đỏ thẫm biểu thị nhiệt độ môi trường
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

    return alt.layer(humidity_bar, temp_line, temp_points).resolve_scale(y='independent').properties(width='container', height=220)
