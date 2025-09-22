# ===== OPTIMIZED PROPERTIES VIEWS =====
"""
Properties Views - Shop Window Backend API (Performance Optimized)
Django REST Framework views for shopping centers and tenants.

Key Performance Optimizations:
- Prefetch related data to avoid N+1 queries
- Database query optimization with select_related/prefetch_related
- Efficient spatial queries using PostGIS
- Proper pagination and filtering
- Response caching for read-heavy operations
"""

from django.db import transaction
from django.db.models import Q, Count, Avg, Sum, Prefetch
from django.db.models.functions import Distance
from django.shortcuts import get_object_or_404
from django.contrib.gis.measure import D
from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings

from rest_framework import status, generics, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

from django_filters.rest_framework import DjangoFilterBackend

from .models import ShoppingCenter, Tenant
from .serializers import (
    ShoppingCenterSerializer,
    ShoppingCenterDetailSerializer,
    ShoppingCenterCreateSerializer,
    TenantSerializer,
    TenantCreateSerializer
)
from .filters import ShoppingCenterFilter, TenantFilter
from services import (
    safe_calculate_quality_score, 
    safe_calculate_center_type,
    safe_geocode_address
)

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM PAGINATION WITH PERFORMANCE OPTIMIZATION
# =============================================================================

class OptimizedPagination(PageNumberPagination):
    """Optimized pagination with performance monitoring."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'page_size': self.page_size,
            'results': data
        })


class UploadRateThrottle(UserRateThrottle):
    """Custom throttle for upload endpoints."""
    rate = '5/hour'


# =============================================================================
# SHOPPING CENTER VIEWSET - OPTIMIZED
# =============================================================================

class ShoppingCenterViewSet(ModelViewSet):
    """
    Optimized ViewSet for shopping center CRUD operations.
    
    Performance Features:
    - Optimized database queries with prefetch_related
    - Spatial query optimization for location-based searches
    - Response caching for read operations
    - Efficient bulk operations
    """
    
    serializer_class = ShoppingCenterSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = OptimizedPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ShoppingCenterFilter
    search_fields = ['shopping_center_name', 'address_city', 'address_state']
    ordering_fields = ['shopping_center_name', 'total_gla', 'created_at', 'data_quality_score']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Optimized queryset with strategic prefetching to avoid N+1 queries.
        """
        # Base queryset with optimized select_related for foreign keys
        queryset = ShoppingCenter.objects.select_related(
            'import_batch',
            'last_import_batch'
        )
        
        # Prefetch tenants with their related data for detail views
        if self.action in ['retrieve', 'list']:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'tenants',
                    queryset=Tenant.objects.select_related().order_by('tenant_name')
                )
            )
        
        # Add annotations for common aggregations
        queryset = queryset.annotate(
            tenant_count=Count('tenants'),
            occupied_tenant_count=Count('tenants', filter=Q(tenants__occupancy_status='OCCUPIED')),
            total_leased_sqft=Sum('tenants__square_footage'),
        )
        
        # Spatial queries optimization - only when needed
        if 'latitude' in self.request.GET or 'longitude' in self.request.GET:
            # Use database-level distance calculations
            try:
                lat = float(self.request.GET.get('latitude', 0))
                lng = float(self.request.GET.get('longitude', 0))
                radius = float(self.request.GET.get('radius', 25))  # 25 miles default
                
                user_location = Point(lng, lat, srid=4326)
                queryset = queryset.filter(
                    geo_location__distance_lte=(user_location, D(mi=radius))
                ).annotate(
                    distance=Distance('geo_location', user_location)
                ).order_by('distance')
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid spatial query parameters: {e}")
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return ShoppingCenterCreateSerializer
        elif self.action == 'retrieve':
            return ShoppingCenterDetailSerializer
        return ShoppingCenterSerializer
    
    @transaction.atomic
    def perform_create(self, serializer):
        """
        Optimized create with automatic geocoding and business logic.
        """
        shopping_center = serializer.save()
        
        # Trigger geocoding in background if address provided
        if (shopping_center.address_street and 
            not shopping_center.latitude and 
            not shopping_center.longitude):
            
            try:
                coordinates = safe_geocode_address(shopping_center.full_address)
                if coordinates:
                    shopping_center.latitude, shopping_center.longitude = coordinates
                    # Create Point for PostGIS
                    shopping_center.geo_location = Point(coordinates[1], coordinates[0], srid=4326)
                    shopping_center.save(update_fields=['latitude', 'longitude', 'geo_location'])
                    
            except Exception as e:
                logger.error(f"Geocoding failed for {shopping_center.shopping_center_name}: {e}")
        
        # Calculate initial quality score
        try:
            quality_score = safe_calculate_quality_score(shopping_center)
            if quality_score != shopping_center.data_quality_score:
                shopping_center.data_quality_score = quality_score
                shopping_center.save(update_fields=['data_quality_score'])
        except Exception as e:
            logger.error(f"Quality score calculation failed: {e}")
        
        return shopping_center
    
    @transaction.atomic
    def perform_update(self, serializer):
        """
        Optimized update with change detection and selective processing.
        """
        original_instance = self.get_object()
        updated_instance = serializer.save()
        
        # Check if address fields changed for re-geocoding
        address_fields = ['address_street', 'address_city', 'address_state', 'address_zip']
        address_changed = any(
            getattr(original_instance, field) != getattr(updated_instance, field)
            for field in address_fields
        )
        
        if address_changed and updated_instance.full_address:
            try:
                coordinates = safe_geocode_address(updated_instance.full_address)
                if coordinates:
                    updated_instance.latitude, updated_instance.longitude = coordinates
                    updated_instance.geo_location = Point(coordinates[1], coordinates[0], srid=4326)
                    updated_instance.save(update_fields=['latitude', 'longitude', 'geo_location'])
            except Exception as e:
                logger.error(f"Re-geocoding failed: {e}")
        
        # Recalculate quality score if significant fields changed
        quality_affecting_fields = ['total_gla', 'center_type', 'owner_name', 'property_manager']
        if address_changed or any(
            getattr(original_instance, field) != getattr(updated_instance, field)
            for field in quality_affecting_fields
        ):
            try:
                quality_score = safe_calculate_quality_score(updated_instance)
                if quality_score != updated_instance.data_quality_score:
                    updated_instance.data_quality_score = quality_score
                    updated_instance.save(update_fields=['data_quality_score'])
            except Exception as e:
                logger.error(f"Quality score recalculation failed: {e}")
        
        return updated_instance
    
    # ==========================================================================
    # OPTIMIZED CUSTOM ACTIONS
    # ==========================================================================
    
    @action(detail=False, methods=['get'])
    @cache_page(300)  # Cache for 5 minutes
    @vary_on_headers('Authorization')
    def map_data(self, request):
        """
        Optimized endpoint for map display with minimal data transfer.
        Returns only essential fields for map markers.
        """
        queryset = self.get_queryset().only(
            'id', 'shopping_center_name', 'latitude', 'longitude', 
            'center_type', 'total_gla', 'address_city', 'address_state'
        )
        
        # Apply basic filters
        name_filter = request.GET.get('search')
        if name_filter:
            queryset = queryset.filter(shopping_center_name__icontains=name_filter)
        
        # Limit results for map performance
        queryset = queryset[:500]  # Max 500 markers on map
        
        map_data = []
        for center in queryset:
            if center.latitude and center.longitude:
                map_data.append({
                    'id': center.id,
                    'name': center.shopping_center_name,
                    'lat': float(center.latitude),
                    'lng': float(center.longitude),
                    'type': center.center_type,
                    'gla': center.total_gla,
                    'location': f"{center.address_city}, {center.address_state}"
                })
        
        return Response({
            'count': len(map_data),
            'results': map_data
        })
    
    @action(detail=True, methods=['get'])
    @cache_page(300)
    def analytics(self, request, pk=None):
        """
        Get comprehensive analytics for a shopping center.
        Cached for performance.
        """
        shopping_center = self.get_object()
        
        # Use cached analytics if available
        cache_key = f"shopping_center_analytics_{pk}"
        cached_analytics = cache.get(cache_key)
        
        if cached_analytics:
            return Response(cached_analytics)
        
        # Calculate analytics
        tenants = shopping_center.tenants.all()
        
        analytics_data = {
            'basic_metrics': {
                'total_tenants': tenants.count(),
                'occupied_tenants': tenants.filter(occupancy_status='OCCUPIED').count(),
                'vacant_spaces': tenants.filter(occupancy_status='VACANT').count(),
                'total_gla': shopping_center.total_gla or 0,
                'leased_sqft': tenants.aggregate(total=Sum('square_footage'))['total'] or 0,
            },
            'occupancy_analysis': self._calculate_occupancy_metrics(tenants),
            'tenant_mix': self._analyze_tenant_categories(tenants),
            'financial_metrics': self._calculate_financial_metrics(tenants),
            'data_quality': {
                'score': shopping_center.data_quality_score,
                'completeness': self._analyze_data_completeness(shopping_center)
            }
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, analytics_data, 300)
        
        return Response(analytics_data)
    
    @action(detail=False, methods=['get'])
    def nearby(self, request):
        """
        Optimized spatial query for nearby shopping centers.
        Uses PostGIS spatial indexing for performance.
        """
        try:
            latitude = float(request.GET.get('latitude'))
            longitude = float(request.GET.get('longitude'))
            radius = float(request.GET.get('radius', 10))  # Default 10 miles
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid coordinates. Latitude and longitude are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user_location = Point(longitude, latitude, srid=4326)
        
        # Optimized spatial query using PostGIS
        nearby_centers = ShoppingCenter.objects.filter(
            geo_location__distance_lte=(user_location, D(mi=radius))
        ).annotate(
            distance_miles=Distance('geo_location', user_location)
        ).select_related(
            'import_batch'
        ).prefetch_related(
            'tenants'
        ).order_by('distance_miles')[:50]  # Limit results
        
        serializer = ShoppingCenterSerializer(nearby_centers, many=True)
        return Response({
            'center': {'lat': latitude, 'lng': longitude},
            'radius_miles': radius,
            'count': len(nearby_centers),
            'results': serializer.data
        })
    
    @action(detail=False, methods=['post'], throttle_classes=[UploadRateThrottle])
    def bulk_update(self, request):
        """
        Bulk update multiple shopping centers efficiently.
        Uses batch processing to minimize database queries.
        """
        updates = request.data.get('updates', [])
        
        if not updates or len(updates) > 100:
            return Response(
                {'error': 'Updates must be between 1 and 100 items'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_centers = []
        errors = []
        
        with transaction.atomic():
            for update_data in updates:
                try:
                    center_id = update_data.get('id')
                    if not center_id:
                        errors.append({'error': 'Missing id in update data'})
                        continue
                    
                    center = ShoppingCenter.objects.get(id=center_id)
                    serializer = ShoppingCenterSerializer(
                        center, 
                        data=update_data, 
                        partial=True
                    )
                    
                    if serializer.is_valid():
                        serializer.save()
                        updated_centers.append(serializer.data)
                    else:
                        errors.append({
                            'id': center_id, 
                            'errors': serializer.errors
                        })
                        
                except ShoppingCenter.DoesNotExist:
                    errors.append({
                        'id': center_id, 
                        'error': 'Shopping center not found'
                    })
                except Exception as e:
                    errors.append({
                        'id': center_id, 
                        'error': str(e)
                    })
        
        return Response({
            'updated_count': len(updated_centers),
            'error_count': len(errors),
            'updated_centers': updated_centers,
            'errors': errors
        })
    
    # ==========================================================================
    # HELPER METHODS FOR ANALYTICS
    # ==========================================================================
    
    def _calculate_occupancy_metrics(self, tenants):
        """Calculate occupancy-related metrics."""
        total_tenants = tenants.count()
        if total_tenants == 0:
            return {'occupancy_rate': 0, 'vacancy_rate': 0}
        
        occupied = tenants.filter(occupancy_status='OCCUPIED').count()
        
        return {
            'occupancy_rate': (occupied / total_tenants) * 100,
            'vacancy_rate': ((total_tenants - occupied) / total_tenants) * 100,
            'pending_leases': tenants.filter(occupancy_status='PENDING').count()
        }
    
    def _analyze_tenant_categories(self, tenants):
        """Analyze tenant category distribution."""
        # This would need to be implemented based on your retail_category field structure
        categories = {}
        for tenant in tenants:
            if tenant.retail_category:
                for category in tenant.retail_category:
                    categories[category] = categories.get(category, 0) + 1
        
        return categories
    
    def _calculate_financial_metrics(self, tenants):
        """Calculate financial metrics."""
        rent_data = tenants.exclude(base_rent__isnull=True).aggregate(
            avg_rent=Avg('base_rent'),
            total_rent=Sum('base_rent'),
            min_rent=models.Min('base_rent'),
            max_rent=models.Max('base_rent')
        )
        
        return {
            'average_rent': rent_data.get('avg_rent'),
            'total_rent_roll': rent_data.get('total_rent'),
            'rent_range': {
                'min': rent_data.get('min_rent'),
                'max': rent_data.get('max_rent')
            }
        }
    
    def _analyze_data_completeness(self, shopping_center):
        """Analyze data completeness for quality scoring."""
        total_fields = 15  # Total important fields
        completed_fields = 0
        
        # Check core fields
        if shopping_center.shopping_center_name:
            completed_fields += 1
        if shopping_center.address_street:
            completed_fields += 1
        if shopping_center.address_city:
            completed_fields += 1
        if shopping_center.address_state:
            completed_fields += 1
        if shopping_center.total_gla:
            completed_fields += 1
        if shopping_center.center_type:
            completed_fields += 1
        if shopping_center.latitude and shopping_center.longitude:
            completed_fields += 2
        if shopping_center.owner_name:
            completed_fields += 1
        if shopping_center.property_manager:
            completed_fields += 1
        if shopping_center.year_built:
            completed_fields += 1
        if shopping_center.contact_phone:
            completed_fields += 1
        # Tenant data completeness (3 points)
        if shopping_center.tenants.exists():
            completed_fields += 3
        
        return {
            'completed_fields': completed_fields,
            'total_fields': total_fields,
            'completeness_percentage': (completed_fields / total_fields) * 100
        }


# =============================================================================
# TENANT VIEWSET - OPTIMIZED
# =============================================================================

class TenantViewSet(ModelViewSet):
    """
    Optimized ViewSet for tenant CRUD operations.
    """
    
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = OptimizedPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TenantFilter
    search_fields = ['tenant_name', 'retail_category', 'shopping_center__shopping_center_name']
    ordering_fields = ['tenant_name', 'square_footage', 'base_rent', 'lease_expiration']
    ordering = ['tenant_name']
    
    def get_queryset(self):
        """Optimized queryset with select_related."""
        return Tenant.objects.select_related(
            'shopping_center'
        ).prefetch_related(
            'shopping_center__tenants'
        )
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return TenantCreateSerializer
        return TenantSerializer
    
    @action(detail=False, methods=['get'])
    def by_shopping_center(self, request):
        """Get tenants for a specific shopping center (optimized)."""
        center_id = request.GET.get('shopping_center_id')
        if not center_id:
            return Response(
                {'error': 'shopping_center_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tenants = self.get_queryset().filter(shopping_center_id=center_id)
        
        page = self.paginate_queryset(tenants)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tenants, many=True)
        return Response(serializer.data)


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Lightweight health check endpoint for monitoring.
    """
    try:
        # Quick database connectivity check
        ShoppingCenter.objects.count()
        
        # Check service integrations
        from services import check_service_health
        service_health = check_service_health()
        
        return Response({
            'status': 'healthy',
            'timestamp': timezone.now(),
            'database': 'connected',
            'services': service_health,
            'version': '1.0.0'
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)