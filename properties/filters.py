"""
Properties Filters - Shop Window Backend API
Django REST Framework filters for shopping centers and tenants.

Provides comprehensive filtering capabilities for:
- Geographic filtering (city, state, bounds)
- Size and type filtering (GLA, center type)
- Data quality filtering (quality scores, completeness)
- Business relationship filtering (owner, property manager)
- Tenant-specific filtering (occupancy, categories)
- Date and time filtering (creation, updates, lease terms)

Supports the progressive data enrichment philosophy by allowing
filtering based on EXTRACT, DETERMINE, and DEFINE field categories.
"""

from django_filters import rest_framework as filters
from django_filters import CharFilter, NumberFilter, BooleanFilter, DateFilter, ChoiceFilter
from django.db import models
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from decimal import Decimal

from .models import ShoppingCenter, Tenant


# =============================================================================
# SHOPPING CENTER FILTERS
# =============================================================================

class ShoppingCenterFilter(filters.FilterSet):
    """
    Comprehensive filtering for shopping centers with spatial and business logic support.
    
    Provides filtering capabilities for:
    - Location-based filtering (city, state, geographic bounds)
    - Size-based filtering (GLA ranges, center types)
    - Data quality filtering (completeness scores)
    - Business relationship filtering (ownership, management)
    - Spatial proximity filtering (nearby properties)
    """
    
    # =============================================================================
    # LOCATION FILTERS (EXTRACT fields)
    # =============================================================================
    
    # Basic location filtering
    city = CharFilter(
        field_name='address_city',
        lookup_expr='icontains',
        help_text='Filter by city name (partial match)'
    )
    
    state = CharFilter(
        field_name='address_state',
        lookup_expr='iexact',
        help_text='Filter by state code (exact match, e.g., CA, NY)'
    )
    
    zip_code = CharFilter(
        field_name='address_zip',
        lookup_expr='istartswith',
        help_text='Filter by ZIP code (prefix match)'
    )
    
    # Multiple city filtering
    cities = CharFilter(
        method='filter_multiple_cities',
        help_text='Filter by multiple cities (comma-separated)'
    )
    
    states = CharFilter(
        method='filter_multiple_states', 
        help_text='Filter by multiple states (comma-separated)'
    )
    
    # =============================================================================
    # SIZE AND TYPE FILTERS (EXTRACT + DETERMINE fields)
    # =============================================================================
    
    # GLA range filtering
    min_gla = NumberFilter(
        field_name='total_gla',
        lookup_expr='gte',
        help_text='Minimum GLA in square feet'
    )
    
    max_gla = NumberFilter(
        field_name='total_gla',
        lookup_expr='lte',
        help_text='Maximum GLA in square feet'
    )
    
    gla_range = CharFilter(
        method='filter_gla_range',
        help_text='GLA range filter (small, medium, large, xl)'
    )
    
    # Center type filtering
    center_type = ChoiceFilter(
        field_name='center_type',
        choices=[
            ('Strip/Convenience', 'Strip/Convenience'),
            ('Neighborhood Center', 'Neighborhood Center'),
            ('Community Center', 'Community Center'),
            ('Regional Mall', 'Regional Mall'),
            ('Super-Regional Mall', 'Super-Regional Mall'),
        ],
        help_text='Filter by shopping center type'
    )
    
    center_types = CharFilter(
        method='filter_multiple_center_types',
        help_text='Filter by multiple center types (comma-separated)'
    )
    
    # =============================================================================
    # DATA QUALITY FILTERS (DETERMINE fields)
    # =============================================================================
    
    # Quality score filtering
    min_quality = NumberFilter(
        field_name='data_quality_score',
        lookup_expr='gte',
        help_text='Minimum data quality score (0-100)'
    )
    
    max_quality = NumberFilter(
        field_name='data_quality_score',
        lookup_expr='lte',
        help_text='Maximum data quality score (0-100)'
    )
    
    quality_tier = ChoiceFilter(
        method='filter_quality_tier',
        choices=[
            ('high', 'High Quality (80-100%)'),
            ('medium', 'Medium Quality (50-79%)'),
            ('low', 'Low Quality (0-49%)'),
            ('incomplete', 'Needs Attention (<50%)')
        ],
        help_text='Filter by quality tier'
    )
    
    # Geocoding status
    has_coordinates = BooleanFilter(
        method='filter_has_coordinates',
        help_text='Filter by presence of lat/lng coordinates'
    )
    
    # =============================================================================
    # BUSINESS RELATIONSHIP FILTERS (DEFINE fields)
    # =============================================================================
    
    # Ownership and management
    owner = CharFilter(
        field_name='owner',
        lookup_expr='icontains',
        help_text='Filter by owner name (partial match)'
    )
    
    property_manager = CharFilter(
        field_name='property_manager',
        lookup_expr='icontains',
        help_text='Filter by property manager (partial match)'
    )
    
    leasing_agent = CharFilter(
        field_name='leasing_agent',
        lookup_expr='icontains',
        help_text='Filter by leasing agent (partial match)'
    )
    
    # Multiple business relationship filtering
    owners = CharFilter(
        method='filter_multiple_owners',
        help_text='Filter by multiple owners (comma-separated)'
    )
    
    # =============================================================================
    # SPATIAL FILTERS (DETERMINE fields)
    # =============================================================================
    
    # Proximity filtering - finds properties near a point
    near_lat = NumberFilter(
        method='filter_near_coordinates',
        help_text='Latitude for proximity search (use with near_lng and radius)'
    )
    
    near_lng = NumberFilter(
        method='filter_near_coordinates',
        help_text='Longitude for proximity search (use with near_lat and radius)'
    )
    
    radius_miles = NumberFilter(
        method='filter_near_coordinates',
        help_text='Search radius in miles (use with near_lat and near_lng)'
    )
    
    # Bounding box filtering for map views
    bounds = CharFilter(
        method='filter_map_bounds',
        help_text='Map bounds: "sw_lat,sw_lng,ne_lat,ne_lng"'
    )
    
    # =============================================================================
    # TEMPORAL FILTERS
    # =============================================================================
    
    created_after = DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text='Filter by creation date (YYYY-MM-DD)'
    )
    
    created_before = DateFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text='Filter by creation date (YYYY-MM-DD)'
    )
    
    updated_after = DateFilter(
        field_name='updated_at',
        lookup_expr='gte',
        help_text='Filter by last update date (YYYY-MM-DD)'
    )
    
    # =============================================================================
    # TENANT-BASED FILTERS
    # =============================================================================
    
    has_tenants = BooleanFilter(
        method='filter_has_tenants',
        help_text='Filter by presence of tenant data'
    )
    
    min_tenant_count = NumberFilter(
        method='filter_min_tenant_count',
        help_text='Minimum number of tenants'
    )
    
    max_vacancy_rate = NumberFilter(
        method='filter_max_vacancy_rate',
        help_text='Maximum vacancy rate percentage (0-100)'
    )
    
    # =============================================================================
    # PROGRESSIVE DATA FILTERS
    # =============================================================================
    
    data_completeness = ChoiceFilter(
        method='filter_data_completeness',
        choices=[
            ('extract_only', 'Extract fields only'),
            ('has_determine', 'Has calculated fields'),
            ('has_define', 'Has manual entry fields'),
            ('fully_enriched', 'Fully enriched data')
        ],
        help_text='Filter by data enrichment level'
    )
    
    class Meta:
        model = ShoppingCenter
        fields = {
            # Additional simple field filters
            'year_built': ['exact', 'gte', 'lte'],
            'county': ['icontains'],
            'municipality': ['icontains'],
        }
    
    # =============================================================================
    # CUSTOM FILTER METHODS
    # =============================================================================
    
    def filter_multiple_cities(self, queryset, name, value):
        """Filter by multiple cities (comma-separated list)"""
        if not value:
            return queryset
        
        cities = [city.strip() for city in value.split(',') if city.strip()]
        return queryset.filter(address_city__in=cities)
    
    def filter_multiple_states(self, queryset, name, value):
        """Filter by multiple states (comma-separated list)"""
        if not value:
            return queryset
        
        states = [state.strip().upper() for state in value.split(',') if state.strip()]
        return queryset.filter(address_state__in=states)
    
    def filter_gla_range(self, queryset, name, value):
        """Filter by predefined GLA ranges"""
        if not value:
            return queryset
        
        range_mapping = {
            'small': (0, 30000),        # Strip/Convenience
            'medium': (30000, 125000),  # Neighborhood  
            'large': (125000, 400000),  # Community
            'xl': (400000, float('inf')) # Regional+
        }
        
        if value.lower() in range_mapping:
            min_gla, max_gla = range_mapping[value.lower()]
            if max_gla == float('inf'):
                return queryset.filter(total_gla__gte=min_gla)
            else:
                return queryset.filter(total_gla__gte=min_gla, total_gla__lt=max_gla)
        
        return queryset
    
    def filter_multiple_center_types(self, queryset, name, value):
        """Filter by multiple center types"""
        if not value:
            return queryset
        
        types = [ct.strip() for ct in value.split(',') if ct.strip()]
        return queryset.filter(center_type__in=types)
    
    def filter_quality_tier(self, queryset, name, value):
        """Filter by quality score tiers"""
        if not value:
            return queryset
        
        tier_mapping = {
            'high': (80, 100),
            'medium': (50, 79),
            'low': (1, 49),
            'incomplete': (0, 49)
        }
        
        if value in tier_mapping:
            min_score, max_score = tier_mapping[value]
            return queryset.filter(
                data_quality_score__gte=min_score,
                data_quality_score__lte=max_score
            )
        
        return queryset
    
    def filter_has_coordinates(self, queryset, name, value):
        """Filter by presence of geographic coordinates"""
        if value is True:
            return queryset.filter(
                latitude__isnull=False,
                longitude__isnull=False
            )
        elif value is False:
            return queryset.filter(
                models.Q(latitude__isnull=True) | models.Q(longitude__isnull=True)
            )
        return queryset
    
    def filter_multiple_owners(self, queryset, name, value):
        """Filter by multiple owners"""
        if not value:
            return queryset
        
        owners = [owner.strip() for owner in value.split(',') if owner.strip()]
        # Use OR logic for partial matches across multiple owners
        q_objects = models.Q()
        for owner in owners:
            q_objects |= models.Q(owner__icontains=owner)
        
        return queryset.filter(q_objects)
    
    def filter_near_coordinates(self, queryset, name, value):
        """
        Spatial proximity filtering using PostGIS.
        Requires near_lat, near_lng, and radius_miles parameters.
        """
        # This method gets called for each of the three parameters
        # We need to check if all three are present in the request
        request = self.request
        lat = request.GET.get('near_lat')
        lng = request.GET.get('near_lng') 
        radius = request.GET.get('radius_miles')
        
        if not (lat and lng and radius):
            return queryset
        
        try:
            lat = float(lat)
            lng = float(lng)
            radius = float(radius)
            
            # Create point and filter by distance
            point = Point(lng, lat, srid=4326)
            return queryset.filter(
                latitude__isnull=False,
                longitude__isnull=False
            ).annotate(
                distance=models.functions.Distance('location', point)
            ).filter(
                distance__lte=D(mi=radius)
            ).order_by('distance')
            
        except (ValueError, TypeError):
            return queryset
    
    def filter_map_bounds(self, queryset, name, value):
        """Filter by map viewport bounds"""
        if not value:
            return queryset
        
        try:
            # Parse bounds: "sw_lat,sw_lng,ne_lat,ne_lng"
            coords = [float(x.strip()) for x in value.split(',')]
            if len(coords) != 4:
                return queryset
            
            sw_lat, sw_lng, ne_lat, ne_lng = coords
            
            return queryset.filter(
                latitude__gte=sw_lat,
                latitude__lte=ne_lat,
                longitude__gte=sw_lng,
                longitude__lte=ne_lng
            )
            
        except (ValueError, TypeError):
            return queryset
    
    def filter_has_tenants(self, queryset, name, value):
        """Filter by presence of tenant data"""
        if value is True:
            return queryset.annotate(
                tenant_count=models.Count('tenants')
            ).filter(tenant_count__gt=0)
        elif value is False:
            return queryset.annotate(
                tenant_count=models.Count('tenants')
            ).filter(tenant_count=0)
        
        return queryset
    
    def filter_min_tenant_count(self, queryset, name, value):
        """Filter by minimum number of tenants"""
        if not value:
            return queryset
        
        try:
            min_count = int(value)
            return queryset.annotate(
                tenant_count=models.Count('tenants')
            ).filter(tenant_count__gte=min_count)
        except (ValueError, TypeError):
            return queryset
    
    def filter_max_vacancy_rate(self, queryset, name, value):
        """Filter by maximum vacancy rate"""
        if not value:
            return queryset
        
        try:
            max_rate = float(value)
            # This would require more complex calculation
            # For now, return queryset as-is
            # TODO: Implement vacancy rate calculation in annotation
            return queryset
        except (ValueError, TypeError):
            return queryset
    
    def filter_data_completeness(self, queryset, name, value):
        """Filter by data enrichment completeness level"""
        if not value:
            return queryset
        
        if value == 'extract_only':
            # Has basic extracted fields but minimal other data
            return queryset.filter(
                shopping_center_name__isnull=False,
                owner__isnull=True,
                property_manager__isnull=True
            )
        elif value == 'has_determine':
            # Has calculated/determined fields
            return queryset.filter(
                models.Q(center_type__isnull=False) |
                models.Q(latitude__isnull=False, longitude__isnull=False)
            )
        elif value == 'has_define':
            # Has manually entered strategic data
            return queryset.filter(
                models.Q(owner__isnull=False) |
                models.Q(property_manager__isnull=False) |
                models.Q(year_built__isnull=False)
            )
        elif value == 'fully_enriched':
            # Has data across all categories
            return queryset.filter(
                shopping_center_name__isnull=False,
                center_type__isnull=False,
                owner__isnull=False,
                data_quality_score__gte=80
            )
        
        return queryset


# =============================================================================
# TENANT FILTERS
# =============================================================================

class TenantFilter(filters.FilterSet):
    """
    Comprehensive filtering for tenants with business and lease analysis support.
    
    Provides filtering capabilities for:
    - Tenant identification and categorization
    - Space and size filtering
    - Occupancy and lease status filtering
    - Business relationship filtering
    - Multi-location tenant analysis
    """
    
    # =============================================================================
    # TENANT IDENTITY FILTERS
    # =============================================================================
    
    tenant_name = CharFilter(
        field_name='tenant_name',
        lookup_expr='icontains',
        help_text='Filter by tenant name (partial match)'
    )
    
    tenant_names = CharFilter(
        method='filter_multiple_tenant_names',
        help_text='Filter by multiple tenant names (comma-separated)'
    )
    
    suite_number = CharFilter(
        field_name='tenant_suite_number',
        lookup_expr='icontains',
        help_text='Filter by suite number'
    )
    
    # =============================================================================
    # SHOPPING CENTER RELATIONSHIP FILTERS
    # =============================================================================
    
    shopping_center = NumberFilter(
        field_name='shopping_center__id',
        help_text='Filter by shopping center ID'
    )
    
    shopping_center_name = CharFilter(
        field_name='shopping_center__shopping_center_name',
        lookup_expr='icontains',
        help_text='Filter by shopping center name'
    )
    
    center_city = CharFilter(
        field_name='shopping_center__address_city',
        lookup_expr='icontains',
        help_text='Filter by shopping center city'
    )
    
    center_state = CharFilter(
        field_name='shopping_center__address_state',
        lookup_expr='iexact',
        help_text='Filter by shopping center state'
    )
    
    center_type = ChoiceFilter(
        field_name='shopping_center__center_type',
        choices=[
            ('Strip/Convenience', 'Strip/Convenience'),
            ('Neighborhood Center', 'Neighborhood Center'),
            ('Community Center', 'Community Center'),
            ('Regional Mall', 'Regional Mall'),
            ('Super-Regional Mall', 'Super-Regional Mall'),
        ],
        help_text='Filter by shopping center type'
    )
    
    # =============================================================================
    # SPACE AND SIZE FILTERS
    # =============================================================================
    
    min_square_footage = NumberFilter(
        field_name='square_footage',
        lookup_expr='gte',
        help_text='Minimum tenant square footage'
    )
    
    max_square_footage = NumberFilter(
        field_name='square_footage',
        lookup_expr='lte',
        help_text='Maximum tenant square footage'
    )
    
    size_category = ChoiceFilter(
        method='filter_size_category',
        choices=[
            ('small', 'Small (0-2,000 SF)'),
            ('medium', 'Medium (2,001-10,000 SF)'),
            ('large', 'Large (10,001-50,000 SF)'),
            ('anchor', 'Anchor (50,000+ SF)'),
        ],
        help_text='Filter by tenant size category'
    )
    
    # =============================================================================
    # OCCUPANCY AND STATUS FILTERS
    # =============================================================================
    
    occupancy_status = ChoiceFilter(
        field_name='occupancy_status',
        choices=[
            ('OCCUPIED', 'Occupied'),
            ('VACANT', 'Vacant'),
            ('PENDING', 'Pending'),
            ('UNKNOWN', 'Unknown'),
        ],
        help_text='Filter by occupancy status'
    )
    
    is_anchor = BooleanFilter(
        field_name='is_anchor',
        help_text='Filter by anchor tenant status'
    )
    
    anchor_only = BooleanFilter(
        method='filter_anchor_only',
        help_text='Show only anchor tenants'
    )
    
    # =============================================================================
    # RETAIL CATEGORY FILTERS
    # =============================================================================
    
    retail_category = CharFilter(
        method='filter_retail_category',
        help_text='Filter by retail category (supports multiple via comma separation)'
    )
    
    category_contains = CharFilter(
        method='filter_category_contains',
        help_text='Filter tenants whose categories contain this term'
    )
    
    # =============================================================================
    # BUSINESS TYPE FILTERS
    # =============================================================================
    
    ownership_type = ChoiceFilter(
        field_name='ownership_type',
        choices=[
            ('Franchise', 'Franchise'),
            ('Corporate', 'Corporate'),
            ('Independent', 'Independent'),
        ],
        help_text='Filter by ownership type'
    )
    
    # =============================================================================
    # LEASE AND FINANCIAL FILTERS
    # =============================================================================
    
    min_base_rent = NumberFilter(
        field_name='base_rent',
        lookup_expr='gte',
        help_text='Minimum base rent'
    )
    
    max_base_rent = NumberFilter(
        field_name='base_rent',
        lookup_expr='lte',
        help_text='Maximum base rent'
    )
    
    lease_term_min = NumberFilter(
        field_name='lease_term',
        lookup_expr='gte',
        help_text='Minimum lease term in months'
    )
    
    lease_term_max = NumberFilter(
        field_name='lease_term',
        lookup_expr='lte',
        help_text='Maximum lease term in months'
    )
    
    # Lease expiration analysis
    lease_expires_within = NumberFilter(
        method='filter_lease_expires_within',
        help_text='Filter by leases expiring within X days'
    )
    
    lease_status = ChoiceFilter(
        method='filter_lease_status',
        choices=[
            ('active', 'Active'),
            ('expiring_soon', 'Expiring Soon (< 6 months)'),
            ('expired', 'Expired'),
            ('unknown', 'Unknown/No Date'),
        ],
        help_text='Filter by lease status'
    )
    
    # =============================================================================
    # TEMPORAL FILTERS
    # =============================================================================
    
    created_after = DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text='Filter by creation date'
    )
    
    updated_after = DateFilter(
        field_name='updated_at',
        lookup_expr='gte',
        help_text='Filter by last update date'
    )
    
    lease_commence_after = DateFilter(
        field_name='lease_commence',
        lookup_expr='gte',
        help_text='Filter by lease commencement date'
    )
    
    lease_expire_before = DateFilter(
        field_name='lease_expiration',
        lookup_expr='lte',
        help_text='Filter by lease expiration date'
    )
    
    # =============================================================================
    # MULTI-LOCATION ANALYSIS FILTERS
    # =============================================================================
    
    multi_location = BooleanFilter(
        method='filter_multi_location',
        help_text='Filter tenants with multiple locations'
    )
    
    location_count_min = NumberFilter(
        method='filter_location_count_min',
        help_text='Minimum number of locations for this tenant'
    )
    
    class Meta:
        model = Tenant
        fields = {
            'credit_category': ['exact', 'icontains'],
        }
    
    # =============================================================================
    # CUSTOM FILTER METHODS
    # =============================================================================
    
    def filter_multiple_tenant_names(self, queryset, name, value):
        """Filter by multiple tenant names"""
        if not value:
            return queryset
        
        names = [name.strip() for name in value.split(',') if name.strip()]
        q_objects = models.Q()
        for tenant_name in names:
            q_objects |= models.Q(tenant_name__icontains=tenant_name)
        
        return queryset.filter(q_objects)
    
    def filter_size_category(self, queryset, name, value):
        """Filter by predefined tenant size categories"""
        if not value:
            return queryset
        
        size_ranges = {
            'small': (0, 2000),
            'medium': (2001, 10000), 
            'large': (10001, 50000),
            'anchor': (50001, float('inf'))
        }
        
        if value in size_ranges:
            min_sf, max_sf = size_ranges[value]
            if max_sf == float('inf'):
                return queryset.filter(square_footage__gte=min_sf)
            else:
                return queryset.filter(
                    square_footage__gte=min_sf,
                    square_footage__lte=max_sf
                )
        
        return queryset
    
    def filter_anchor_only(self, queryset, name, value):
        """Filter to show only anchor tenants"""
        if value is True:
            return queryset.filter(is_anchor=True)
        return queryset
    
    def filter_retail_category(self, queryset, name, value):
        """Filter by retail categories (supports multiple categories)"""
        if not value:
            return queryset
        
        categories = [cat.strip() for cat in value.split(',') if cat.strip()]
        
        # Use array overlap filtering for PostgreSQL ArrayField
        q_objects = models.Q()
        for category in categories:
            q_objects |= models.Q(retail_category__contains=[category])
        
        return queryset.filter(q_objects)
    
    def filter_category_contains(self, queryset, name, value):
        """Filter categories containing a specific term"""
        if not value:
            return queryset
        
        # Search within the array field elements
        return queryset.filter(
            retail_category__contains=[value]
        )
    
    def filter_lease_expires_within(self, queryset, name, value):
        """Filter by lease expiring within specified days"""
        if not value:
            return queryset
        
        try:
            days = int(value)
            from django.utils import timezone
            from datetime import timedelta
            
            future_date = timezone.now().date() + timedelta(days=days)
            
            return queryset.filter(
                lease_expiration__isnull=False,
                lease_expiration__lte=future_date,
                lease_expiration__gte=timezone.now().date()
            )
        except (ValueError, TypeError):
            return queryset
    
    def filter_lease_status(self, queryset, name, value):
        """Filter by calculated lease status"""
        if not value:
            return queryset
        
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        six_months = today + timedelta(days=180)
        
        if value == 'active':
            return queryset.filter(
                lease_expiration__isnull=False,
                lease_expiration__gt=six_months
            )
        elif value == 'expiring_soon':
            return queryset.filter(
                lease_expiration__isnull=False,
                lease_expiration__lte=six_months,
                lease_expiration__gte=today
            )
        elif value == 'expired':
            return queryset.filter(
                lease_expiration__isnull=False,
                lease_expiration__lt=today
            )
        elif value == 'unknown':
            return queryset.filter(lease_expiration__isnull=True)
        
        return queryset
    
    def filter_multi_location(self, queryset, name, value):
        """Filter tenants that appear in multiple shopping centers"""
        if value is not True:
            return queryset
        
        # Find tenant names that appear more than once
        multi_location_names = Tenant.objects.values('tenant_name').annotate(
            location_count=models.Count('shopping_center', distinct=True)
        ).filter(location_count__gt=1).values_list('tenant_name', flat=True)
        
        return queryset.filter(tenant_name__in=multi_location_names)
    
    def filter_location_count_min(self, queryset, name, value):
        """Filter by minimum number of locations for tenant"""
        if not value:
            return queryset
        
        try:
            min_count = int(value)
            
            # Subquery to count locations per tenant name
            tenant_location_counts = Tenant.objects.values('tenant_name').annotate(
                location_count=models.Count('shopping_center', distinct=True)
            ).filter(location_count__gte=min_count).values_list('tenant_name', flat=True)
            
            return queryset.filter(tenant_name__in=tenant_location_counts)
            
        except (ValueError, TypeError):
            return queryset


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_filter_choices(model_class, field_name):
    """
    Get distinct values for a field to populate filter choices dynamically.
    
    Useful for populating dropdown filters with actual database values.
    """
    try:
        distinct_values = model_class.objects.exclude(
            **{f'{field_name}__isnull': True}
        ).exclude(
            **{f'{field_name}__exact': ''}
        ).values_list(field_name, flat=True).distinct().order_by(field_name)
        
        return [(value, value) for value in distinct_values if value]
    except Exception:
        return []


def get_shopping_center_filter_stats():
    """Get statistics about filterable shopping center data."""
    from django.db.models import Count, Min, Max, Avg
    
    stats = ShoppingCenter.objects.aggregate(
        total_centers=Count('id'),
        avg_gla=Avg('total_gla'),
        min_gla=Min('total_gla'),
        max_gla=Max('total_gla'),
        avg_quality=Avg('data_quality_score'),
        centers_with_coordinates=Count('id', filter=models.Q(latitude__isnull=False)),
        centers_with_tenants=Count('id', filter=models.Q(tenants__isnull=False))
    )
    
    # Get distinct values for key categorical fields
    stats['distinct_states'] = list(ShoppingCenter.objects.exclude(
        address_state__isnull=True
    ).values_list('address_state', flat=True).distinct())
    
    stats['distinct_center_types'] = list(ShoppingCenter.objects.exclude(
        center_type__isnull=True
    ).values_list('center_type', flat=True).distinct())
    
    return stats


def get_tenant_filter_stats():
    """Get statistics about filterable tenant data."""
    from django.db.models import Count, Min, Max, Avg
    
    stats = Tenant.objects.aggregate(
        total_tenants=Count('id'),
        occupied_tenants=Count('id', filter=models.Q(occupancy_status='OCCUPIED')),
        anchor_tenants=Count('id', filter=models.Q(is_anchor=True)),
        avg_square_footage=Avg('square_footage'),
        min_square_footage=Min('square_footage'),
        max_square_footage=Max('square_footage'),
        avg_base_rent=Avg('base_rent')
    )
    
    # Multi-location analysis
    multi_location_count = Tenant.objects.values('tenant_name').annotate(
        location_count=Count('shopping_center', distinct=True)
    ).filter(location_count__gt=1).count()
    
    stats['multi_location_tenants'] = multi_location_count
    
    return stats


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'ShoppingCenterFilter',
    'TenantFilter', 
    'get_filter_choices',
    'get_shopping_center_filter_stats',
    'get_tenant_filter_stats'
]
