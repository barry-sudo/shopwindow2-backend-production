# ===== IMPORTS APP URL CONFIGURATION =====
"""
URL routing for the imports app - handles CSV import API endpoints
File: imports/urls.py

This module defines the URL patterns for import-related functionality:
- Import batch management
- CSV file upload and processing
- Import status monitoring
- Import history and logging
- Admin tools for import management

Business Logic:
- Supports the "Stocking Shelves" data philosophy
- Handles rolling CSV imports with conflict resolution
- Tracks import quality scores and validation
- Provides comprehensive import management tools
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# =============================================================================
# DRF ROUTER CONFIGURATION
# =============================================================================

# Create router for ViewSet-based endpoints
router = DefaultRouter()
router.register(r'batches', views.ImportBatchViewSet, basename='importbatch')

# =============================================================================
# URL PATTERNS
# =============================================================================

urlpatterns = [
    # =============================================================================
    # IMPORT BATCH MANAGEMENT
    # =============================================================================
    
    # DRF ViewSet routes (automatically generated)
    # GET/POST /api/v1/imports/batches/ - List and create import batches
    # GET/PUT/PATCH/DELETE /api/v1/imports/batches/{id}/ - Individual batch operations
    # GET /api/v1/imports/batches/{id}/status/ - Import batch status (custom action)
    # GET /api/v1/imports/batches/{id}/quality/ - Quality report (custom action) 
    # POST /api/v1/imports/batches/{id}/retry/ - Retry failed import (custom action)
    path('', include(router.urls)),
    
    # =============================================================================
    # CSV UPLOAD AND PROCESSING
    # =============================================================================
    
    # CSV file upload endpoint
    path('upload/csv/', views.CSVUploadView.as_view(), name='csv-upload'),
    # POST /api/v1/imports/upload/csv/
    # Content-Type: multipart/form-data
    # Body: file (CSV file), import_type (optional), notes (optional)
    # Returns: {"import_batch_id": 123, "status": "processing", "message": "Upload successful"}
    
    # =============================================================================
    # CSV VALIDATION AND TEMPLATES
    # =============================================================================
    
    # CSV structure validation endpoint
    path('validate/csv/', views.CSVValidationView.as_view(), name='csv-validate'),
    # POST /api/v1/imports/validate/csv/
    # Content-Type: multipart/form-data
    # Body: file (CSV file to validate)
    # Returns: {"valid": true, "headers": [...], "row_count": 150, "message": "Valid"}
    
    # Download CSV template with proper headers
    path('template/csv/', views.CSVTemplateView.as_view(), name='csv-template'),
    # GET /api/v1/imports/template/csv/
    # Returns: CSV file download with sample data and proper headers
    # Content-Disposition: attachment; filename="shop_window_import_template.csv"
    
    # =============================================================================
    # IMPORT STATUS AND MONITORING
    # =============================================================================
    
    # Import batch status by batch ID
    path('batches/<int:batch_id>/status/', views.ImportStatusView.as_view(), name='import-status'),
    # GET /api/v1/imports/batches/123/status/
    # Returns: {"status": "completed", "records_processed": 150, "progress_percentage": 100}
    
    # Import statistics dashboard
    path('stats/', views.ImportStatsView.as_view(), name='import-stats'),
    # GET /api/v1/imports/stats/
    # Query params: date_from, date_to (ISO format)
    # Returns: {"summary": {...}, "status_distribution": {...}, "recent_activity": [...]}
    
    # Recent import activity
    path('recent/', views.RecentImportsView.as_view(), name='recent-imports'),
    # GET /api/v1/imports/recent/
    # Query params: limit (default: 20, max: 100)
    # Returns: {"count": 10, "results": [...]}
    
    # =============================================================================
    # ADMIN AND MAINTENANCE
    # =============================================================================
    
    # Load sample data (admin only)
    path('sample-data/load/', views.LoadSampleDataView.as_view(), name='load-sample-data'),
    # POST /api/v1/imports/sample-data/load/
    # Permissions: Admin users only
    # Returns: {"message": "Sample data loaded", "import_batch_id": 123}
    
    # Clear import data (admin only)
    path('admin/clear/', views.ClearImportsView.as_view(), name='clear-imports'),
    # DELETE /api/v1/imports/admin/clear/
    # Query params: days_old (default: 30), status (optional filter)
    # Permissions: Admin users only
    # Returns: {"message": "Cleared X imports", "deleted_count": X}
]

# =============================================================================
# URL PATTERN DOCUMENTATION
# =============================================================================

"""
Import API Endpoints Summary:
=============================

Core Import Operations:
-----------------------
POST /api/v1/imports/upload/csv/
  - Upload CSV file for processing
  - Body: multipart/form-data with 'file', optional 'import_type' and 'notes'
  - Returns: Import batch ID and processing status
  - Authentication: Required
  - File validation: CSV only, max size configurable

GET /api/v1/imports/batches/
  - List all import batches with filtering
  - Query params: status, import_type, date_from, date_to, min_quality, max_quality
  - Returns: Paginated list of import batches
  - Authentication: Required

POST /api/v1/imports/batches/
  - Create new import batch manually
  - Body: JSON with batch details
  - Returns: Created import batch
  - Authentication: Required

GET /api/v1/imports/batches/{id}/
  - Get specific import batch details
  - Returns: Complete import batch information
  - Authentication: Required

PATCH /api/v1/imports/batches/{id}/
  - Update import batch (notes, status, etc.)
  - Body: JSON with fields to update
  - Returns: Updated import batch
  - Authentication: Required

DELETE /api/v1/imports/batches/{id}/
  - Delete import batch
  - Returns: 204 No Content on success
  - Authentication: Required

Status and Quality Monitoring:
------------------------------
GET /api/v1/imports/batches/{id}/status/
  - Get detailed processing status
  - Returns: Status, progress, timing information
  - Authentication: Required

GET /api/v1/imports/batches/{id}/quality/
  - Get quality report and validation results
  - Returns: Quality score, errors, warnings
  - Authentication: Required

POST /api/v1/imports/batches/{id}/retry/
  - Retry failed import batch
  - Returns: Confirmation message and new status
  - Authentication: Required
  - Restriction: Only works for failed imports

Validation and Templates:
-------------------------
POST /api/v1/imports/validate/csv/
  - Validate CSV structure without processing
  - Body: multipart/form-data with CSV file
  - Returns: Validation results, headers, row count
  - Authentication: Required

GET /api/v1/imports/template/csv/
  - Download CSV template file
  - Returns: CSV file with sample data and proper headers
  - Content-Type: text/csv
  - Authentication: Required

Analytics and Reporting:
------------------------
GET /api/v1/imports/stats/
  - Import statistics dashboard
  - Query params: date_from, date_to (ISO format)
  - Returns: Summary stats, status distribution, recent activity
  - Default range: Last 30 days
  - Authentication: Required

GET /api/v1/imports/recent/
  - Recent import activity feed
  - Query params: limit (1-100, default: 20)
  - Returns: List of recent import batches
  - Authentication: Required

Admin Operations:
-----------------
POST /api/v1/imports/sample-data/load/
  - Load sample property data for testing
  - Returns: Import batch ID and processing results
  - Permissions: Admin users only
  - Use case: Development and testing

DELETE /api/v1/imports/admin/clear/
  - Clear old import batches
  - Query params: days_old (default: 30), status (optional)
  - Returns: Count of deleted batches
  - Permissions: Admin users only
  - Use case: Database maintenance

Authentication and Permissions:
-------------------------------
- All endpoints require user authentication (IsAuthenticated)
- Admin endpoints require admin privileges (IsAdminUser)
- JWT tokens are handled by Django REST framework authentication
- CORS configured for frontend integration

Query Parameter Examples:
-------------------------
# Filter by status
GET /api/v1/imports/batches/?status=completed

# Filter by date range
GET /api/v1/imports/batches/?date_from=2024-01-01T00:00:00Z&date_to=2024-01-31T23:59:59Z

# Filter by quality score
GET /api/v1/imports/batches/?min_quality=80&max_quality=100

# Multiple filters combined
GET /api/v1/imports/batches/?status=completed&min_quality=90&date_from=2024-01-01T00:00:00Z

# Limit recent imports
GET /api/v1/imports/recent/?limit=50

# Statistics for specific date range
GET /api/v1/imports/stats/?date_from=2024-01-01T00:00:00Z&date_to=2024-01-31T23:59:59Z

Error Handling:
---------------
- 400 Bad Request: Invalid parameters, file validation errors
- 401 Unauthorized: Authentication required
- 403 Forbidden: Admin permissions required
- 404 Not Found: Import batch not found
- 413 Payload Too Large: File size exceeds limit
- 415 Unsupported Media Type: Non-CSV file uploaded
- 500 Internal Server Error: Processing failures, system errors

Response Formats:
-----------------
Success responses return JSON with relevant data and HTTP 2xx status codes.
Error responses return JSON with error messages and appropriate HTTP status codes.

All datetime fields are returned in ISO 8601 format with timezone information.
File uploads use multipart/form-data encoding.
All other requests use application/json content type.

Integration Points:
-------------------
- Frontend: React components can use these endpoints for import workflows
- Admin Interface: Django admin uses these endpoints for import management
- Services Layer: imports/services.py handles the business logic
- Properties App: Created shopping centers and tenants are accessible via properties app
- Authentication: Integrates with Django's user authentication system
"""
