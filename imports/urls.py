"""
URL configuration for imports app.

Endpoints:
    POST /api/v1/imports/csv/     - Upload and process CSV file
    POST /api/v1/imports/pdf/     - Upload and process PDF file (not implemented)
    GET  /api/v1/imports/status/  - Get import system status
"""

from django.urls import path
from . import views

urlpatterns = [
    # CSV Import
    path('csv/', views.upload_csv, name='upload-csv'),
    
    # PDF Import (not yet implemented)
    path('pdf/', views.upload_pdf, name='upload-pdf'),
    
    # Import Status
    path('status/', views.import_status, name='import-status'),
]
