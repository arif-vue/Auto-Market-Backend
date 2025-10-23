"""
URL configuration for auto_market project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render

from api.views import api_test, ebay_test_page

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def about(request):
    return render(request, 'about.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentications.urls')),
    path('api/', include('api.urls')),
    path('api/test/', api_test, name='api_test'),
    path('test/', ebay_test_page, name='ebay_test_page'),
    path('amazon/', include('api.amazon_urls')),  # Amazon OAuth URLs
    path('api/amazon/', include('api.amazon_urls')),  # Amazon API callbacks
    path('privacy/', privacy_policy, name='privacy_policy'),
    path('privacy-policy/', privacy_policy, name='privacy_policy_amazon'),  # Amazon LWA compliance
    path('about/', about, name='about'),
]

# Serve static and media files during development
if settings.DEBUG:
    # Serve static files
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Serve media files
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
