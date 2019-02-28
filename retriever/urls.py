from django.urls import path
from retriever.views import get_raw_data

urlpatterns = [
    path('rawdata/', get_raw_data)
]
