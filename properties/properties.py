"""
API Views for Shop Window Properties.

This module implements the REST API endpoints for shopping centers and tenants.
Provides comprehensive CRUD operations, filtering, search, and specialized endpoints
for map integration and business analytics.

Key Features:
- RESTful API with standard HTTP methods
- Advanced filtering and search capabilities
- Spatial queries for map-based interfaces
- Business logic integration (geocoding, quality scoring)
- Performance optimization with query optimization
- Comprehensive error handling and validation
- Progressive data enrichment support
"""

from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum, Prefetch
from django.contrib.gis.measure import D
from django.contrib.gis.geos import Point, Polygon
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.http import JsonResponse
import logging
from decimal import Decimal
from datetime import datetime, date

from .models import ShoppingCenter, Tenant
from .serializers import (
    ShoppingCenterListSerializer,
    ShoppingCenterDetailSerializer,
    ShoppingCenterCreateSerializer,
    ShoppingCenterUpdateSerializer,
    ShoppingCenterMapSerializer,
    TenantListSerializer,
    TenantDetailSerializer,
    TenantCreateSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM PAGINATION
# =============================================================================

class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for API responses."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class MapResultsSetPagination(PageNumberPagination):
    """High-performance pagination for map queries."""
    page_size = 500
    page_size_query_param = 'page_size'
    max_page_size = 1000


# =============================================================================
# SHOPPING CENTER VIEWSET
# =============================================================================

class ShoppingCenterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for shopping center CRUD operations.
    
    Provides:
    - Standard CRUD operations (list, create, retrieve, update, destroy)
    - Advanced filtering by multiple criteria
    - Search functionality across multiple fields
    - Spatial queries for map integration
    - Business logic integration
    - Performance optimizations
    """
    
    queryset = ShoppingCenter.objects.all().select_related('import_batch').prefetch_related(
        Prefetch('tenants', queryset=Tenant.objects.select_related())
    )
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Search configuration
    search_fields = [
        'shopping_center_name',
        'address_city',
        'address_state',
        'owner',
        'property_manager'
    ]
    
    # Ordering configuration
    ordering_fields = [
        'shopping_center_name',
        'data_quality_score',
        'total_gla',
        'created_at',
        'updated_at'
    ]
    ordering = ['shopping_center_name']
    
    # Filtering configuration
    filterset_fields = {
        'center_type': ['exact', 'in'],
        'address_city': ['exact', 'icontains'],
        'address_state': ['exact', 'in'],
        'data_quality_score': ['gte', 'lte', 'range'],
        'total_gla': ['gte', 'lte', 'range'],
        'owner': ['exact', 'icontains'],
        'property_manager': ['exact', 'icontains'],
    }
    
    def get_permissions(self):
        """
        Instantiate and return the list of permissions required for this view.
        
        Read operations are allowed for authenticated users.
        Write operations require additional permissions.
        """
        if self.action in ['list', 'retrieve', 'map_bounds', 'statistics']:
            permission_classes = [permissions.IsAuthenticatedOrReadOnly]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        """Return the appropriate serializer class based on the action."""
        if self.action == 'list':
            return ShoppingCenterListSerializer
        elif self.action == 'create':
            return ShoppingCenterCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ShoppingCenterUpdateSerializer
        elif self.action == 'map_bounds':
            return ShoppingCenterMapSerializer
        else:
            return ShoppingCenterDetailSerializer
    
    def get_queryset(self):
        """
        Customize queryset based on query parameters.
        
        Supports advanced filtering for business use cases.
        """
        queryset = self.queryset
        
        # Filter by GLA range
        min_gla = self.request.query_params.get('min_gla')
        max_gla = self.request.query_params.get('max_gla')
        
        if min_gla:
            try:
                queryset = queryset.filter(total_gla__gte=int(min_gla))
            except ValueError:
                pass
        
        if max_gla:
            try:
                queryset = queryset.filter(total_gla__lte=int(max_gla))
            except ValueError:
                pass
        
        # Filter by quality score
        quality_score_min = self.request.query_params.get('quality_score_min')
        if quality_score_min:
            try:
                queryset = queryset.filter(data_quality_score__gte=int(quality_score_min))
            except ValueError:
                pass
        
        # Filter by coordinates (has been geocoded)
        has_coordinates = self.request.query_params.get('has_coordinates')
        if has_coordinates and has_coordinates.lower() == 'true':
            queryset = queryset.exclude(latitude__isnull=True, longitude__isnull=True)
        elif has_coordinates and has_coordinates.lower() == 'false':
            queryset = queryset.filter(latitude__isnull=True, longitude__isnull=True)
        
        # Filter by tenant count
        min_tenants = self.request.query_params.get('min_tenants')
        if min_tenants:
            try:
                queryset = queryset.annotate(
                    tenant_count=Count('tenants')
                ).filter(tenant_count__gte=int(min_tenants))
            except ValueError:
                pass
        
        # Filter by vacancy rate
        max_vacancy_rate = self.request.query_params.get('max_vacancy_rate')
        if max_vacancy_rate:
            try:
                # This is a more complex query - would need custom SQL for accurate calculation
                # For now, we'll implement a simpler version
                pass
            except ValueError:
                pass
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Custom create logic with geocoding integration.
        
        Automatically geocodes new shopping centers and triggers
        business logic calculations.
        """
        shopping_center = serializer.save()
        
        # Trigger geocoding if address provided and coordinates not manually set
        if (shopping_center.address_street and 
            not shopping_center.latitude and 
            not shopping_center.longitude):
            
            try:
                from services.geocoding import GeocodingService
                geocoding_service = GeocodingService()
                result = geocoding_service.geocode_shopping_center(shopping_center)
                
                if result:
                    logger.info(f"Successfully geocoded {shopping_center.shopping_center_name}")
                else:
                    logger.warning(f"Failed to geocode {shopping_center.shopping_center_name}")
                    
            except Exception as e:
                logger.error(f"Geocoding error for {shopping_center.shopping_center_name}: {str(e)}")
        
        return shopping_center
    
    def perform_update(self, serializer):
        """
        Custom update logic with progressive data enrichment.
        
        Re-geocodes if address fields are updated and preserves existing data quality.
        """
        # Get the original instance to compare changes
        original_instance = self.get_object()
        
        # Check if address fields are being updated
        address_fields = ['address_street', 'address_city', 'address_state', 'address_zip']
        address_updated = any(
            field in serializer.validated_data and
            getattr(original_instance, field) != serializer.validated_data[field]
            for field in address_fields
        )
        
        # Save the updated instance
        shopping_center = serializer.save()
        
        # Re-geocode if address was updated
        if address_updated:
            try:
                from services.geocoding import GeocodingService
                geocoding_service = GeocodingService()
                result = geocoding_service.geocode_shopping_center(shopping_center)
                
                if result:
                    logger.info(f"Re-geocoded {shopping_center.shopping_center_name} after address update")
                    
            except Exception as e:
                logger.error(f"Re-geocoding error for {shopping_center.shopping_center_name}: {str(e)}")
        
        return shopping_center
    
    # ==========================================================================
    # CUSTOM ACTIONS
    # ==========================================================================
    
    @action(detail=False, methods=['get'])
    def map_bounds(self, request):
        """
        Get shopping centers within specified map bounds.
        
        Query parameters:
        - north, south, east, west: Bounding box coordinates
        - zoom_level: Optional zoom level for clustering logic
        
        Returns optimized data for map marker display.
        """
        try:
            north = float(request.query_params.get('north'))
            south = float(request.query_params.get('south'))
            east = float(request.query_params.get('east'))
            west = float(request.query_params.get('west'))
            zoom_level = request.query_params.get('zoom_level', 10)
            
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid bounds parameters. Required: north, south, east, west (as numbers)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate bounds
        if not (-90 <= south < north <= 90) or not (-180 <= west < east <= 180):
            return Response(
                {'error': 'Invalid coordinate bounds'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Query shopping centers within bounds
        queryset = ShoppingCenter.objects.filter(
            latitude__gte=south,
            latitude__lte=north,
            longitude__gte=west,
            longitude__lte=east
        ).exclude(
            latitude__isnull=True,
            longitude__isnull=True
        ).select_related('import_batch')
        
        # Apply additional filters from query params
        queryset = self.filter_queryset(queryset)
        
        # Limit results based on zoom level for performance
        try:
            zoom_level = int(zoom_level)
            if zoom_level <= 8:
                max_results = 100
            elif zoom_level <= 12:
                max_results = 500
            else:
                max_results = 1000
        except ValueError:
            max_results = 500
        
        # Limit queryset size
        queryset = queryset[:max_results]
        
        # Serialize with map-optimized serializer
        serializer = ShoppingCenterMapSerializer(queryset, many=True)
        
        return Response({
            'results': serializer.data,
            'count': len(serializer.data),
            'bounds': {
                'north': north,
                'south': south,
                'east': east,
                'west': west
            }
        })
    
    @action(detail=True, methods=['get', 'post'])
    def tenants(self, request, pk=None):
        """
        Manage tenants for a specific shopping center.
        
        GET: List all tenants for the shopping center
        POST: Add a new tenant to the shopping center
        """
        shopping_center = self.get_object()
        
        if request.method == 'GET':
            # Get tenants with filtering
            tenants = shopping_center.tenants.all()
            
            # Filter by retail category
            category = request.query_params.get('retail_category')
            if category:
                tenants = tenants.filter(retail_category__contains=[category])
            
            # Filter by occupancy status
            occupancy_status = request.query_params.get('occupancy_status')
            if occupancy_status:
                tenants = tenants.filter(occupancy_status=occupancy_status)
            
            # Filter by lease expiration
            expiring_soon = request.query_params.get('expiring_soon')
            if expiring_soon and expiring_soon.lower() == 'true':
                from datetime import date
                from dateutil.relativedelta import relativedelta
                warning_date = date.today() + relativedelta(months=12)
                tenants = tenants.filter(
                    lease_expiration__lte=warning_date,
                    lease_expiration__gte=date.today()
                )
            
            # Apply ordering
            ordering = request.query_params.get('ordering', 'tenant_suite_number')
            if ordering in ['tenant_name', 'tenant_suite_number', 'square_footage', 'base_rent']:
                tenants = tenants.order_by(ordering)
            
            # Paginate results
            page = self.paginate_queryset(tenants)
            if page is not None:
                serializer = TenantListSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = TenantListSerializer(tenants, many=True)
            return Response(serializer.data)
        
        elif request.method == 'POST':
            # Create new tenant
            serializer = TenantCreateSerializer(data=request.data)
            if serializer.is_valid():
                tenant = serializer.save(shopping_center=shopping_center)
                
                # Return created tenant with detail serializer
                detail_serializer = TenantDetailSerializer(tenant)
                return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes
    def statistics(self, request):
        """
        Get aggregated statistics about shopping centers.
        
        Returns dashboard-ready statistics for analytics.
        """
        try:
            # Basic counts
            total_centers = ShoppingCenter.objects.count()
            total_tenants = Tenant.objects.count()
            
            # Quality metrics
            avg_quality_score = ShoppingCenter.objects.aggregate(
                avg_score=Avg('data_quality_score')
            )['avg_score'] or 0
            
            # GLA statistics
            gla_stats = ShoppingCenter.objects.filter(
                total_gla__isnull=False
            ).aggregate(
                total_gla=Sum('total_gla'),
                avg_gla=Avg('total_gla')
            )
            
            # Centers by type
            centers_by_type = dict(
                ShoppingCenter.objects.filter(
                    center_type__isnull=False
                ).values_list('center_type').annotate(
                    count=Count('center_type')
                )
            )
            
            # Top owners
            top_owners = list(
                ShoppingCenter.objects.filter(
                    owner__isnull=False
                ).values('owner').annotate(
                    count=Count('id')
                ).order_by('-count')[:10]
            )
            
            # Geocoding statistics
            geocoded_count = ShoppingCenter.objects.exclude(
                latitude__isnull=True,
                longitude__isnull=True
            ).count()
            geocoded_percentage = (geocoded_count / total_centers * 100) if total_centers > 0 else 0
            
            # Recent additions (last 30 days)
            from datetime import date, timedelta
            thirty_days_ago = date.today() - timedelta(days=30)
            recent_additions = ShoppingCenter.objects.filter(
                created_at__date__gte=thirty_days_ago
            ).count()
            
            return Response({
                'total_shopping_centers': total_centers,
                'total_tenants': total_tenants,
                'total_gla': gla_stats.get('total_gla') or 0,
                'average_gla': round(gla_stats.get('avg_gla') or 0),
                'average_quality_score': round(avg_quality_score, 1),
                'centers_by_type': centers_by_type,
                'top_owners': top_owners,
                'recent_additions': recent_additions,
                'geocoded_percentage': round(geocoded_percentage, 1),
                'generated_at': datetime.now().isoformat(),
            })
            
        except Exception as e:
            logger.error(f"Error generating statistics: {str(e)}")
            return Response(
                {'error': 'Failed to generate statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def geocode(self, request, pk=None):
        """
        Manually trigger geocoding for a specific shopping center.
        
        Useful for re-geocoding after address updates or initial geocoding failures.
        """
        shopping_center = self.get_object()
        
        try:
            from services.geocoding import GeocodingService
            geocoding_service = GeocodingService()
            result = geocoding_service.geocode_shopping_center(shopping_center)
            
            if result:
                return Response({
                    'success': True,
                    'message': 'Shopping center successfully geocoded',
                    'coordinates': {
                        'latitude': float(shopping_center.latitude),
                        'longitude': float(shopping_center.longitude)
                    }
                })
            else:
                return Response({
                    'success': False,
                    'message': 'Geocoding failed - address may be invalid or incomplete'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Manual geocoding error for {shopping_center.shopping_center_name}: {str(e)}")
            return Response({
                'success': False,
                'message': 'Geocoding service error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def nearby(self, request, pk=None):
        """
        Find shopping centers near the specified center.
        
        Query parameters:
        - radius: Search radius in kilometers (default: 10)
        - limit: Maximum number of results (default: 20)
        """
        shopping_center = self.get_object()
        
        # Check if center has coordinates
        if not shopping_center.latitude or not shopping_center.longitude:
            return Response({
                'error': 'Shopping center must be geocoded to find nearby centers'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            radius = float(request.query_params.get('radius', 10))  # km
            limit = int(request.query_params.get('limit', 20))
            
            # Validate parameters
            if radius <= 0 or radius > 100:
                radius = 10
            if limit <= 0 or limit > 50:
                limit = 20
            
        except ValueError:
            radius = 10
            limit = 20
        
        # Create point from shopping center coordinates
        center_point = Point(float(shopping_center.longitude), float(shopping_center.latitude))
        
        # Find nearby shopping centers using PostGIS
        nearby_centers = ShoppingCenter.objects.filter(
            location__distance_lte=(center_point, D(km=radius))
        ).exclude(
            id=shopping_center.id
        ).exclude(
            latitude__isnull=True,
            longitude__isnull=True
        ).order_by(
            'location__distance'
        )[:limit]
        
        serializer = ShoppingCenterListSerializer(nearby_centers, many=True)
        
        return Response({
            'center': shopping_center.shopping_center_name,
            'search_radius_km': radius,
            'nearby_centers': serializer.data,
            'count': len(serializer.data)
        })


# =============================================================================
# TENANT VIEWSET
# =============================================================================

class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for tenant CRUD operations.
    
    Provides comprehensive tenant management with filtering and search.
    """
    
    queryset = Tenant.objects.all().select_related('shopping_center')
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Search configuration
    search_fields = [
        'tenant_name',
        'shopping_center__shopping_center_name',
        'retail_category'
    ]
    
    # Ordering configuration
    ordering_fields = [
        'tenant_name',
        'shopping_center__shopping_center_name',
        'square_footage',
        'base_rent',
        'lease_expiration'
    ]
    ordering = ['shopping_center__shopping_center_name', 'tenant_suite_number']
    
    # Filtering configuration
    filterset_fields = {
        'occupancy_status': ['exact', 'in'],
        'is_anchor': ['exact'],
        'ownership_type': ['exact', 'in'],
        'retail_category': ['contains'],
        'square_footage': ['gte', 'lte', 'range'],
        'base_rent': ['gte', 'lte', 'range'],
    }
    
    def get_permissions(self):
        """Configure permissions for tenant operations."""
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticatedOrReadOnly]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return TenantListSerializer
        elif self.action == 'create':
            return TenantCreateSerializer
        else:
            return TenantDetailSerializer
    
    def get_queryset(self):
        """Custom queryset filtering for business logic."""
        queryset = self.queryset
        
        # Filter by shopping center
        shopping_center_id = self.request.query_params.get('shopping_center')
        if shopping_center_id:
            try:
                queryset = queryset.filter(shopping_center_id=int(shopping_center_id))
            except ValueError:
                pass
        
        # Filter by lease expiration timeframe
        lease_expiring = self.request.query_params.get('lease_expiring')
        if lease_expiring:
            try:
                months = int(lease_expiring)
                from datetime import date
                from dateutil.relativedelta import relativedelta
                
                warning_date = date.today() + relativedelta(months=months)
                queryset = queryset.filter(
                    lease_expiration__lte=warning_date,
                    lease_expiration__gte=date.today()
                )
            except ValueError:
                pass
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def chains(self, request):
        """
        Get tenant chains (same tenant name in multiple locations).
        
        Useful for analyzing tenant expansion and chain operations.
        """
        # Find tenants that appear in multiple shopping centers
        chain_tenants = Tenant.objects.values('tenant_name').annotate(
            location_count=Count('shopping_center', distinct=True),
            total_square_footage=Sum('square_footage'),
            shopping_centers=Count('shopping_center', distinct=True)
        ).filter(
            location_count__gt=1
        ).order_by('-location_count', 'tenant_name')
        
        # Get detailed information for each chain
        chains_data = []
        for chain in chain_tenants:
            tenant_locations = Tenant.objects.filter(
                tenant_name=chain['tenant_name']
            ).select_related('shopping_center').values(
                'shopping_center__shopping_center_name',
                'shopping_center__address_city',
                'shopping_center__address_state',
                'tenant_suite_number',
                'square_footage',
                'occupancy_status'
            )
            
            chains_data.append({
                'tenant_name': chain['tenant_name'],
                'location_count': chain['location_count'],
                'total_square_footage': chain['total_square_footage'],
                'locations': list(tenant_locations)
            })
        
        return Response({
            'chains': chains_data,
            'total_chains': len(chains_data)
        })
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """
        Get retail category statistics.
        
        Returns breakdown of tenants by retail category.
        """
        from django.contrib.postgres.aggregates import ArrayAgg
        
        # Get all unique retail categories
        categories = {}
        
        # This is a simplified approach - in practice, you'd want more sophisticated
        # category aggregation since retail_category is an ArrayField
        tenants_with_categories = Tenant.objects.exclude(
            retail_category__isnull=True
        ).exclude(
            retail_category=[]
        )
        
        for tenant in tenants_with_categories:
            for category in tenant.retail_category or []:
                if category not in categories:
                    categories[category] = {
                        'category': category,
                        'tenant_count': 0,
                        'total_square_footage': 0,
                        'shopping_centers': set()
                    }
                
                categories[category]['tenant_count'] += 1
                if tenant.square_footage:
                    categories[category]['total_square_footage'] += tenant.square_footage
                categories[category]['shopping_centers'].add(tenant.shopping_center.shopping_center_name)
        
        # Convert sets to counts and lists
        category_stats = []
        for cat_data in categories.values():
            category_stats.append({
                'category': cat_data['category'],
                'tenant_count': cat_data['tenant_count'],
                'total_square_footage': cat_data['total_square_footage'],
                'shopping_center_count': len(cat_data['shopping_centers'])
            })
        
        # Sort by tenant count
        category_stats.sort(key=lambda x: x['tenant_count'], reverse=True)
        
        return Response({
            'categories': category_stats,
            'total_categories': len(category_stats)
        })


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_api_access(request, view_name, additional_info=None):
    """Log API access for monitoring and analytics."""
    client_ip = get_client_ip(request)
    user = request.user if request.user.is_authenticated else 'Anonymous'
    
    log_data = {
        'view': view_name,
        'user': str(user),
        'ip': client_ip,
        'method': request.method,
        'path': request.path,
        'query_params': dict(request.query_params),
    }
    
    if additional_info:
        log_data.update(additional_info)
    
    logger.info(f"API Access: {log_data}")


# =============================================================================
# CUSTOM EXCEPTION HANDLERS
# =============================================================================

def handle_api_exception(exc, context):
    """Custom exception handler for API errors."""
    from rest_framework.views import exception_handler
    
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        # Log the error
        logger.error(f"API Exception: {exc} | Context: {context}")
        
        # Customize error response format
        custom_response_data = {
            'error': True,
            'message': 'An error occurred processing your request',
            'details': response.data,
            'status_code': response.status_code,
        }
        
        # Add specific messages for common errors
        if response.status_code == 400:
            custom_response_data['message'] = 'Invalid request data'
        elif response.status_code == 401:
            custom_response_data['message'] = 'Authentication required'
        elif response.status_code == 403:
            custom_response_data['message'] = 'Permission denied'
        elif response.status_code == 404:
            custom_response_data['message'] = 'Resource not found'
        elif response.status_code == 500:
            custom_response_data['message'] = 'Internal server error'
        
        response.data = custom_response_data
    
    return response
