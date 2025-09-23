"""
Properties Admin - Shop Window Backend
Django admin configuration for shopping centers, tenants, and data management.

Provides comprehensive admin interface for:
- Shopping center management with spatial data
- Tenant relationship management  
- Data quality monitoring and flags
- Import batch tracking and review
- Progressive data enrichment workflow
"""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.db import models
from django.forms import TextInput, Textarea
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, Q, Avg
from django.utils import timezone

from .models import (
    ShoppingCenter, 
    Tenant, 
    DataQualityFlag,
    TenantCategoryTaxonomy
)
from imports.models import ImportBatch  # <- Import from correct app

# =============================================================================
# CUSTOM ADMIN FILTERS
# =============================================================================

class DataQualityFilter(SimpleListFilter):
    """Filter shopping centers by data quality score ranges"""
    title = 'Data Quality'
    parameter_name = 'quality'
    
    def lookups(self, request, model_admin):
        return (
            ('high', 'High Quality (80-100%)'),
            ('medium', 'Medium Quality (50-79%)'),
            ('low', 'Low Quality (0-49%)'),
            ('incomplete', 'Incomplete (<50% fields)'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'high':
            return queryset.filter(data_quality_score__gte=80)
        elif self.value() == 'medium':
            return queryset.filter(data_quality_score__gte=50, data_quality_score__lt=80)
        elif self.value() == 'low':
            return queryset.filter(data_quality_score__lt=50)
        elif self.value() == 'incomplete':
            return queryset.filter(data_quality_score__lt=50)
        return queryset


class CenterTypeFilter(SimpleListFilter):
    """Filter shopping centers by calculated center type"""
    title = 'Center Type'
    parameter_name = 'center_type'
    
    def lookups(self, request, model_admin):
        # Get actual center types from database
        center_types = ShoppingCenter.objects.exclude(
            center_type__isnull=True
        ).values_list('center_type', flat=True).distinct()
        
        return [(ct, ct) for ct in center_types if ct]
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(center_type=self.value())
        return queryset


class HasLocationFilter(SimpleListFilter):
    """Filter shopping centers by geocoding status"""
    title = 'Location Data'
    parameter_name = 'has_location'
    
    def lookups(self, request, model_admin):
        return (
            ('yes', 'Has Coordinates'),
            ('no', 'Missing Coordinates'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(latitude__isnull=False, longitude__isnull=False)
        elif self.value() == 'no':
            return queryset.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True))
        return queryset


# =============================================================================
# INLINE ADMIN CLASSES
# =============================================================================

class TenantInline(admin.TabularInline):
    """Inline editing of tenants within shopping center admin"""
    model = Tenant
    extra = 0
    min_num = 0
    
    fields = [
        'tenant_name', 
        'tenant_suite_number', 
        'square_footage',
        'occupancy_status',
        'is_anchor',
        'retail_category'
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    # Custom form field sizing
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '20'})},
    }


class DataQualityFlagInline(admin.TabularInline):
    """Inline editing of data quality flags"""
    model = DataQualityFlag
    extra = 0
    
    fields = [
        'flag_type',
        'severity', 
        'field_name',
        'message',
        'is_resolved'
    ]
    
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        # Show unresolved flags first
        return super().get_queryset(request).order_by('is_resolved', '-severity', '-created_at')


# =============================================================================
# MAIN ADMIN CLASSES
# =============================================================================

@admin.register(ShoppingCenter)
class ShoppingCenterAdmin(GISModelAdmin):
    """
    Admin interface for shopping centers with spatial data support.
    
    Features:
    - Map widget for lat/lng editing
    - Comprehensive filtering and search
    - Data quality monitoring
    - Progressive enrichment workflow
    - Bulk actions for data management
    """
    
    # List display configuration
    list_display = [
        'shopping_center_name',
        'address_city',
        'address_state',
        'center_type',
        'total_gla',
        'tenant_count',
        'quality_score_display',
        'has_location_display',
        'last_updated'
    ]
    
    list_filter = [
        DataQualityFilter,
        CenterTypeFilter,
        HasLocationFilter,
        'address_state',
        'address_city',
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'shopping_center_name',
        'address_street',
        'address_city',
        'owner',
        'property_manager',
        'leasing_agent'
    ]
    
    readonly_fields = [
        'id',
        'created_at', 
        'updated_at',
        'data_quality_score',
        'calculated_gla',
        'import_batch',
        'last_import_batch'
    ]
    
    # Fieldset organization for progressive data philosophy
    fieldsets = (
        ('Identity', {
            'fields': ('id', 'shopping_center_name'),
            'classes': ('wide',)
        }),
        
        ('EXTRACT Fields (From Imports)', {
            'fields': (
                'address_street',
                'address_city', 
                'address_state',
                'address_zip',
                'contact_name',
                'contact_phone',
                'total_gla'
            ),
            'classes': ('wide',),
            'description': 'Fields automatically extracted from PDFs/CSVs'
        }),
        
        ('DETERMINE Fields (Calculated)', {
            'fields': (
                'center_type',
                'latitude',
                'longitude', 
                'calculated_gla'
            ),
            'classes': ('wide',),
            'description': 'Fields calculated via business logic and geocoding'
        }),
        
        ('DEFINE Fields (Manual Entry)', {
            'fields': (
                'county',
                'municipality',
                'zoning_authority',
                'year_built',
                'owner',
                'property_manager',
                'leasing_agent',
                'leasing_brokerage'
            ),
            'classes': ('wide',),
            'description': 'Fields requiring manual data entry and research'
        }),
        
        ('System Metadata', {
            'fields': (
                'data_quality_score',
                'import_batch',
                'last_import_batch',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',),
            'description': 'System-generated tracking information'
        })
    )
    
    # Inline editing
    inlines = [TenantInline, DataQualityFlagInline]
    
    # Map configuration for spatial editing
    default_lat = 39.8283  # Geographic center of USA
    default_lon = -98.5795
    default_zoom = 4
    map_width = 800
    map_height = 400
    
    # Pagination
    list_per_page = 25
    list_max_show_all = 100
    
    # Custom admin methods
    def tenant_count(self, obj):
        """Display count of tenants for this shopping center"""
        count = obj.tenants.count()
        if count > 0:
            url = reverse('admin:properties_tenant_changelist') + f'?shopping_center__id__exact={obj.id}'
            return format_html('<a href="{}">{} tenants</a>', url, count)
        return '0 tenants'
    tenant_count.short_description = 'Tenants'
    tenant_count.admin_order_field = 'tenant_count'
    
    def quality_score_display(self, obj):
        """Display data quality score with color coding"""
        score = obj.data_quality_score or 0
        if score >= 80:
            color = 'green'
        elif score >= 50:
            color = 'orange'  
        else:
            color = 'red'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.0f}%</span>',
            color, score
        )
    quality_score_display.short_description = 'Quality'
    quality_score_display.admin_order_field = 'data_quality_score'
    
    def has_location_display(self, obj):
        """Display geocoding status with icons"""
        if obj.latitude and obj.longitude:
            return format_html('<span style="color: green;">📍 Located</span>')
        else:
            return format_html('<span style="color: red;">❌ Missing</span>')
    has_location_display.short_description = 'Location'
    
    def last_updated(self, obj):
        """Display last updated timestamp in friendly format"""
        from django.utils.timesince import timesince
        return f"{timesince(obj.updated_at)} ago"
    last_updated.short_description = 'Last Updated'
    last_updated.admin_order_field = 'updated_at'
    
    def get_queryset(self, request):
        """Optimize queryset with annotations for list display"""
        return super().get_queryset(request).annotate(
            tenant_count=Count('tenants')
        ).select_related('import_batch', 'last_import_batch')
    
    # Bulk actions
    actions = ['recalculate_quality_scores', 'geocode_missing_coordinates', 'export_to_csv']
    
    def recalculate_quality_scores(self, request, queryset):
        """Bulk action to recalculate data quality scores"""
        updated_count = 0
        for center in queryset:
            old_score = center.data_quality_score
            # Trigger recalculation by saving
            center.save()
            if center.data_quality_score != old_score:
                updated_count += 1
        
        self.message_user(request, f'Recalculated quality scores for {updated_count} shopping centers.')
    recalculate_quality_scores.short_description = 'Recalculate quality scores'
    
    def geocode_missing_coordinates(self, request, queryset):
        """Bulk action to geocode shopping centers missing coordinates"""
        # Note: This would need actual geocoding service implementation
        missing_coords = queryset.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True))
        geocoded_count = 0
        
        for center in missing_coords[:10]:  # Limit to 10 to avoid API limits
            if center.address_street and center.address_city:
                try:
                    # Placeholder for actual geocoding implementation
                    # from services.geocoding import geocode_address
                    # full_address = f"{center.address_street}, {center.address_city}, {center.address_state} {center.address_zip}"
                    # lat, lng = geocode_address(full_address)
                    # center.latitude = lat
                    # center.longitude = lng
                    # center.save(update_fields=['latitude', 'longitude'])
                    # geocoded_count += 1
                    pass
                except Exception:
                    continue
        
        self.message_user(request, f'Geocoding service would process {missing_coords.count()} centers (placeholder).')
    geocode_missing_coordinates.short_description = 'Geocode missing coordinates (max 10)'


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """
    Admin interface for tenants with relationship management.
    
    Features:
    - Multi-location tenant support
    - Lease information management
    - Retail category taxonomy
    - Occupancy status tracking
    """
    
    list_display = [
        'tenant_name',
        'shopping_center',
        'tenant_suite_number',
        'square_footage',
        'occupancy_status',
        'is_anchor',
        'retail_categories_display',
        'lease_status'
    ]
    
    list_filter = [
        'occupancy_status',
        'is_anchor',
        'retail_category',
        'ownership_type',
        'shopping_center__address_state',
        'created_at'
    ]
    
    search_fields = [
        'tenant_name',
        'shopping_center__shopping_center_name',
        'tenant_suite_number'
    ]
    
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Tenant Identity', {
            'fields': ('tenant_name', 'shopping_center', 'tenant_suite_number'),
        }),
        
        ('Space Details', {
            'fields': ('square_footage', 'occupancy_status', 'is_anchor'),
        }),
        
        ('Business Information', {
            'fields': ('retail_category', 'ownership_type'),
        }),
        
        ('Lease Information', {
            'fields': (
                'base_rent',
                'lease_term',
                'lease_commence',
                'lease_expiration',
                'credit_category'
            ),
            'classes': ('collapse',),
        }),
        
        ('System Info', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        })
    )
    
    # Custom admin methods
    def retail_categories_display(self, obj):
        """Display retail categories as comma-separated list"""
        if obj.retail_category:
            categories = obj.retail_category[:3]  # Show first 3
            display = ', '.join(categories)
            if len(obj.retail_category) > 3:
                display += f' (+{len(obj.retail_category)-3} more)'
            return display
        return '-'
    retail_categories_display.short_description = 'Categories'
    
    def lease_status(self, obj):
        """Display lease status with color coding"""
        if obj.lease_expiration:
            from django.utils import timezone
            from datetime import timedelta
            
            days_until_expiry = (obj.lease_expiration - timezone.now().date()).days
            
            if days_until_expiry < 0:
                return format_html('<span style="color: red;">Expired</span>')
            elif days_until_expiry < 180:  # Less than 6 months
                return format_html('<span style="color: orange;">Expires Soon</span>')
            else:
                return format_html('<span style="color: green;">Active</span>')
        
        return '-'
    lease_status.short_description = 'Lease Status'


@admin.register(DataQualityFlag)
class DataQualityFlagAdmin(admin.ModelAdmin):
    """Admin interface for data quality monitoring"""
    
    list_display = [
        'content_type',
        'object_id', 
        'flag_type',
        'severity',
        'field_name',
        'message_preview',
        'is_resolved',
        'created_at'
    ]
    
    list_filter = [
        'flag_type',
        'severity',
        'is_resolved',
        'content_type',
        'created_at'
    ]
    
    search_fields = ['message', 'field_name']
    
    readonly_fields = ['content_type', 'object_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Flag Details', {
            'fields': ('content_type', 'object_id', 'flag_type', 'severity'),
        }),
        
        ('Issue Description', {
            'fields': ('field_name', 'message'),
        }),
        
        ('Resolution', {
            'fields': ('is_resolved', 'resolved_by', 'resolved_at', 'resolution_notes'),
        }),
        
        ('System Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        })
    )
    
    actions = ['mark_resolved', 'mark_unresolved']
    
    def message_preview(self, obj):
        """Display truncated message for list view"""
        if len(obj.message) > 50:
            return f"{obj.message[:50]}..."
        return obj.message
    message_preview.short_description = 'Message'
    
    def mark_resolved(self, request, queryset):
        updated = queryset.update(
            is_resolved=True, 
            resolved_by=request.user,
            resolved_at=timezone.now()
        )
        self.message_user(request, f'Marked {updated} flags as resolved.')
    mark_resolved.short_description = 'Mark selected flags as resolved'
    
    def mark_unresolved(self, request, queryset):
        updated = queryset.update(
            is_resolved=False,
            resolved_by=None,
            resolved_at=None
        )
        self.message_user(request, f'Marked {updated} flags as unresolved.')
    mark_unresolved.short_description = 'Mark selected flags as unresolved'


@admin.register(TenantCategoryTaxonomy)
class TenantCategoryTaxonomyAdmin(admin.ModelAdmin):
    """Admin interface for managing tenant category taxonomy"""
    
    list_display = ['category_name_display', 'parent_category', 'icsc_code', 'subcategory_count']
    list_filter = ['parent_category']
    search_fields = ['category_name', 'icsc_code', 'description']
    
    fieldsets = (
        (None, {
            'fields': ('category_name', 'parent_category', 'icsc_code', 'description')
        }),
    )
    
    def category_name_display(self, obj):
        """Display category with indentation for hierarchy"""
        depth = obj.get_depth_level()
        indent = '—' * depth
        return f"{indent} {obj.category_name}" if depth > 0 else obj.category_name
    category_name_display.short_description = 'Category Name'
    
    def subcategory_count(self, obj):
        """Display count of direct subcategories"""
        count = obj.subcategories.count()
        return f"{count} subcategories" if count > 0 else "No subcategories"
    subcategory_count.short_description = 'Subcategories'


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    """Admin interface for import batch tracking and review"""
    
    list_display = [
        'batch_id',
        'import_type',
        'status',
        'file_name',
        'records_processed',
        'success_rate',
        'created_at',
        'created_by'
    ]
    
    list_filter = [
        'import_type',
        'status', 
        'created_at'
    ]
    
    readonly_fields = [
        'batch_id',
        'created_at',
        'updated_at',
        'started_at',
        'completed_at'
    ]
    
    def success_rate(self, obj):
        """Calculate and display import success rate"""
        if obj.records_total > 0:
            rate = ((obj.records_created + obj.records_updated) / obj.records_total) * 100
            return f"{rate:.1f}%"
        return "-"
    success_rate.short_description = 'Success Rate'


# =============================================================================
# ADMIN SITE CUSTOMIZATION
# =============================================================================

# Customize admin site headers
admin.site.site_header = 'Shop Window Administration'
admin.site.site_title = 'Shop Window Admin' 
admin.site.index_title = 'Retail CRE Data Management'

# Custom admin CSS and JavaScript
class AdminConfig:
    """Custom admin configuration"""
    
    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)
        }
        js = ('admin/js/custom_admin.js',)


# =============================================================================
# ADMIN UTILITIES AND HELPERS
# =============================================================================

def get_admin_stats():
    """Return admin dashboard statistics"""
    return {
        'shopping_centers': ShoppingCenter.objects.count(),
        'tenants': Tenant.objects.count(), 
        'import_batches': ImportBatch.objects.count(),
        'quality_flags': DataQualityFlag.objects.filter(is_resolved=False).count(),
        'geocoded_properties': ShoppingCenter.objects.filter(
            latitude__isnull=False, 
            longitude__isnull=False
        ).count()
    }