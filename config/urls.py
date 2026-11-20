"""
URL configuration for PUMO TECHNOVATION EXAM PORTAL - POONAMALLEE.
Developed By Team SAT
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

def root_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')
    return redirect('login')

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', root_redirect, name='root'),
    path('', include('accounts.urls')),
    path('', include('portal.urls')),
    path('', include('exams.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
