from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.portal_login, name='login'),
    path('logout/', views.portal_logout, name='logout'),
    path('redirect/', views.dashboard_redirect, name='dashboard_redirect'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
]
