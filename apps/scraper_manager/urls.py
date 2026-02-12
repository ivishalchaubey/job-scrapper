from django.urls import path
from . import views

urlpatterns = [
    path('start/', views.start_scrape_view, name='start-scrape'),
    path('start/<str:company_name>/', views.start_single_scrape_view, name='start-single-scrape'),
    path('tasks/', views.task_list_view, name='task-list'),
    path('tasks/<str:task_id>/', views.task_detail_view, name='task-detail'),
    path('tasks/<str:task_id>/cancel/', views.cancel_task_view, name='cancel-task'),
    path('scrapers/', views.scraper_list_view, name='scraper-list'),
]
