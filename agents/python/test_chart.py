from src.lib.chart_tool import GeneratePlotlyChartInput, ChartDataSeries, ChartDataPoint, ChartType, create_chart_html
import logging
logging.basicConfig(level=logging.INFO)

print("Testing Candlestick...")
params_candle = GeneratePlotlyChartInput(
    title="AAPL Stock", x_axis_label="Date", y_axis_label="Price", chart_type=ChartType.CANDLESTICK,
    series=[ChartDataSeries(series_name="AAPL", data=[
        ChartDataPoint(label="2024-01-01", value=0, open=150, high=155, low=149, close=152),
        ChartDataPoint(label="2024-01-02", value=0, open=152, high=160, low=151, close=159)
    ])]
)
html = create_chart_html(params_candle)
print("Candle SUCCESS:", len(html))

print("Testing Map...")
params_map = GeneratePlotlyChartInput(
    title="GDP Map", x_axis_label="Country", y_axis_label="GDP", chart_type=ChartType.MAP,
    series=[ChartDataSeries(series_name="World", data=[
        ChartDataPoint(label="Thailand", value=500, country_iso="THA"),
        ChartDataPoint(label="USA", value=20000, country_iso="USA")
    ])]
)
html = create_chart_html(params_map)
print("Map SUCCESS:", len(html))

print("Testing Sunburst...")
params_sun = GeneratePlotlyChartInput(
    title="Company Structure", x_axis_label="", y_axis_label="", chart_type=ChartType.SUNBURST,
    series=[ChartDataSeries(series_name="Corp", data=[
        ChartDataPoint(label="Global", value=100, parent=""),
        ChartDataPoint(label="Asia", value=40, parent="Global"),
        ChartDataPoint(label="Thailand", value=20, parent="Asia")
    ])]
)
html = create_chart_html(params_sun)
print("Sunburst SUCCESS:", len(html))

