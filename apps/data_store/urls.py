from django.urls import path
from . import views

urlpatterns = [
    path('jobs/', views.job_list_view, name='job-list'),
    path('jobs/delete/', views.delete_jobs_view, name='delete-jobs'),
    path('jobs/clear-all/', views.clear_all_view, name='clear-all'),
    path('jobs/<str:job_id>/', views.job_detail_view, name='job-detail'),
    path('stats/', views.stats_view, name='stats'),
    path('companies/', views.companies_view, name='companies'),
    path('history/', views.scraping_history_view, name='scraping-history'),
    path('health/', views.health_view, name='health'),
    path('export/xlsx/', views.export_xlsx_view, name='export-xlsx'),
]
