from django.urls import path
from retriever.views import get_raw_data, get_select_page, get_checks, retrieve_data

urlpatterns = [
    path('rawdata/', get_raw_data),
    path('select/', get_select_page),
    path('get-checks/', get_checks),
    path('retrieve/', retrieve_data)
]
