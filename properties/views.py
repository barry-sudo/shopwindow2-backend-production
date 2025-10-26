"""
Views for the properties app.

This module defines the API viewsets for Shopping Centers and Tenants,
including filtering, search, and custom actions.

CHANGES (Oct 25, 2025):
- Added ShoppingCenterPagination class to explicitly enable page_size query parameter
- This fixes the issue where frontend requests for page_size=100 were being ignored
- Now respects ?page_size=X parameter up to MAX_PAGE_SIZE of 1000
- Corrected serializer import names to match actual serializers.py
"""

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q, Avg, Sum
from .models import ShoppingCenter, Tenant
from .serializers import (
    ShoppingCenterListSerializer,
    ShoppingCenterDetailSerializer,
    TenantListSerializer,
    TenantDetailSerializer
)
from .filters import ShoppingCenterFilter, TenantFilter


# =============================================================================
# CUSTOM PAGINATION CLASS
# =============================================================================

class ShoppingCenterPagination(PageNumberPagination):
    """
    Custom pagination class for Shopping Centers.
    
    Explicitly enables page_size query parameter to allow frontend
    to request variable page sizes (up to 1000 results).
    
    This fixes the issue where the global PAGE_SIZE_QUERY_PARAM setting
    wasn't being respected. By defining it directly on the pagination class,
    we ensure the ViewSet will honor ?page_size=X in the URL.
    
    Usage:
        GET /api/v1/shopping-centers/              → Returns 20 results (default)
        GET /api/v1/shopping-centers/?page_size=100 → Returns 100 results
        GET /api/v1/shopping-centers/?page_size=1000 → Returns 1000 results (max)
    """
    page_size = 20  # Default page size
    page_size_query_param = 'page_size'  # Allow client to override with ?page_size=X
    max_page_size = 1000  # Maximum allowed page size


# =============================================================================
# SHOPPING CENTER VIEWSET
# =============================================================================

class ShoppingCenterViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Shopping Centers.
    
    Supports:
    - List all shopping centers (with pagination)
    - Create new shopping center
    - Retrieve specific shopping center
    - Update shopping center
    - Delete shopping center
    - Filtering by type, owner, state, etc.
    - Search by name, address
    - Ordering by various fields
    - Custom actions for map bounds and data quality
    
    Pagination:
    - Default: 20 results per page
    - Customizable via ?page_size=X parameter (max 1000)
    """
    queryset = ShoppingCenter.objects.all()
    serializer_class = ShoppingCenterListSerializer
    pagination_class = ShoppingCenterPagination  # Custom pagination with page_size support
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ShoppingCenterFilter
    
    # Search configuration
    search_fields = [
        'shopping_center_name',
        'address_street',
        'address_city',
        'address_state',
        'owner',
        'property_manager'
    ]
    
    # Ordering configuration
    ordering_fields = [
        'shopping_center_name',
        'address_city',
        'address_state',
        'total_gla',
        'year_built',
        'created_at',
        'updated_at'
    ]
    ordering = ['shopping_center_name']  # Default ordering
    
    def get_serializer_class(self):
        """
        Use detailed serializer for retrieve actions, standard serializer for list.
        This optimizes performance by not loading nested tenant data in list view.
        """
        if self.action == 'retrieve':
            return ShoppingCenterDetailSerializer
        return ShoppingCenterListSerializer
    
    def get_queryset(self):
        """
        Optionally filter queryset based on query parameters.
        Optimizes queries by selecting related data when needed.
        """
        queryset = ShoppingCenter.objects.all()
        
        # For detail views, prefetch related tenants
        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('tenants')
        
        # Add annotations for computed fields if needed
        if self.action in ['list', 'retrieve']:
            queryset = queryset.annotate(
                tenant_count=Count('tenants'),
                occupied_tenant_count=Count('tenants', filter=Q(tenants__tenant_name__isnull=False))
            )
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def map_bounds(self, request):
        """
        Custom action to return geographic bounds for map initialization.
        
        Returns the min/max latitude and longitude for all shopping centers,
        useful for automatically setting map zoom and center.
        
        GET /api/v1/shopping-centers/map_bounds/
        
        Response:
        {
            "north": 40.1234,
            "south": 39.5678,
            "east": -75.1234,
            "west": -75.9876,
            "center": {
                "lat": 39.8456,
                "lng": -75.5555
            }
        }
        """
        from django.db.models import Max, Min
        
        bounds = ShoppingCenter.objects.aggregate(
            north=Max('latitude'),
            south=Min('latitude'),
            east=Max('longitude'),
            west=Min('longitude')
        )
        
        # Calculate center point
        if all(bounds.values()):
            center = {
                'lat': (float(bounds['north']) + float(bounds['south'])) / 2,
                'lng': (float(bounds['east']) + float(bounds['west'])) / 2
            }
            bounds['center'] = center
        
        return Response(bounds)
    
    @action(detail=False, methods=['get'])
    def data_quality(self, request):
        """
        Custom action to return data quality metrics.
        
        Provides statistics on data completeness for all shopping centers:
        - Total centers
        - Percentage with complete addresses
        - Percentage with GLA data
        - Percentage with tenant data
        - Percentage geocoded
        
        GET /api/v1/shopping-centers/data_quality/
        
        Response:
        {
            "total_centers": 55,
            "data_completeness": {
                "complete_addresses": {
                    "count": 45,
                    "percentage": 81.8
                },
                "has_gla_data": {
                    "count": 50,
                    "percentage": 90.9
                },
                ...
            }
        }
        """
        total = ShoppingCenter.objects.count()
        
        metrics = {
            'total_centers': total,
            'data_completeness': {
                'complete_addresses': {
                    'count': ShoppingCenter.objects.filter(
                        address_street__isnull=False,
                        address_city__isnull=False,
                        address_state__isnull=False
                    ).count(),
                    'percentage': 0
                },
                'has_gla_data': {
                    'count': ShoppingCenter.objects.filter(
                        total_gla__isnull=False
                    ).count(),
                    'percentage': 0
                },
                'has_tenant_data': {
                    'count': ShoppingCenter.objects.annotate(
                        tenant_count=Count('tenants')
                    ).filter(tenant_count__gt=0).count(),
                    'percentage': 0
                },
                'has_coordinates': {
                    'count': ShoppingCenter.objects.filter(
                        latitude__isnull=False,
                        longitude__isnull=False
                    ).count(),
                    'percentage': 0
                }
            }
        }
        
        # Calculate percentages
        if total > 0:
            for category in metrics['data_completeness'].values():
                category['percentage'] = round((category['count'] / total) * 100, 1)
        
        return Response(metrics)


# =============================================================================
# TENANT VIEWSET
# =============================================================================

class TenantViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Tenants.
    
    Supports:
    - List all tenants
    - Create new tenant
    - Retrieve specific tenant
    - Update tenant
    - Delete tenant
    - Filtering by shopping center, category, lease status
    - Search by name
    - Ordering by various fields
    """
    queryset = Tenant.objects.all()
    serializer_class = TenantListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TenantFilter
    
    # Search configuration
    search_fields = [
        'tenant_name',
        'tenant_suite_number',
        'retail_category',
        'major_group'
    ]
    
    # Ordering configuration
    ordering_fields = [
        'tenant_name',
        'square_footage',
        'base_rent',
        'lease_expiration',
        'created_at'
    ]
    ordering = ['tenant_name']  # Default ordering
    
    def get_serializer_class(self):
        """
        Use detailed serializer for retrieve actions.
        """
        if self.action == 'retrieve':
            return TenantDetailSerializer
        return TenantListSerializer
    
    def get_queryset(self):
        """
        Optionally filter queryset by shopping center if provided in URL.
        
        Supports:
        - /api/v1/tenants/ → All tenants
        - /api/v1/shopping-centers/{id}/tenants/ → Tenants for specific center
        """
        queryset = Tenant.objects.select_related('shopping_center')
        
        # Filter by shopping center if provided in URL kwargs
        shopping_center_id = self.kwargs.get('shopping_center_id')
        if shopping_center_id:
            queryset = queryset.filter(shopping_center_id=shopping_center_id)
        
        return queryset


# =============================================================================
# CSV UPLOAD FUNCTION (Placeholder for urls.py import)
# =============================================================================

@api_view(['POST'])
def upload_csv(request):
    """
    CSV upload endpoint.
    
    This is a placeholder function that returns HTTP 501 Not Implemented.
    The actual CSV import is handled via Django management command:
        python manage.py import_csv_simple path/to/file.csv
    
    POST /api/v1/shopping-centers/upload_csv/
    
    Future implementation will handle:
    - File validation
    - CSV parsing
    - Property creation/update
    - Automatic geocoding
    - Tenant import
    """
    return Response(
        {
            'error': 'CSV upload via API not yet implemented',
            'message': 'Please use the management command: python manage.py import_csv_simple <file>',
            'status': 'not_implemented'
        },
        status=status.HTTP_501_NOT_IMPLEMENTED
    )


# =============================================================================
# NOTES ON PAGINATION
# =============================================================================

"""
Pagination Configuration:
========================

The ShoppingCenterPagination class explicitly enables the page_size query
parameter, which allows the frontend to request different page sizes.

Before this change:
- Frontend requested ?page_size=100
- Backend ignored it and returned default 20 results
- Map showed only 20 of 55 properties

After this change:
- Frontend requests ?page_size=100
- Backend returns all 55 results
- Map displays all 55 properties

The key fix was adding page_size_query_param to the pagination class.
The global REST_FRAMEWORK settings alone weren't sufficient due to a
Django REST Framework quirk where PAGE_SIZE_QUERY_PARAM doesn't always
work as expected without explicit pagination class configuration.

Testing:
--------
curl "http://localhost:8000/api/v1/shopping-centers/" 
  → Returns 20 results (default)

curl "http://localhost:8000/api/v1/shopping-centers/?page_size=100" 
  → Returns 55 results (all properties)

curl "http://localhost:8000/api/v1/shopping-centers/?page_size=1000" 
  → Returns 55 results (capped at total available)
"""
