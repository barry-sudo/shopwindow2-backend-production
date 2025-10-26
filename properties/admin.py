"""
Properties Admin - Shop Window Backend
Django admin configuration for shopping centers and tenants.

Simplified version focusing on core data management.
"""

from django.contrib import admin
from django.db import models
from django.forms import TextInput
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Count

from .models import ShoppingCenter, Tenant


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
        'retail_category'
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    # Custom form field sizing
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '20'})},
    }


# =============================================================================
# MAIN ADMIN CLASSES
# =============================================================================

@admin.register(ShoppingCenter)
class ShoppingCenterAdmin(admin.ModelAdmin):
    """
    Admin interface for shopping centers.
    
    Features:
    - Comprehensive filtering and search
    - Inline tenant editing
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
        'has_coordinates',
        'last_updated'
    ]
    
    list_filter = [
        'address_state',
        'address_city',
        'center_type',
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
        'updated_at'
    ]
    
    # Fieldset organization
    fieldsets = (
        ('Identity', {
            'fields': ('id', 'shopping_center_name'),
            'classes': ('wide',)
        }),
        
        ('Address', {
            'fields': (
                'address_street',
                'address_city', 
                'address_state',
                'address_zip'
            ),
            'classes': ('wide',)
        }),
        
        ('Location Details', {
            'fields': (
                'county',
                'municipality',
                'latitude',
                'longitude'
            ),
            'classes': ('wide',)
        }),
        
        ('Property Details', {
            'fields': (
                'total_gla',
                'center_type',
                'year_built'
            ),
            'classes': ('wide',)
        }),
        
        ('Ownership and Management', {
            'fields': (
                'owner',
                'property_manager',
                'leasing_agent',
                'leasing_brokerage'
            ),
            'classes': ('wide',)
        }),
        
        ('System Metadata', {
            'fields': (
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        })
    )
    
    # Inline editing
    inlines = [TenantInline]
    
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
    
    def has_coordinates(self, obj):
        """Display geocoding status"""
        if obj.latitude and obj.longitude:
            return format_html('<span style="color: green;">✓</span>')
        else:
            return format_html('<span style="color: red;">✗</span>')
    has_coordinates.short_description = 'Coords'
    
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
        )


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """
    Admin interface for tenants with relationship management.
    
    Features:
    - Multi-location tenant support
    - Lease information management
    - Retail category tracking
    """
    
    list_display = [
        'tenant_name',
        'shopping_center',
        'tenant_suite_number',
        'square_footage',
        'retail_category',
        'lease_expiration',
        'rent_display'
    ]
    
    list_filter = [
        'retail_category',
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
            'fields': ('square_footage', 'retail_category'),
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
        
        ('Additional Info', {
            'fields': ('categories',),
            'classes': ('collapse',),
        }),
        
        ('System Info', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        })
    )
    
    # Custom admin methods
    def rent_display(self, obj):
        """Display base rent formatted"""
        if obj.base_rent:
            return f"${obj.base_rent:,.2f}"
        return '-'
    rent_display.short_description = 'Base Rent'
    rent_display.admin_order_field = 'base_rent'


# =============================================================================
# ADMIN SITE CUSTOMIZATION
# =============================================================================

# Customize admin site headers
admin.site.site_header = 'Shop Window Administration'
admin.site.site_title = 'Shop Window Admin' 
admin.site.index_title = 'Retail CRE Data Management'
