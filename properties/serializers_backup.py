"""
API Serializers for Shop Window Properties - CLEANED VERSION.

This module defines the serialization layer between Django models and REST API.
Only includes fields that actually exist in the models.

Updated: 2025-10-14 to add annual_rent calculated field
"""

from rest_framework import serializers
from django.contrib.gis.geos import Point
from datetime import date
import re
import logging

from .models import ShoppingCenter, Tenant

logger = logging.getLogger(__name__)


# =============================================================================
# TENANT SERIALIZERS
# =============================================================================

class TenantListSerializer(serializers.ModelSerializer):
    """
    Simplified tenant serializer for list views and nested shopping center details.
    """
    
    # Computed fields
    rent_per_sq_ft = serializers.SerializerMethodField()
    annual_rent = serializers.SerializerMethodField()
    lease_status = serializers.SerializerMethodField()
    is_lease_expiring_soon = serializers.SerializerMethodField()
    
    class Meta:
        model = Tenant
        fields = [
            'id',
            'tenant_name',
            'tenant_suite_number', 
            'square_footage',
            'retail_category',
            'ownership_type',
            'base_rent',
            'lease_commence',
            'lease_expiration',
            'rent_per_sq_ft',
            'annual_rent',
            'lease_status',
            'is_lease_expiring_soon',
            'major_group',
        ]
        read_only_fields = ['id', 'rent_per_sq_ft', 'annual_rent', 'lease_status', 'is_lease_expiring_soon']
    
    def get_rent_per_sq_ft(self, obj):
        """Return annual rent per square foot."""
        return obj.get_rent_per_sq_ft()
    
    def get_annual_rent(self, obj):
        """Calculate total annual rent."""
        return obj.get_annual_rent()
    
    def get_lease_status(self, obj):
        """Get current lease status."""
        return obj.get_lease_status()
    
    def get_is_lease_expiring_soon(self, obj):
        """Check if lease expires within 12 months."""
        return obj.is_lease_expiring_soon(months=12)


class TenantDetailSerializer(serializers.ModelSerializer):
    """
    Complete tenant serializer with all fields and computed properties.
    """
    
    # Computed fields
    rent_per_sq_ft = serializers.SerializerMethodField()
    annual_rent = serializers.SerializerMethodField()
    lease_status = serializers.SerializerMethodField()
    is_lease_expiring_soon = serializers.SerializerMethodField()
    shopping_center_name = serializers.CharField(source='shopping_center.shopping_center_name', read_only=True)
    
    class Meta:
        model = Tenant
        fields = [
            'id',
            'shopping_center',
            'shopping_center_name',
            'tenant_name',
            'tenant_suite_number',
            'square_footage',
            'retail_category',
            'ownership_type',
            'base_rent',
            'lease_term',
            'lease_commence',
            'lease_expiration',
            'credit_category',
            'rent_per_sq_ft',
            'annual_rent',
            'lease_status',
            'is_lease_expiring_soon',
            'created_at',
            'updated_at',
            'major_group',
        ]
        read_only_fields = [
            'id', 'shopping_center_name', 'rent_per_sq_ft', 'annual_rent', 'lease_status',
            'is_lease_expiring_soon', 'created_at', 'updated_at'
        ]
    
    def get_rent_per_sq_ft(self, obj):
        """Return annual rent per square foot."""
        return obj.get_rent_per_sq_ft()
    
    def get_annual_rent(self, obj):
        """Calculate total annual rent."""
        return obj.get_annual_rent()
    
    def get_lease_status(self, obj):
        """Get current lease status."""
        return obj.get_lease_status()
    
    def get_is_lease_expiring_soon(self, obj):
        """Check if lease expires within 12 months."""
        return obj.is_lease_expiring_soon(months=12)
    
    def validate(self, data):
        """Custom validation for tenant data."""
        errors = {}
        
        # Validate lease dates
        lease_commence = data.get('lease_commence')
        lease_expiration = data.get('lease_expiration')
        
        if lease_commence and lease_expiration:
            if lease_commence >= lease_expiration:
                errors['lease_expiration'] = "Lease expiration must be after commencement date."
        
        # Validate rent and square footage relationship
        base_rent = data.get('base_rent')
        square_footage = data.get('square_footage')
        
        if base_rent and square_footage:
            # base_rent is now $/SF/year, so sanity check is simpler
            if base_rent > 500:  # $500/SF/year is extremely high for retail
                errors['base_rent'] = "Rent per square foot appears unusually high. Please verify."
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return data


class TenantCreateSerializer(serializers.ModelSerializer):
    """
    Tenant creation serializer with input validation.
    """
    
    class Meta:
        model = Tenant
        fields = [
            'shopping_center',
            'tenant_name',
            'tenant_suite_number',
            'square_footage',
            'retail_category',
            'ownership_type',
            'base_rent',
            'lease_term',
            'lease_commence',
            'lease_expiration',
            'credit_category',
            'major_group',
        ]
    
    def validate_tenant_name(self, value):
        """Validate tenant name."""
        if not value or not value.strip():
            raise serializers.ValidationError("Tenant name cannot be empty.")
        
        cleaned_name = value.strip()
        if len(cleaned_name) < 2:
            raise serializers.ValidationError("Tenant name must be at least 2 characters.")
        
        return cleaned_name
    
    def validate_square_footage(self, value):
        """Validate square footage."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Square footage must be positive.")
        
        if value is not None and value > 1000000:
            raise serializers.ValidationError("Square footage seems unusually large.")
        
        return value
    
    def validate_base_rent(self, value):
        """Validate base rent (annual $/SF)."""
        if value is not None and value < 0:
            raise serializers.ValidationError("Base rent cannot be negative.")
        
        if value is not None and value > 500:
            raise serializers.ValidationError("Base rent per SF seems unusually high (over $500/SF/year).")
        
        return value


# =============================================================================
# SHOPPING CENTER SERIALIZERS
# =============================================================================

class ShoppingCenterListSerializer(serializers.ModelSerializer):
    """
    Shopping center list serializer for map views and property listings.
    
    Optimized for performance with minimal data transfer.
    Includes key fields needed for map markers and property cards.
    """
    
    # Computed fields for frontend display
    tenant_count = serializers.SerializerMethodField()
    vacancy_rate = serializers.SerializerMethodField()
    full_address = serializers.SerializerMethodField()
    
    class Meta:
        model = ShoppingCenter
        fields = [
            'id',
            'shopping_center_name',
            'address_city',
            'address_state',
            'address_zip',
            'center_type',
            'total_gla',
            'latitude',
            'longitude', 
            'tenant_count',
            'vacancy_rate',
            'full_address',
            'owner',
            'property_manager',
            'county',
        ]
        read_only_fields = [
            'id', 'tenant_count', 'vacancy_rate', 'full_address'
        ]
    
    def get_tenant_count(self, obj):
        """Get total number of tenants."""
        return obj.get_tenant_count()
    
    def get_vacancy_rate(self, obj):
        """Get vacancy rate as percentage."""
        return obj.get_vacancy_rate()
    
    def get_full_address(self, obj):
        """Get formatted full address."""
        return obj.get_full_address()


class ShoppingCenterDetailSerializer(serializers.ModelSerializer):
    """
    Complete shopping center serializer with all fields and related data.
    
    Used for individual property detail views with full tenant listings
    and comprehensive property information.
    """
    
    # Related data
    tenants = TenantListSerializer(many=True, read_only=True)
    
    # Computed fields
    tenant_count = serializers.SerializerMethodField()
    occupied_tenant_count = serializers.SerializerMethodField()
    vacancy_rate = serializers.SerializerMethodField()
    full_address = serializers.SerializerMethodField()
    
    # Coordinate fields (for frontend mapping)
    coordinates = serializers.SerializerMethodField()
    
    class Meta:
        model = ShoppingCenter
        fields = [
            'id',
            'shopping_center_name',
            'address_street',
            'address_city', 
            'address_state',
            'address_zip',
            'total_gla',
            'center_type',
            'latitude',
            'longitude',
            'coordinates',
            'county',
            'municipality',
            'zoning_authority',
            'year_built',
            'owner',
            'property_manager',
            'leasing_agent',
            'leasing_brokerage',
            'tenant_count',
            'occupied_tenant_count',
            'vacancy_rate',
            'full_address',
            'tenants',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'latitude', 'longitude', 'coordinates', 'tenant_count', 
            'occupied_tenant_count', 'vacancy_rate', 'full_address', 
            'tenants', 'created_at', 'updated_at'
        ]
    
    def get_tenant_count(self, obj):
        """Get total number of tenants."""
        return obj.get_tenant_count()
    
    def get_occupied_tenant_count(self, obj):
        """Get number of occupied tenants."""
        return obj.get_occupied_tenant_count()
    
    def get_vacancy_rate(self, obj):
        """Get vacancy rate as percentage."""
        return obj.get_vacancy_rate()
    
    def get_full_address(self, obj):
        """Get formatted full address."""
        return obj.get_full_address()
    
    def get_coordinates(self, obj):
        """Get coordinates as [longitude, latitude] array for mapping."""
        if obj.latitude and obj.longitude:
            return [float(obj.longitude), float(obj.latitude)]
        return None


class ShoppingCenterCreateSerializer(serializers.ModelSerializer):
    """
    Shopping center creation serializer with validation and business logic.
    """
    
    # Optional coordinate override
    override_coordinates = serializers.BooleanField(write_only=True, required=False, default=False)
    manual_latitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, write_only=True, required=False, allow_null=True
    )
    manual_longitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, write_only=True, required=False, allow_null=True
    )
    
    class Meta:
        model = ShoppingCenter
        fields = [
            'shopping_center_name',
            'address_street',
            'address_city',
            'address_state', 
            'address_zip',
            'total_gla',
            'center_type',
            'county',
            'municipality',
            'zoning_authority',
            'year_built',
            'owner',
            'property_manager',
            'leasing_agent',
            'leasing_brokerage',
            'override_coordinates',
            'manual_latitude',
            'manual_longitude',
        ]
    
    def validate_shopping_center_name(self, value):
        """Validate shopping center name uniqueness."""
        if not value or not value.strip():
            raise serializers.ValidationError("Shopping center name is required.")
        
        cleaned_name = value.strip()
        
        if ShoppingCenter.objects.filter(
            shopping_center_name__iexact=cleaned_name
        ).exists():
            raise serializers.ValidationError(
                f"Shopping center '{cleaned_name}' already exists."
            )
        
        return cleaned_name
    
    def validate_address_state(self, value):
        """Validate state code format."""
        if value:
            if len(value) != 2:
                raise serializers.ValidationError("State must be a 2-letter code (e.g., 'PA').")
            return value.upper()
        return value
    
    def validate_address_zip(self, value):
        """Validate ZIP code format."""
        if value:
            cleaned_zip = re.sub(r'[^0-9]', '', value)
            
            if not re.match(r'^\d{5}(\d{4})?$', cleaned_zip):
                raise serializers.ValidationError(
                    "ZIP code must be 5 digits (e.g., '19382') or 9 digits."
                )
            
            if len(cleaned_zip) == 9:
                return f"{cleaned_zip[:5]}-{cleaned_zip[5:]}"
            return cleaned_zip
        
        return value
    
    def validate_total_gla(self, value):
        """Validate GLA value."""
        if value is not None:
            if value <= 0:
                raise serializers.ValidationError("Total GLA must be positive.")
            
            if value > 10000000:
                raise serializers.ValidationError("Total GLA seems unusually large.")
        
        return value
    
    def validate_year_built(self, value):
        """Validate year built."""
        if value is not None:
            current_year = date.today().year
            if value < 1800 or value > current_year + 5:
                raise serializers.ValidationError(
                    f"Year built must be between 1800 and {current_year + 5}."
                )
        
        return value
    
    def validate(self, data):
        """Cross-field validation."""
        errors = {}
        
        override_coords = data.get('override_coordinates', False)
        manual_lat = data.get('manual_latitude')
        manual_lng = data.get('manual_longitude')
        
        if override_coords:
            if manual_lat is None or manual_lng is None:
                errors['override_coordinates'] = (
                    "Both manual_latitude and manual_longitude required."
                )
            else:
                if not (-90 <= manual_lat <= 90):
                    errors['manual_latitude'] = "Latitude must be between -90 and 90."
                
                if not (-180 <= manual_lng <= 180):
                    errors['manual_longitude'] = "Longitude must be between -180 and 180."
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return data
    
    def create(self, validated_data):
        """Create shopping center with business logic."""
        override_coordinates = validated_data.pop('override_coordinates', False)
        manual_latitude = validated_data.pop('manual_latitude', None)
        manual_longitude = validated_data.pop('manual_longitude', None)
        
        shopping_center = ShoppingCenter.objects.create(**validated_data)
        
        if override_coordinates and manual_latitude and manual_longitude:
            shopping_center.latitude = manual_latitude
            shopping_center.longitude = manual_longitude
            shopping_center.save()
        else:
            try:
                from services.geocoding import GeocodingService
                geocoding_service = GeocodingService()
                geocoding_service.geocode_shopping_center(shopping_center)
            except Exception as e:
                logger.warning(f"Geocoding failed for {shopping_center.shopping_center_name}: {str(e)}")
        
        return shopping_center


class ShoppingCenterUpdateSerializer(serializers.ModelSerializer):
    """
    Shopping center update serializer for PATCH operations.
    
    Supports progressive data enrichment with validation.
    """
    
    class Meta:
        model = ShoppingCenter
        fields = [
            'address_street',
            'address_city',
            'address_state',
            'address_zip',
            'total_gla',
            'center_type',
            'county',
            'municipality',
            'zoning_authority',
            'year_built',
            'owner',
            'property_manager',
            'leasing_agent',
            'leasing_brokerage',
        ]
    
    def validate_address_state(self, value):
        """Validate state code format."""
        if value:
            if len(value) != 2:
                raise serializers.ValidationError("State must be a 2-letter code.")
            return value.upper()
        return value
    
    def validate_address_zip(self, value):
        """Validate ZIP code format."""
        if value:
            cleaned_zip = re.sub(r'[^0-9]', '', value)
            
            if not re.match(r'^\d{5}(\d{4})?$', cleaned_zip):
                raise serializers.ValidationError("ZIP code must be 5 digits or 9 digits.")
            
            if len(cleaned_zip) == 9:
                return f"{cleaned_zip[:5]}-{cleaned_zip[5:]}"
            return cleaned_zip
        
        return value
    
    def update(self, instance, validated_data):
        """Update with progressive data enrichment logic."""
        for field, value in validated_data.items():
            if value is not None and value != '':
                setattr(instance, field, value)
        
        instance.save()
        
        address_fields = ['address_street', 'address_city', 'address_state', 'address_zip']
        if any(field in validated_data for field in address_fields):
            try:
                from services.geocoding import GeocodingService
                geocoding_service = GeocodingService()
                geocoding_service.geocode_shopping_center(instance)
            except Exception as e:
                logger.warning(f"Re-geocoding failed: {str(e)}")
        
        return instance


# =============================================================================
# SPECIALIZED SERIALIZERS
# =============================================================================

class ShoppingCenterMapSerializer(serializers.ModelSerializer):
    """
    Minimal serializer optimized for map displays.
    """
    
    coordinates = serializers.SerializerMethodField()
    popup_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ShoppingCenter
        fields = [
            'id',
            'shopping_center_name',
            'address_city',
            'address_state',
            'center_type',
            'total_gla',
            'coordinates',
            'popup_info',
        ]
    
    def get_coordinates(self, obj):
        """Get coordinates for mapping."""
        if obj.latitude and obj.longitude:
            return [float(obj.longitude), float(obj.latitude)]
        return None
    
    def get_popup_info(self, obj):
        """Get formatted info for map popup."""
        return {
            'name': obj.shopping_center_name,
            'city': obj.address_city,
            'state': obj.address_state,
            'type': obj.center_type or 'Unknown',
            'gla': f"{obj.total_gla:,}" if obj.total_gla else 'Unknown',
            'tenant_count': obj.get_tenant_count(),
        }
