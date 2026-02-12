from django.apps import AppConfig


class DataStoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data_store'
    label = 'data_store'
