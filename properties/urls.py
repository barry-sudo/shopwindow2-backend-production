"""
URL configuration for properties app.

This module defines the URL routing for shopping centers and tenants within the properties app.
Uses Django REST Framework's router system for automatic ViewSet URL generation with custom actions.

URL Structure Generated:
========================

Shopping Center Endpoints:
- /                                    - Shopping center list/create (GET, POST)
- /{id}/                              - Shopping center detail/update/delete (GET, PUT, PATCH, DELETE)
- /map_bounds/                        - Map integration endpoint (GET)
- /statistics/                        - Dashboard analytics (GET)
- /{id}/geocode/                      - Manual geocoding (POST)
- /{id}/nearby/                       - Spatial queries (GET)
- /{id}/tenants/                      - Tenant management for specific center (GET, POST)

Tenant Endpoints:
- /tenants/                           - All tenants list/create (GET, POST)
- /tenants/{id}/                      - Tenant detail/update/delete (GET, PUT, PATCH, DELETE)
- /tenants/chains/                    - Multi-location tenant analysis (GET)
- /tenants/categories/                - Retail category statistics (GET)

This URLs file gets included by the main project URLs at:
/api/v1/shopping-centers/ -> properties.urls

Full API paths will be:
/api/v1/shopping-centers/              -> ShoppingCenterViewSet
/api/v1/shopping-centers/tenants/      -> TenantViewSet
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ShoppingCenterViewSet, TenantViewSet


# =============================================================================
# ROUTER CONFIGURATION
# =============================================================================

# Create router for automatic URL generation
router = DefaultRouter()

# Register ViewSets with the router
# Note: ShoppingCenterViewSet is registered at root '' since this entire
# URL config gets included at /api/v1/shopping-centers/
router.register(r'', ShoppingCenterViewSet, basename='shopping-center')

# Register TenantViewSet at 'tenants' sub-path
# This creates URLs like /api/v1/shopping-centers/tenants/
router.register(r'tenants', TenantViewSet, basename='tenant')


# Router automatically generates these URL patterns:
#
# Shopping Center URLs (from ShoppingCenterViewSet at ''):
# ^$ [name='shopping-center-list']                     - GET (list), POST (create)
# ^(?P<pk>[^/.]+)/$ [name='shopping-center-detail']    - GET, PUT, PATCH, DELETE
#
# Custom Shopping Center Actions:
# ^map_bounds/$ [name='shopping-center-map-bounds']     - GET
# ^statistics/$ [name='shopping-center-statistics']    - GET
# ^(?P<pk>[^/.]+)/geocode/$ [name='shopping-center-geocode'] - POST
# ^(?P<pk>[^/.]+)/nearby/$ [name='shopping-center-nearby']   - GET
# ^(?P<pk>[^/.]+)/tenants/$ [name='shopping-center-tenants'] - GET, POST
#
# Tenant URLs (from TenantViewSet at 'tenants'):
# ^tenants/$ [name='tenant-list']                       - GET (list), POST (create)
# ^tenants/(?P<pk>[^/.]+)/$ [name='tenant-detail']      - GET, PUT, PATCH, DELETE
#
# Custom Tenant Actions:
# ^tenants/chains/$ [name='tenant-chains']              - GET
# ^tenants/categories/$ [name='tenant-categories']      - GET


# =============================================================================
# MAIN URL PATTERNS
# =============================================================================

urlpatterns = [
    # Include all router-generated URLs
    path('', include(router.urls)),
]

# Apply format suffix patterns for content negotiation
# Allows URLs like /api/v1/shopping-centers/1.json or /api/v1/shopping-centers/1.xml
urlpatterns = format_suffix_patterns(urlpatterns)


# =============================================================================
# URL PATTERN REFERENCE
# =============================================================================

"""
Complete Endpoint Reference:
============================

When this URLs file is included at /api/v1/shopping-centers/, 
the following endpoints become available:

SHOPPING CENTER ENDPOINTS:
--------------------------

1. List/Create Shopping Centers
   GET  /api/v1/shopping-centers/
   POST /api/v1/shopping-centers/
   
   Query Parameters for GET:
   - search: Search across name, city, owner, property manager
   - center_type: Filter by center type
   - address_city: Filter by city (exact or contains)
   - address_state: Filter by state
   - data_quality_score__gte: Minimum quality score
   - total_gla__gte / total_gla__lte: GLA range filtering
   - owner: Filter by owner (exact or contains)
   - property_manager: Filter by property manager
   - has_coordinates: true/false - filter geocoded centers
   - min_tenants: Minimum number of tenants
   - ordering: Sort by field (shopping_center_name, data_quality_score, total_gla)
   - page: Page number for pagination
   - page_size: Results per page (max 200)

2. Shopping Center Details
   GET    /api/v1/shopping-centers/{id}/
   PUT    /api/v1/shopping-centers/{id}/
   PATCH  /api/v1/shopping-centers/{id}/
   DELETE /api/v1/shopping-centers/{id}/

3. Map Integration
   GET /api/v1/shopping-centers/map_bounds/
   
   Required Query Parameters:
   - north: Northern latitude boundary
   - south: Southern latitude boundary
   - east: Eastern longitude boundary
   - west: Western longitude boundary
   
   Optional Query Parameters:
   - zoom_level: Map zoom level for result optimization (default: 10)

4. Dashboard Statistics
   GET /api/v1/shopping-centers/statistics/
   
   Returns:
   - Total counts (centers, tenants)
   - GLA statistics (total, average)
   - Quality score metrics
   - Centers by type breakdown
   - Top owners list
   - Recent additions count
   - Geocoding completion percentage

5. Manual Geocoding
   POST /api/v1/shopping-centers/{id}/geocode/
   
   Triggers geocoding for a specific shopping center.

6. Nearby Centers (Spatial Query)
   GET /api/v1/shopping-centers/{id}/nearby/
   
   Query Parameters:
   - radius: Search radius in kilometers (default: 10, max: 100)
   - limit: Maximum results (default: 20, max: 50)

7. Tenant Management for Specific Center
   GET  /api/v1/shopping-centers/{id}/tenants/
   POST /api/v1/shopping-centers/{id}/tenants/
   
   Query Parameters for GET:
   - retail_category: Filter by category
   - occupancy_status: Filter by status (OCCUPIED, VACANT, PENDING, UNKNOWN)
   - expiring_soon: true - show leases expiring within 12 months
   - ordering: Sort by tenant_name, tenant_suite_number, square_footage, base_rent


TENANT ENDPOINTS:
-----------------

1. List/Create Tenants (All Centers)
   GET  /api/v1/shopping-centers/tenants/
   POST /api/v1/shopping-centers/tenants/
   
   Query Parameters for GET:
   - search: Search across tenant name, shopping center, retail category
   - shopping_center: Filter by shopping center ID
   - occupancy_status: Filter by status
   - is_anchor: Filter anchor tenants (true/false)
   - ownership_type: Filter by ownership type
   - retail_category__contains: Filter by retail category
   - square_footage__gte / square_footage__lte: Size range filtering
   - base_rent__gte / base_rent__lte: Rent range filtering
   - lease_expiring: Number of months ahead to check for lease expiration
   - ordering: Sort by various fields

2. Tenant Details
   GET    /api/v1/shopping-centers/tenants/{id}/
   PUT    /api/v1/shopping-centers/tenants/{id}/
   PATCH  /api/v1/shopping-centers/tenants/{id}/
   DELETE /api/v1/shopping-centers/tenants/{id}/

3. Tenant Chain Analysis
   GET /api/v1/shopping-centers/tenants/chains/
   
   Returns tenants that appear in multiple shopping centers with:
   - Location count
   - Total square footage across all locations
   - Detailed location information

4. Retail Category Statistics
   GET /api/v1/shopping-centers/tenants/categories/
   
   Returns breakdown of tenants by retail category with:
   - Tenant count per category
   - Total square footage per category
   - Shopping center count per category


URL NAME REFERENCE:
===================

For Django reverse URL lookups:

Shopping Centers:
- 'shopping-center-list'
- 'shopping-center-detail'
- 'shopping-center-map-bounds'
- 'shopping-center-statistics'
- 'shopping-center-geocode'
- 'shopping-center-nearby'
- 'shopping-center-tenants'

Tenants:
- 'tenant-list'
- 'tenant-detail'
- 'tenant-chains'
- 'tenant-categories'

Usage:
from django.urls import reverse
url = reverse('shopping-center-detail', kwargs={'pk': 1})

Usage in DRF:
from rest_framework.reverse import reverse
url = reverse('shopping-center-list', request=request)


CONTENT NEGOTIATION:
====================

All endpoints support format suffixes:
- /api/v1/shopping-centers/1.json
- /api/v1/shopping-centers/1.xml
- /api/v1/shopping-centers/statistics.json

Default format: JSON
Accept header also supported: Accept: application/json
"""

# =============================================================================
# TESTING COMMANDS
# =============================================================================

"""
API Testing Commands:
=====================

# Test basic endpoints
curl http://localhost:8000/api/v1/shopping-centers/
curl http://localhost:8000/api/v1/shopping-centers/1/
curl http://localhost:8000/api/v1/shopping-centers/statistics/
curl http://localhost:8000/api/v1/shopping-centers/tenants/
curl http://localhost:8000/api/v1/shopping-centers/tenants/chains/

# Test filtering
curl "http://localhost:8000/api/v1/shopping-centers/?address_city=Chester"
curl "http://localhost:8000/api/v1/shopping-centers/tenants/?search=Starbucks"

# Test map bounds
curl "http://localhost:8000/api/v1/shopping-centers/map_bounds/?north=40.1&south=39.9&east=-75.0&west=-75.2"

# Test spatial queries
curl "http://localhost:8000/api/v1/shopping-centers/1/nearby/?radius=10"

# Test tenant management
curl "http://localhost:8000/api/v1/shopping-centers/1/tenants/?occupancy_status=OCCUPIED"

# Create shopping center (requires JWT token)
curl -X POST http://localhost:8000/api/v1/shopping-centers/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"shopping_center_name": "Test Plaza", "address_city": "Philadelphia"}'

# Create tenant (requires JWT token)
curl -X POST http://localhost:8000/api/v1/shopping-centers/1/tenants/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_name": "New Store", "tenant_suite_number": "A-1"}'
"""
