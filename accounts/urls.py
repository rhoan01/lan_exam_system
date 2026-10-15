from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.redirect_after_login, name='home'),
    path('register/', views.StudentRegisterView.as_view(), name='register'),
    path('login/', views.RoleAwareLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('redirect/', views.redirect_after_login, name='redirect_after_login'),
]
