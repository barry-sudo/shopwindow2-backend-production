# properties/views.py - EMERGENCY FIX (No PostGIS required)

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
# EMERGENCY FIX: Remove all geographic imports temporarily
import logging

from .models import ShoppingCenter, Tenant
from .serializers import (
    ShoppingCenterSerializer, 
    TenantSerializer,
    ShoppingCenterDetailSerializer
)
from .filters import ShoppingCenterFilter, TenantFilter

logger = logging.getLogger(__name__)


class ShoppingCenterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ShoppingCenter model with progressive data enrichment support.
    Implements the "stocking shelves" philosophy - accepts incomplete data gracefully.
    """
    queryset = ShoppingCenter.objects.all()
    serializer_class = ShoppingCenterSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchBackend, filters.OrderingFilter]
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
        """Use detailed serializer for retrieve actions."""
        if self.action == 'retrieve':
            return ShoppingCenterDetailSerializer
        return ShoppingCenterSerializer

    def get_queryset(self):
        """
        Enhanced queryset with data quality indicators.
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
        EMERGENCY FIX: Geographic search temporarily disabled.
        """
        return Response(
            {
                "message": "Geographic search temporarily unavailable",
                "error": "PostGIS configuration in progress",
                "available_endpoints": [
                    "/api/v1/shopping-centers/",
                    "/api/v1/shopping-centers/data_quality/", 
                    "/api/v1/shopping-centers/{id}/enrich_data/"
                ]
            },
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
        complete_address = centers.exclude(
            Q(address_street__isnull=True) | Q(address_street__exact='')
        ).count()
        has_gla = centers.exclude(
            Q(total_gla__isnull=True) | Q(total_gla=0)
        ).count()
        has_tenants = centers.filter(tenant_count__gt=0).count()
        
        return Response({
            'total_centers': total_count,
            'data_completeness': {
                'complete_addresses': {
                    'count': complete_address,
                    'percentage': round((complete_address / total_count * 100) if total_count > 0 else 0, 1)
                },
                'has_gla_data': {
                    'count': has_gla,
                    'percentage': round((has_gla / total_count * 100) if total_count > 0 else 0, 1)
                },
                'has_tenant_data': {
                    'count': has_tenants,
                    'percentage': round((has_tenants / total_count * 100) if total_count > 0 else 0, 1)
                }
            }
        })

    @action(detail=True, methods=['post'])
    def enrich_data(self, request, pk=None):
        """
        Endpoint for progressive data enrichment - add missing fields to existing center.
        """
        center = self.get_object()
        serializer = ShoppingCenterSerializer(center, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            
            # Log enrichment for audit trail
            enriched_fields = [
                field for field in request.data.keys() 
                if getattr(center, field, None) != request.data[field]
            ]
            
            logger.info(f"Data enriched for center {center.id}: {enriched_fields}")
            
            return Response({
                'message': 'Data successfully enriched',
                'enriched_fields': enriched_fields,
                'data': serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tenant model with shopping center relationship.
    """
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchBackend, filters.OrderingFilter]
    filterset_class = TenantFilter
    search_fields = ['tenant_name', 'tenant_category', 'shopping_center__shopping_center_name']
    ordering_fields = ['tenant_name', 'square_footage', 'lease_start_date']
    ordering = ['tenant_name']

    def get_queryset(self):
        """Optimize queries with select_related."""
        return Tenant.objects.select_related('shopping_center')

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """
        Group tenants by category with counts.
        """
        from django.db.models import Count
        
        categories = self.get_queryset().values('tenant_category').annotate(
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
