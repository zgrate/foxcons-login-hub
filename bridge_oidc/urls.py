from django.urls import path
from . import views

app_name = 'bridge_oidc'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('continue/', views.continue_view, name='continue'),
    path('logout/', views.logout_view, name='logout'),
]