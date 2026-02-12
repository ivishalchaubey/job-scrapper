from rest_framework import serializers


class JobSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    external_id = serializers.CharField()
    company_name = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True, default='')
    location = serializers.CharField(allow_blank=True, default='')
    city = serializers.CharField(allow_blank=True, default='')
    state = serializers.CharField(allow_blank=True, default='')
    country = serializers.CharField(allow_blank=True, default='')
    employment_type = serializers.CharField(allow_blank=True, default='')
    department = serializers.CharField(allow_blank=True, default='')
    apply_url = serializers.CharField(allow_blank=True, default='')
    posted_date = serializers.CharField(allow_blank=True, default='')
    job_function = serializers.CharField(allow_blank=True, default='')
    experience_level = serializers.CharField(allow_blank=True, default='')
    salary_range = serializers.CharField(allow_blank=True, default='')
    remote_type = serializers.CharField(allow_blank=True, default='')
    status = serializers.CharField(default='active')
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class JobListSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    external_id = serializers.CharField()
    company_name = serializers.CharField()
    title = serializers.CharField()
    location = serializers.CharField(allow_blank=True, default='')
    city = serializers.CharField(allow_blank=True, default='')
    country = serializers.CharField(allow_blank=True, default='')
    department = serializers.CharField(allow_blank=True, default='')
    employment_type = serializers.CharField(allow_blank=True, default='')
    apply_url = serializers.CharField(allow_blank=True, default='')
    posted_date = serializers.CharField(allow_blank=True, default='')
    status = serializers.CharField(default='active')


class ScrapingRunSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    company_name = serializers.CharField()
    run_date = serializers.DateTimeField()
    jobs_scraped = serializers.IntegerField()
    status = serializers.CharField()
    error_message = serializers.CharField(allow_null=True, allow_blank=True)


class CompanyStatsSerializer(serializers.Serializer):
    company_name = serializers.CharField()
    count = serializers.IntegerField()
    last_scraped = serializers.DateTimeField(allow_null=True)


class DashboardStatsSerializer(serializers.Serializer):
    total_jobs = serializers.IntegerField()
    active_companies = serializers.IntegerField()
    total_scrapers = serializers.IntegerField()
    success_rate = serializers.FloatField()
    last_scrape = serializers.DateTimeField(allow_null=True)
