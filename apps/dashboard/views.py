from django.shortcuts import render


def index_view(request):
    return render(request, 'dashboard/index.html')


def jobs_view(request):
    return render(request, 'dashboard/jobs.html')


def scrapers_view(request):
    return render(request, 'dashboard/scrapers.html')
