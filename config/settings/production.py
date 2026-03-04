from .base import *

DEBUG = False
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

# Only enable secure cookies if you have HTTPS set up
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

CORS_ALLOWED_ORIGINS = [
    "http://ec2-13-233-86-11.ap-south-1.compute.amazonaws.com",
]
CORS_ALLOW_ALL_ORIGINS = False
