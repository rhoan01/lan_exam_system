from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('instructor/', include('exams.urls')),
    path('student/', include('results.urls')),
    # The deployment is intentionally self-contained on the LAN. Uploaded
    # question images are therefore served by this WSGI application too.
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
