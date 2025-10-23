"""
Amazon SP-API OAuth URL Configuration
"""
from django.urls import path
from .amazon_views import amazon_login, amazon_callback

urlpatterns = [
    path('login/', amazon_login, name='amazon_login'),
    path('callback/', amazon_callback, name='amazon_callback'),
]