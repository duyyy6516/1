def draw_combined_temp_humidity_chart(df):
    """
    Biểu đồ 2: 2 ĐƯỜNG THẲNG lồng vào nhau, cùng xuất phát từ góc lề bên trái của trục X.
    - Trục Y bên trái: Tự động scale theo Nhiệt độ để đường uốn lượn rõ nét.
    - Trục Y bên phải: Tự động scale theo Độ ẩm để thấy rõ đỉnh/đáy biến động.
    - Cả hai đường đều bắt đầu vẽ từ lề trái của biểu đồ (Trục X).
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
                # Tự động tối ưu scale theo dữ liệu thực tế để đường uốn lượn đẹp nhất
                scale=alt.Scale(domain=[df['Nhiệt độ (°C)'].min() - 1, df['Nhiệt độ (°C)'].max() + 1]),
                axis=alt.Axis(titleColor='#DC143C', orient='left', grid=True, gridDash=[3,3]))
    )

    temp_points = base.mark_point(
        color='#DC143C', 
        fill='#FFFFFF', 
        size=40,
        shape='square' # Nốt hình vuông màu đỏ cho Nhiệt độ
    ).encode(y=alt.Y('Nhiệt độ (°C):Q'))


    # 2. ĐƯỜNG ĐỘ ẨM KHÔNG KHÍ (%) - Định vị trục Y hiển thị ở bên PHẢI để không đè nén biên độ
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
        shape='circle' # Nốt hình tròn màu xanh cho Độ ẩm
    ).encode(y=alt.Y('Độ ẩm (%):Q'))


    # GỘP 2 LỚP: Giữ trục độc lập (independent) nhưng cả hai đều đi từ trục X gốc lề trái đi ra
    return alt.layer(
        alt.layer(temp_line, temp_points),
        alt.layer(humidity_line, humidity_points)
    ).resolve_scale(
        y='independent'
    ).properties(
        width='container',
        height=220
    )
