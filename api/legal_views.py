"""
Legal Pages Views for Privacy Policy and Terms of Service
"""
from django.shortcuts import render
from django.http import HttpResponse

def privacy_policy(request):
    """Serve privacy policy page"""
    return render(request, 'privacy_policy.html')

def terms_of_service(request):
    """Serve terms of service page"""  
    return render(request, 'terms_of_service.html')

def about_page(request):
    """Serve company about page"""
    return render(request, 'about.html')