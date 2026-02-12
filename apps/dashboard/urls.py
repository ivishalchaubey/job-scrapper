from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='dashboard'),
    path('jobs/', views.jobs_view, name='dashboard-jobs'),
    path('scrapers/', views.scrapers_view, name='dashboard-scrapers'),
]
