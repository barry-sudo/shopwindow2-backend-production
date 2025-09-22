"""
URL configuration for shopwindow project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
import sys
import os
from django.conf import settings


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================

@require_http_methods(["GET"])
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def health_check(request):
    """
    Health check endpoint for Render deployment monitoring.
    
    Returns:
        JSON response with system status and database connectivity
    """
    try:
        # Test database connectivity
        from django.db import connection
        from django.core.cache import cache
        
        # Test database query
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_status = "connected"
        
        # Test PostGIS functionality
        try:
            cursor.execute("SELECT PostGIS_version()")
            postgis_status = "enabled"
        except Exception:
            postgis_status = "disabled"
        
        # System information
        response_data = {
            "status": "healthy",
            "database": db_status,
            "postgis": postgis_status,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "django_version": settings.DEBUG,  # Don't expose version in production
            "timestamp": str(timezone.now()) if 'timezone' in locals() else None,
        }
        
        return JsonResponse(response_data, status=200)
        
    except Exception as e:
        # Log error but don't expose details in production
        error_response = {
            "status": "unhealthy",
            "database": "error",
            "error": str(e) if settings.DEBUG else "Database connection failed"
        }
        return JsonResponse(error_response, status=503)


# =============================================================================
# API INFO ENDPOINT  
# =============================================================================

@require_http_methods(["GET"])
def api_info(request):
    """
    API information endpoint for frontend integration.
    
    Returns:
        JSON response with API version and available endpoints
    """
    api_info_data = {
        "api_name": "Shop Window API",
        "version": "1.0",
        "description": "Retail Commercial Real Estate Intelligence Platform",
        "endpoints": {
            "authentication": {
                "token_obtain": "/api/v1/auth/token/",
                "token_refresh": "/api/v1/auth/token/refresh/",
                "token_verify": "/api/v1/auth/token/verify/",
            },
            "shopping_centers": {
                "list_create": "/api/v1/shopping-centers/",
                "detail_update": "/api/v1/shopping-centers/{id}/",
                "tenants": "/api/v1/shopping-centers/{id}/tenants/",
                "map_bounds": "/api/v1/shopping-centers/map_bounds/",
            },
            "imports": {
                "csv_import": "/api/v1/imports/csv/",
                "pdf_import": "/api/v1/imports/pdf/",
                "batch_status": "/api/v1/imports/batches/{id}/",
            },
            "utilities": {
                "health": "/api/v1/health/",
                "geocode": "/api/v1/geocode/",
            }
        },
        "data_stats": {
            "total_centers": None,  # Will be populated by actual count
            "total_tenants": None,  # Will be populated by actual count
        }
    }
    
    # Add actual data counts if models are available
    try:
        from properties.models import ShoppingCenter, Tenant
        api_info_data["data_stats"]["total_centers"] = ShoppingCenter.objects.count()
        api_info_data["data_stats"]["total_tenants"] = Tenant.objects.count()
    except Exception:
        # Models not available or database not ready
        pass
    
    return JsonResponse(api_info_data)


# =============================================================================
# GEOCODING PROXY ENDPOINT
# =============================================================================

@require_http_methods(["POST"])
def geocode_address(request):
    """
    Geocoding proxy endpoint for frontend address validation.
    
    Proxies requests to Google Maps API to avoid exposing API key to frontend.
    """
    try:
        import json
        from services.geocoding import GeocodingService
        
        # Parse request data
        data = json.loads(request.body)
        address = data.get('address')
        
        if not address:
            return JsonResponse(
                {"error": "Address parameter required"}, 
                status=400
            )
        
        # Initialize geocoding service
        geocoding_service = GeocodingService()
        
        # Perform geocoding (implement basic geocoding without shopping center)
        try:
            import googlemaps
            gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
            geocode_result = gmaps.geocode(address)
            
            if geocode_result:
                location = geocode_result[0]['geometry']['location']
                formatted_address = geocode_result[0]['formatted_address']
                
                return JsonResponse({
                    "latitude": location['lat'],
                    "longitude": location['lng'],
                    "formatted_address": formatted_address,
                    "status": "success"
                })
            else:
                return JsonResponse({
                    "error": "Address not found",
                    "status": "not_found"
                }, status=404)
                
        except Exception as e:
            return JsonResponse({
                "error": "Geocoding service error",
                "status": "error"
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON data"}, 
            status=400
        )
    except Exception as e:
        return JsonResponse(
            {"error": "Internal server error"}, 
            status=500
        )


# =============================================================================
# MAIN URL PATTERNS
# =============================================================================

urlpatterns = [
    # Django Admin Interface
    path('admin/', admin.site.urls),
    
    # =============================================================================
    # API VERSION 1 - Main API Endpoints
    # =============================================================================
    
    # Health and System Status
    path('api/v1/health/', health_check, name='health-check'),
    path('api/v1/info/', api_info, name='api-info'),
    
    # Authentication Endpoints (JWT)
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Core Application Endpoints
    path('api/v1/shopping-centers/', include('properties.urls')),
    path('api/v1/imports/', include('imports.urls')),
    
    # Utility Endpoints
    path('api/v1/geocode/', geocode_address, name='geocode-proxy'),
    
    # =============================================================================
    # API ROOT - Default API Landing Page
    # =============================================================================
    
    path('api/v1/', api_info, name='api-root'),
    path('api/', api_info, name='api-default'),
]


# =============================================================================
# DEVELOPMENT URL PATTERNS
# =============================================================================

# Add development-specific URLs when DEBUG is enabled
if settings.DEBUG:
    from django.conf.urls.static import static
    from django.views.generic import TemplateView
    
    urlpatterns += [
        # Serve media files in development
        *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
        
        # Development API browser (Django REST Framework)
        path('', TemplateView.as_view(template_name='rest_framework/api.html'), name='api-browser'),
        
        # Django REST Framework browsable API
        path('api-auth/', include('rest_framework.urls')),
    ]


# =============================================================================
# CUSTOM ERROR HANDLERS
# =============================================================================

def custom_404_handler(request, exception):
    """Custom 404 handler for API endpoints"""
    if request.path.startswith('/api/'):
        return JsonResponse({
            'error': 'API endpoint not found',
            'message': f'The requested endpoint {request.path} does not exist',
            'available_endpoints': '/api/v1/info/'
        }, status=404)
    
    # Fall back to default 404 for non-API requests
    from django.views.defaults import page_not_found
    return page_not_found(request, exception)


def custom_500_handler(request):
    """Custom 500 handler for API endpoints"""
    if request.path.startswith('/api/'):
        return JsonResponse({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred',
            'contact': 'Please contact support if this error persists'
        }, status=500)
    
    # Fall back to default 500 for non-API requests  
    from django.views.defaults import server_error
    return server_error(request)


# Register custom error handlers
handler404 = custom_404_handler
handler500 = custom_500_handler


# =============================================================================
# URL PATTERN ORGANIZATION NOTES
# =============================================================================

"""
URL Structure Overview:
========================

/admin/                          - Django admin interface
/api/v1/health/                  - Health check for Render monitoring
/api/v1/info/                    - API information and documentation
/api/v1/auth/token/              - JWT token authentication
/api/v1/shopping-centers/        - Shopping center CRUD operations
/api/v1/shopping-centers/{id}/   - Individual shopping center details
/api/v1/shopping-centers/{id}/tenants/ - Tenant management
/api/v1/imports/                 - Data import endpoints
/api/v1/geocode/                 - Address geocoding proxy

Frontend Integration Notes:
==========================

1. All API endpoints are prefixed with /api/v1/
2. JWT authentication required for POST/PATCH/DELETE operations
3. CORS configured for localhost:3000 (React development)
4. Health check endpoint for deployment monitoring
5. Geocoding proxy prevents API key exposure to frontend
6. Error responses return consistent JSON format

Production Deployment:
=====================

1. Health check endpoint required by Render for deployment status
2. Static files served by WhiteNoise middleware
3. Database connectivity verified in health check
4. PostGIS functionality tested in health check
5. Error handlers provide JSON responses for API requests
"""
