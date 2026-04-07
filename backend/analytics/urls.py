# from django.urls import path
# from .views import (
#     PerformanceReportListView, GenerateReportView,
#     EquityCurveView, DrawdownAnalysisView, InsightsView,
#     CalendarHeatmapView
# )

# urlpatterns = [
#     path('reports/', PerformanceReportListView.as_view(), name='performance-reports'),
#     path('reports/generate/', GenerateReportView.as_view(), name='generate-report'),
#     path('equity-curve/', EquityCurveView.as_view(), name='equity-curve'),
#     path('drawdown/', DrawdownAnalysisView.as_view(), name='drawdown-analysis'),
#     path('insights/', InsightsView.as_view(), name='insights'),
#     path('calendar-heatmap/', CalendarHeatmapView.as_view(), name='calendar-heatmap'),
# ]
from django.urls import path
from .views import (
    PerformanceReportListView, GenerateReportView,
    EquityCurveView, DrawdownAnalysisView,
    InsightsView, InsightDetailView,
    CalendarHeatmapView,
)

urlpatterns = [
    # Reports
    path("reports/",          PerformanceReportListView.as_view(), name="performance-reports"),
    path("reports/generate/", GenerateReportView.as_view(),        name="generate-report"),

    # Charts
    path("equity-curve/",     EquityCurveView.as_view(),           name="equity-curve"),
    path("drawdown/",         DrawdownAnalysisView.as_view(),       name="drawdown-analysis"),
    path("calendar-heatmap/", CalendarHeatmapView.as_view(),       name="calendar-heatmap"),

    # AI Insights
    # GET  → list saved insights
    # POST → generate new AI insights  (body: { "days": 30 })
    path("insights/",         InsightsView.as_view(),               name="insights"),

    # PATCH → acknowledge or action an insight
    path("insights/<uuid:pk>/", InsightDetailView.as_view(),        name="insight-detail"),
]