from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from . import services
from .serializers import ScrapeTaskSerializer, StartScrapeSerializer
from .engine import start_scrape, cancel_scrape
from scrapers.registry import ALL_COMPANY_CHOICES, SCRAPER_MAP


@extend_schema(
    request=StartScrapeSerializer,
    responses=ScrapeTaskSerializer,
    description="Start scraping for specified companies or all companies"
)
@api_view(['POST'])
def start_scrape_view(request):
    serializer = StartScrapeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    companies = data.get('companies', [])
    scrape_all = data.get('all', False)
    max_workers = data.get('max_workers', 10)
    timeout = data.get('timeout', 180)

    if scrape_all or not companies:
        companies = ALL_COMPANY_CHOICES
    else:
        invalid = [c for c in companies if c.lower() not in SCRAPER_MAP]
        if invalid:
            return Response(
                {'error': f'Unknown companies: {", ".join(invalid)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    task = start_scrape(companies=companies, max_workers=max_workers, timeout=timeout)
    return Response(task, status=status.HTTP_201_CREATED)


@extend_schema(
    responses=ScrapeTaskSerializer,
    description="Start scraping for a single company"
)
@api_view(['POST'])
def start_single_scrape_view(request, company_name):
    if company_name.lower() not in SCRAPER_MAP:
        return Response(
            {'error': f'Unknown company: {company_name}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    display_name = next(
        (c for c in ALL_COMPANY_CHOICES if c.lower() == company_name.lower()),
        company_name,
    )
    timeout = request.data.get('timeout', 180)
    max_workers = request.data.get('max_workers', 1)
    task = start_scrape(companies=[display_name], max_workers=max_workers, timeout=timeout)
    return Response(task, status=status.HTTP_201_CREATED)


@extend_schema(
    responses=ScrapeTaskSerializer(many=True),
    description="List all scrape tasks"
)
@api_view(['GET'])
def task_list_view(request):
    services.cleanup_stale_tasks()
    return Response(services.list_tasks())


@extend_schema(
    responses=ScrapeTaskSerializer,
    description="Get scrape task progress by task_id"
)
@api_view(['GET'])
def task_detail_view(request, task_id):
    task = services.get_task(task_id)
    if not task:
        return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response(task)


@extend_schema(
    responses=ScrapeTaskSerializer,
    description="Cancel a running scrape task"
)
@api_view(['POST'])
def cancel_task_view(request, task_id):
    success = cancel_scrape(task_id)
    if not success:
        return Response(
            {'error': 'Task not found or not running'},
            status=status.HTTP_400_BAD_REQUEST
        )
    task = services.get_task(task_id)
    return Response(task)


@extend_schema(description="List all available scraper companies")
@api_view(['GET'])
def scraper_list_view(request):
    return Response({
        'total': len(ALL_COMPANY_CHOICES),
        'companies': sorted(ALL_COMPANY_CHOICES),
    })


@extend_schema(description="Get scraper info (URL, class name) for a company")
@api_view(['GET'])
def scraper_info_view(request, company_name):
    scraper_class = SCRAPER_MAP.get(company_name.lower())
    if not scraper_class:
        return Response({'error': 'Unknown company'}, status=status.HTTP_404_NOT_FOUND)

    display_name = next(
        (c for c in ALL_COMPANY_CHOICES if c.lower() == company_name.lower()),
        company_name,
    )

    url = ''
    try:
        instance = scraper_class()
        url = getattr(instance, 'url', '')
    except Exception:
        pass

    return Response({
        'company': display_name,
        'url': url,
        'scraper_class': scraper_class.__name__,
    })
