import altair as alt
import pandas as pd

def draw_vpd_chart(df, vpd_min, vpd_max):
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()
    
    df_chart = df.copy()
    df_chart['y_min_bound'] = vpd_min
    df_chart['y_max_bound'] = vpd_max
    df_chart['y_floor'] = 0.0
    df_chart['y_roof'] = 3.0

    x_axis = alt.X(field='Hiển thị Giờ', type='ordinal', title='Mốc thời gian chu kỳ', sort=None)

    bg_under = alt.Chart(df_chart).mark_area(color='#E3F2FD', opacity=0.8).encode(
        x=x_axis,
        y=alt.Y(field='y_floor', type='quantitative'),
        y2=alt.Y2(field='y_min_bound')
    )
    
    bg_ideal = alt.Chart(df_chart).mark_area(color='#E8F5E9', opacity=0.8).encode(
        x=x_axis,
        y=alt.Y(field='y_min_bound', type='quantitative'),
        y2=alt.Y2(field='y_max_bound')
    )
    
    bg_over = alt.Chart(df_chart).mark_area(color='#FFEBEE', opacity=0.8).encode(
        x=x_axis,
        y=alt.Y(field='y_max_bound', type='quantitative'),
        y2=alt.Y2(field='y_roof')
    )

    vpd_line = alt.Chart(df_chart).mark_line(color='#2E7D32', strokeWidth=3.5).encode(
        x=x_axis,
        y=alt.Y(field='VPD (kPa)', type='quantitative', title='VPD (kPa)', scale=alt.Scale(domain=[0, 2.5]))
    )
    
    vpd_points = alt.Chart(df_chart).mark_circle(color='#1B5E20', size=70).encode(
        x=x_axis,
        y=alt.Y(field='VPD (kPa)', type='quantitative'),
        tooltip=['Hiển thị Giờ', 'Nhiệt độ (°C)', 'Độ ẩm (%)', 'VPD (kPa)', 'Trạng thái']
    )

    return alt.layer(bg_under, bg_ideal, bg_over, vpd_line, vpd_points).properties(height=280).interactive()

def draw_temp_humidity_combo_chart(df):
    """Vẽ đồ thị Nhiệt độ & Độ ẩm chung một trục X từ trái sang phải, tách biệt trục Y trái/phải chính xác"""
    if df.empty:
        return alt.Chart(pd.DataFrame()).mark_blank()
        
    df_chart = df.copy()
    x_axis = alt.X(field='Hiển thị Giờ', type='ordinal', title='Mốc thời gian', sort=None)
    
    # Trục Y bên trái: Nhiệt độ (Đường thẳng và chấm điểm đều canh theo X chuẩn)
    temp_line = alt.Chart(df_chart).mark_line(color='#FF4B4B', strokeWidth=2.5).encode(
        x=x_axis,
        y=alt.Y(field='Nhiệt độ (°C)', type='quantitative', title='Nhiệt độ (°C)', axis=alt.Axis(titleColor='#FF4B4B'))
    )
    temp_points = alt.Chart(df_chart).mark_circle(color='#FF4B4B', size=50).encode(
        x=x_axis,
        y=alt.Y(field='Nhiệt độ (°C)', type='quantitative'),
        tooltip=['Hiển thị Giờ', 'Nhiệt độ (°C)', 'Độ ẩm (%)', 'Trạng thái']
    )
    
    # Trục Y bên phải: Độ ẩm
    hum_line = alt.Chart(df_chart).mark_line(color='#0068C9', strokeWidth=2.5).encode(
        x=x_axis,
        y=alt.Y(field='Độ ẩm (%)', type='quantitative', title='Độ ẩm (%)', axis=alt.Axis(titleColor='#0068C9')),
    )
    hum_points = alt.Chart(df_chart).mark_circle(color='#0068C9', size=50).encode(
        x=x_axis,
        y=alt.Y(field='Độ ẩm (%)', type='quantitative'),
        tooltip=['Hiển thị Giờ', 'Nhiệt độ (°C)', 'Độ ẩm (%)', 'Trạng thái']
    )
    
    # Kết hợp lớp trục kép (resolve_scale độc lập trục Y nhưng đồng bộ trục X bên trái)
    chart = alt.layer(
        alt.layer(temp_line, temp_points),
        alt.layer(hum_line, hum_points)
    ).resolve_scale(
        y='independent'
    ).properties(height=240)
    
    return chart
