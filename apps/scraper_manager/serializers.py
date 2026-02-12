from rest_framework import serializers


class ScrapeTaskSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    task_id = serializers.CharField()
    company_name = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    total_companies = serializers.IntegerField()
    completed_companies = serializers.IntegerField()
    total_jobs_found = serializers.IntegerField()
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    results = serializers.DictField()
    error_message = serializers.CharField(allow_blank=True)
    progress_percent = serializers.FloatField(read_only=True)


class StartScrapeSerializer(serializers.Serializer):
    companies = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of company names to scrape. Omit or send empty to scrape all."
    )
    all = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Set to true to scrape all companies"
    )
    max_workers = serializers.IntegerField(
        required=False,
        default=10,
        min_value=1,
        max_value=20,
        help_text="Number of parallel workers (default: 10)"
    )
    timeout = serializers.IntegerField(
        required=False,
        default=180,
        min_value=30,
        max_value=600,
        help_text="Per-scraper timeout in seconds (default: 180)"
    )
