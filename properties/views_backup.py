# properties/views.py - COMPLETE VERSION WITH CSV UPLOAD

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, parser_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.contrib.gis.geos import Point
from django.utils import timezone
import logging

from .models import ShoppingCenter, Tenant
from .serializers import (
    ShoppingCenterListSerializer,
    ShoppingCenterDetailSerializer,
    ShoppingCenterCreateSerializer,
    ShoppingCenterUpdateSerializer,
    TenantListSerializer,
    TenantDetailSerializer,
    TenantCreateSerializer,
)
from .filters import ShoppingCenterFilter, TenantFilter
from .import_utils import process_csv_import, calculate_fields_updated

logger = logging.getLogger(__name__)


class ShoppingCenterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ShoppingCenter model with progressive data enrichment support.
    Implements the "stocking shelves" philosophy - accepts incomplete data gracefully.
    
    Uses different serializers for different actions:
    - List: ShoppingCenterListSerializer (optimized for maps/listings)
    - Retrieve: ShoppingCenterDetailSerializer (full data with tenants)
    - Create: ShoppingCenterCreateSerializer (validation for new entries)
    - Update/Partial Update: ShoppingCenterUpdateSerializer (progressive enrichment)
    """
    queryset = ShoppingCenter.objects.all()
    serializer_class = ShoppingCenterListSerializer  # Default for list action
    permission_classes = [AllowAny]
    #pagination_class = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ShoppingCenterFilter
    search_fields = [
        'shopping_center_name', 
        'address_city', 
        'address_state',
        'center_type'
    ]
    ordering_fields = [
        'shopping_center_name', 
        'total_gla', 
        'year_built',
        'created_at'
    ]
    ordering = ['-created_at']

    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        This implements the progressive data enrichment pattern.
        """
        if self.action == 'retrieve':
            return ShoppingCenterDetailSerializer
        elif self.action == 'create':
            return ShoppingCenterCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ShoppingCenterUpdateSerializer
        return ShoppingCenterListSerializer

    def get_queryset(self):
        """
        Enhanced queryset with geographic filtering and data quality indicators.
        """
        queryset = ShoppingCenter.objects.select_related().prefetch_related('tenants')
        
        # Add data completeness annotation
        queryset = queryset.annotate(
            tenant_count=Count('tenants')
        )
        
        return queryset

    @action(detail=False, methods=['get'])
    def nearby(self, request):
        """
        Find shopping centers within specified distance of coordinates.
        Uses PostGIS for geographic queries.
        """
        try:
            lat = float(request.query_params.get('lat', 0))
            lng = float(request.query_params.get('lng', 0))
            radius = float(request.query_params.get('radius', 10))  # km
            
            # Validate coordinates
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return Response(
                    {"error": "Invalid coordinates provided"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create point for user location
            user_location = Point(lng, lat, srid=4326)
            
            # PostGIS distance query
            nearby_centers = self.get_queryset().annotate(
                distance=Distance('location', user_location)
            ).filter(
                location__distance_lte=(user_location, D(km=radius))
            ).order_by('distance')
            
            serializer = self.get_serializer(nearby_centers, many=True)
            return Response({
                'results': serializer.data,
                'search_center': {'lat': lat, 'lng': lng},
                'radius_km': radius,
                'count': nearby_centers.count()
            })
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid parameters for nearby search: {str(e)}")
            return Response(
                {"error": "Invalid coordinates or radius provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Geographic query failed: {str(e)}")
            return Response(
                {"error": "Geographic search temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

    @action(detail=False, methods=['get'])
    def data_quality(self, request):
        """
        Return data completeness metrics for shopping centers.
        Part of progressive data enrichment strategy.
        """
        centers = self.get_queryset()
        
        total_count = centers.count()
        if total_count == 0:
            return Response({
                'message': 'No shopping centers in database',
                'total_centers': 0
            })
        
        complete_address = centers.exclude(
            Q(address_street__isnull=True) | Q(address_street__exact='')
        ).count()
        has_gla = centers.exclude(
            Q(total_gla__isnull=True) | Q(total_gla=0)
        ).count()
        has_tenants = centers.filter(tenant_count__gt=0).count()
        has_coordinates = centers.exclude(
            Q(latitude__isnull=True) | Q(longitude__isnull=True)
        ).count()
        
        return Response({
            'total_centers': total_count,
            'data_completeness': {
                'complete_addresses': {
                    'count': complete_address,
                    'percentage': round((complete_address / total_count * 100), 1)
                },
                'has_gla_data': {
                    'count': has_gla,
                    'percentage': round((has_gla / total_count * 100), 1)
                },
                'has_tenant_data': {
                    'count': has_tenants,
                    'percentage': round((has_tenants / total_count * 100), 1)
                },
                'has_coordinates': {
                    'count': has_coordinates,
                    'percentage': round((has_coordinates / total_count * 100), 1)
                }
            }
        })

    @action(detail=True, methods=['post'])
    def enrich_data(self, request, pk=None):
        """
        Endpoint for progressive data enrichment - add missing fields to existing center.
        Uses UpdateSerializer to support partial updates without overwriting existing data.
        """
        center = self.get_object()
        serializer = ShoppingCenterUpdateSerializer(center, data=request.data, partial=True)
        
        if serializer.is_valid():
            # Track what fields are being enriched
            enriched_fields = []
            for field, value in request.data.items():
                old_value = getattr(center, field, None)
                if old_value != value and value is not None and value != '':
                    enriched_fields.append(field)
            
            serializer.save()
            
            # Log enrichment for audit trail
            if enriched_fields:
                logger.info(f"Data enriched for center {center.id}: {enriched_fields}")
            
            return Response({
                'message': 'Data successfully enriched',
                'enriched_fields': enriched_fields,
                'data': ShoppingCenterDetailSerializer(center).data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tenant model with shopping center relationship.
    
    Uses different serializers for different actions:
    - List: TenantListSerializer (summary data)
    - Retrieve: TenantDetailSerializer (full tenant info)
    - Create: TenantCreateSerializer (validation for new tenants)
    - Update: TenantDetailSerializer (for modifications)
    """
    queryset = Tenant.objects.all()
    serializer_class = TenantListSerializer  # Default for list action
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TenantFilter
    search_fields = ['tenant_name', 'retail_category', 'shopping_center__shopping_center_name']
    ordering_fields = ['tenant_name', 'square_footage', 'lease_expiration']
    ordering = ['tenant_name']

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return TenantDetailSerializer
        elif self.action == 'create':
            return TenantCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TenantDetailSerializer
        return TenantListSerializer

    def get_queryset(self):
        """Optimize queries with select_related."""
        return Tenant.objects.select_related('shopping_center')

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """
        Group tenants by category with counts.
        """
        from django.db.models import Count
        
        categories = self.get_queryset().values('retail_category').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response({
            'categories': list(categories),
            'total_categories': len(categories)
        })

    @action(detail=False, methods=['get']) 
    def vacancy_analysis(self, request):
        """
        Analyze vacancy rates across shopping centers.
        """
        from django.db.models import Avg, Count, Q
        
        # Get centers with tenant counts
        centers_with_tenants = ShoppingCenter.objects.annotate(
            tenant_count=Count('tenants'),
            occupied_space=Count('tenants__square_footage')
        ).exclude(total_gla__isnull=True)
        
        analysis = {
            'total_centers': centers_with_tenants.count(),
            'avg_tenants_per_center': centers_with_tenants.aggregate(
                avg=Avg('tenant_count')
            )['avg'] or 0,
            'centers_by_occupancy': {
                'fully_occupied': centers_with_tenants.filter(tenant_count__gte=20).count(),
                'moderately_occupied': centers_with_tenants.filter(
                    tenant_count__gte=10, tenant_count__lt=20
                ).count(),
                'low_occupancy': centers_with_tenants.filter(
                    tenant_count__lt=10
                ).count()
            }
        }
        
        return Response(analysis)


@api_view(['GET'])
def health_check(request):
    """System health check including PostGIS availability."""
    try:
        from django.db import connection
        
        # Test basic database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_status = "connected"
            
            # Test PostGIS availability
            try:
                cursor.execute("SELECT PostGIS_Version();")
                postgis_version = cursor.fetchone()[0]
                postgis_status = f"available - {postgis_version}"
            except Exception as e:
                postgis_status = f"unavailable - {str(e)}"
        
        return Response({
            'status': 'healthy',
            'database': db_status,
            'postgis': postgis_status,
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# =============================================================================
# CSV UPLOAD ENDPOINT - Added Oct 11, 2025
# =============================================================================

@api_view(['POST'])
@parser_classes([MultiPartParser])
def upload_csv(request):
    """
    Simple CSV upload endpoint for web-based imports.
    Uses same logic as management command.
    
    POST /api/v1/properties/upload-csv/
    
    Request:
        - Content-Type: multipart/form-data
        - Body: file (CSV file)
    
    Response:
        {
            'success': true,
            'stats': {
                'shopping_centers_imported': 5,  # created + updated
                'tenants_imported': 47,          # created + updated
                'fields_updated': 234,
                'errors': []
            },
            'timestamp': '2025-10-11T14:30:00Z'
        }
    """
    try:
        # Validate file upload
        if 'file' not in request.FILES:
            return Response(
                {'success': False, 'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['file']
        
        # Validate file type
        if not uploaded_file.name.lower().endswith('.csv'):
            return Response(
                {'success': False, 'error': 'Only CSV files are allowed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if uploaded_file.size > max_size:
            return Response(
                {'success': False, 'error': 'File too large. Maximum size is 10MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Read file content
        try:
            csv_content = uploaded_file.read().decode('utf-8-sig')  # Handle BOM
        except UnicodeDecodeError:
            try:
                uploaded_file.seek(0)
                csv_content = uploaded_file.read().decode('latin-1')
            except UnicodeDecodeError:
                return Response(
                    {'success': False, 'error': 'Unable to decode CSV file. Please ensure it is UTF-8 encoded'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Process CSV import
        import_stats = process_csv_import(csv_content, clear_existing=False)
        
        # Calculate totals for response
        shopping_centers_imported = import_stats['centers_created'] + import_stats['centers_updated']
        tenants_imported = import_stats['tenants_created'] + import_stats['tenants_updated']
        fields_updated = calculate_fields_updated(import_stats)
        
        # Return simplified stats
        return Response({
            'success': True,
            'stats': {
                'shopping_centers_imported': shopping_centers_imported,
                'tenants_imported': tenants_imported,
                'fields_updated': fields_updated,
                'errors': import_stats['errors'][:10]  # Limit to first 10 errors
            },
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"CSV upload failed: {str(e)}")
        return Response(
            {
                'success': False,
                'error': f'Import failed: {str(e)}',
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
