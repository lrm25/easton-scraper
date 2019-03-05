from django.urls import path
from retriever.views import get_raw_data, get_select_page, get_checks

urlpatterns = [
    path('rawdata/', get_raw_data),
    path('select/', get_select_page),
    path('get-checks/', get_checks)
]
