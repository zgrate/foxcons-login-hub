from django.urls import path
from . import views

app_name = 'bridge_oidc'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('continue/', views.continue_view, name='continue'),
    path('logout/', views.logout_view, name='logout'),
    path('email-code/', views.email_code_request_view, name='email_code_request'),
    path('email-code/verify/', views.email_code_verify_view, name='email_code_verify'),
]