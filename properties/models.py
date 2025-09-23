"""
Properties models for Shop Window application.

This module implements the core business entities for retail commercial real estate:
- ShoppingCenter: Properties with progressive data enrichment
- Tenant: Retail businesses within shopping centers
- DataQualityFlag: Data quality monitoring and issue tracking
- TenantCategoryTaxonomy: Standardized retail category classification

Business Rules Implemented:
- Shopping centers are UNIQUE by name (core business rule)
- Tenants can exist in multiple shopping centers (chain operations)
- Progressive data enrichment: EXTRACT → DETERMINE → DEFINE
- Non-blocking validation with data quality scoring
- Spatial database integration with PostGIS
"""

from django.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields import ArrayField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.gis.geos import Point
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# SHOPPING CENTER MODEL
# =============================================================================

class ShoppingCenter(models.Model):
    """
    Shopping center entity with progressive data enrichment.
    
    Data Philosophy:
    - EXTRACT fields: Direct from CSV/PDF imports (46% of fields)
    - DETERMINE fields: Calculated via business logic (8% of fields)  
    - DEFINE fields: Manual entry expected (42% of fields)
    
    Business Rules:
    - Shopping centers are UNIQUE by name
    - All fields optional except name and timestamps
    - Quality scoring 0-100 based on field completeness
    - Automatic geocoding for address → coordinates
    """
    
    # =============================================================================
    # IDENTITY FIELDS (Required)
    # =============================================================================
    
    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # =============================================================================
    # EXTRACT FIELDS (From CSV/PDF imports)
    # =============================================================================
    
    shopping_center_name = models.CharField(
        max_length=255, 
        unique=True,  # BUSINESS RULE: Unique constraint
        db_index=True,
        help_text="Unique identifier for the shopping center"
    )
    
    # Address Components
    address_street = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Street address (e.g., '1371 Wilmington Pike')"
    )
    address_city = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="City name"
    )
    address_state = models.CharField(
        max_length=2, 
        blank=True, 
        null=True,
        help_text="Two-letter state code (e.g., 'PA')"
    )
    address_zip = models.CharField(
        max_length=10, 
        blank=True, 
        null=True,
        help_text="ZIP code (5 or 9 digit format)"
    )
    
    # Contact Information
    contact_name = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="Primary contact person"
    )
    contact_phone = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Contact phone number"
    )
    
    # Property Specifications
    total_gla = models.IntegerField(
        blank=True, 
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Total Gross Leasable Area in square feet"
    )
    
    # =============================================================================
    # DETERMINE FIELDS (Calculated via business logic)
    # =============================================================================
    
    center_type = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        choices=[
            ('Strip/Convenience', 'Strip/Convenience (<30k SF)'),
            ('Neighborhood Center', 'Neighborhood Center (30k-125k SF)'),
            ('Community Center', 'Community Center (125k-400k SF)'),
            ('Regional Mall', 'Regional Mall (400k-800k SF)'),
            ('Super-Regional Mall', 'Super-Regional Mall (>800k SF)'),
        ],
        help_text="Calculated from GLA using ICSC standards"
    )
    
    # PostGIS Spatial Fields
    location = gis_models.PointField(
        blank=True, 
        null=True, 
        srid=4326,  # WGS84 coordinate system
        help_text="PostGIS Point field for spatial queries"
    )
    latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        blank=True, 
        null=True,
        help_text="Latitude coordinate (geocoded from address)"
    )
    longitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        blank=True, 
        null=True,
        help_text="Longitude coordinate (geocoded from address)"
    )
    
    # Calculated Fields
    calculated_gla = models.IntegerField(
        blank=True, 
        null=True,
        help_text="Sum of tenant square footage if total_gla missing"
    )
    
    # =============================================================================
    # DEFINE FIELDS (Manual entry expected)
    # =============================================================================
    
    # Location Details
    county = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="County for regulatory and sorting purposes"
    )
    municipality = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Municipality for zoning and regulations"
    )
    zoning_authority = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="Zoning authority or planning commission"
    )
    
    # Property Details
    year_built = models.IntegerField(
        blank=True, 
        null=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2100)],
        help_text="Year the shopping center was constructed"
    )
    
    # Ownership and Management
    owner = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Property owner or ownership entity"
    )
    property_manager = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Property management company"
    )
    leasing_agent = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Leasing agent name"
    )
    leasing_brokerage = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Leasing brokerage company"
    )
    
    # =============================================================================
    # METADATA FIELDS
    # =============================================================================
    
    data_quality_score = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Data completeness score (0-100)"
    )
    
    import_batch = models.ForeignKey(
        'imports.ImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Import batch that created this record"
    )
    
    last_import_batch = models.ForeignKey(
        'imports.ImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_updated_centers',
        help_text="Most recent import batch that updated this record"
    )
    
    # =============================================================================
    # MODEL METHODS
    # =============================================================================
    
    def save(self, *args, **kwargs):
        """
        Custom save method to auto-calculate DETERMINE fields.
        
        Automatically calculates:
        - center_type from total_gla using ICSC standards
        - data_quality_score based on field completeness
        - PostGIS Point from latitude/longitude coordinates
        """
        # Calculate center type from GLA
        if self.total_gla and not self.center_type:
            self.center_type = self._calculate_center_type()
        
        # Update PostGIS Point field from lat/lng
        if self.latitude and self.longitude and not self.location:
            self.location = Point(float(self.longitude), float(self.latitude))
        
        # Calculate data quality score
        self.data_quality_score = self._calculate_quality_score()
        
        # Update timestamp
        self.updated_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def _calculate_center_type(self):
        """Calculate center type from GLA using ICSC standards."""
        if not self.total_gla:
            return None
        
        gla = self.total_gla
        if gla < 30000:
            return "Strip/Convenience"
        elif gla <= 125000:
            return "Neighborhood Center"
        elif gla <= 400000:
            return "Community Center"
        elif gla <= 800000:
            return "Regional Mall"
        else:
            return "Super-Regional Mall"
    
    def _calculate_quality_score(self):
        """
        Calculate data quality score based on field completeness.
        
        Scoring weights:
        - EXTRACT fields: 40%
        - DETERMINE fields: 20%
        - DEFINE fields: 40%
        """
        total_weight = 0
        completed_weight = 0
        
        # EXTRACT fields (40% weight)
        extract_fields = [
            (self.shopping_center_name, 3),  # Required field, higher weight
            (self.address_street, 2),
            (self.address_city, 1.5),
            (self.address_state, 1),
            (self.address_zip, 1),
            (self.contact_name, 1),
            (self.contact_phone, 1),
            (self.total_gla, 2),
        ]
        
        for field_value, weight in extract_fields:
            total_weight += weight
            if field_value:
                completed_weight += weight
        
        # DETERMINE fields (20% weight)
        determine_fields = [
            (self.center_type, 1.5),
            (self.latitude and self.longitude, 2),
            (self.calculated_gla, 1),
        ]
        
        for field_value, weight in determine_fields:
            total_weight += weight
            if field_value:
                completed_weight += weight
        
        # DEFINE fields (40% weight)
        define_fields = [
            (self.owner, 2),
            (self.property_manager, 2),
            (self.county, 1),
            (self.municipality, 1),
            (self.year_built, 1.5),
            (self.leasing_agent, 1),
            (self.leasing_brokerage, 1),
            (self.zoning_authority, 1),
        ]
        
        for field_value, weight in define_fields:
            total_weight += weight
            if field_value:
                completed_weight += weight
        
        # Bonus for tenant data
        if self.tenants.exists():
            total_weight += 2
            completed_weight += 2
        
        # Calculate percentage
        if total_weight > 0:
            return min(int((completed_weight / total_weight) * 100), 100)
        return 0
    
    def get_tenant_count(self):
        """Get total number of tenants in this shopping center."""
        return self.tenants.count()
    
    def get_occupied_tenant_count(self):
        """Get number of occupied tenant spaces."""
        return self.tenants.filter(occupancy_status='OCCUPIED').count()
    
    def get_vacancy_rate(self):
        """Calculate vacancy rate as percentage."""
        total_tenants = self.get_tenant_count()
        if total_tenants == 0:
            return None
        
        occupied = self.get_occupied_tenant_count()
        return round(((total_tenants - occupied) / total_tenants) * 100, 1)
    
    def get_full_address(self):
        """Get formatted full address string."""
        address_parts = [
            self.address_street,
            self.address_city,
            self.address_state,
            self.address_zip
        ]
        return ', '.join([part for part in address_parts if part])
    
    # =============================================================================
    # MODEL CONFIGURATION
    # =============================================================================
    
    class Meta:
        db_table = 'shopping_centers'
        ordering = ['shopping_center_name']
        verbose_name = 'Shopping Center'
        verbose_name_plural = 'Shopping Centers'
        
        indexes = [
            # Core business queries
            models.Index(fields=['shopping_center_name']),
            models.Index(fields=['address_city', 'address_state']),
            models.Index(fields=['center_type']),
            models.Index(fields=['data_quality_score']),
            
            # Import tracking
            models.Index(fields=['import_batch']),
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
            
            # Spatial queries (PostGIS will create spatial index automatically)
        ]
        
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_gla__gte=0),
                name='positive_total_gla'
            ),
            models.CheckConstraint(
                check=models.Q(data_quality_score__gte=0, data_quality_score__lte=100),
                name='valid_quality_score'
            ),
        ]
    
    def __str__(self):
        return self.shopping_center_name
    
    def __repr__(self):
        return f"<ShoppingCenter: {self.shopping_center_name}>"


# =============================================================================
# TENANT MODEL  
# =============================================================================

class Tenant(models.Model):
    """
    Tenant entity representing retail businesses within shopping centers.
    
    Business Rules:
    - Tenants can exist in multiple shopping centers (chain operations)
    - Each tenant-location combination is a unique record
    - Suite numbers must be unique within a shopping center
    - Support for multi-category retail classification
    """
    
    # =============================================================================
    # IDENTITY FIELDS
    # =============================================================================
    
    id = models.AutoField(primary_key=True)
    shopping_center = models.ForeignKey(
        ShoppingCenter,
        on_delete=models.CASCADE,
        related_name='tenants',
        help_text="Shopping center where this tenant is located"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # =============================================================================
    # EXTRACT FIELDS (From imports)
    # =============================================================================
    
    tenant_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Business name (can appear in multiple centers)"
    )
    tenant_suite_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Suite/unit number within the shopping center"
    )
    square_footage = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Leased square footage"
    )
    
    # =============================================================================
    # DEFINE FIELDS (Manual entry)
    # =============================================================================
    
    # Business Classification
    retail_category = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        null=True,
        default=list,
        help_text="Multiple retail categories (e.g., ['Restaurant', 'Fast Food'])"
    )
    ownership_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ('FRANCHISE', 'Franchise'),
            ('CORPORATE', 'Corporate'),
            ('INDEPENDENT', 'Independent'),
            ('CHAIN', 'Chain'),
        ],
        help_text="Business ownership structure"
    )
    
    # Lease Terms
    base_rent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Base rent amount"
    )
    lease_term = models.IntegerField(
        blank=True,
        null=True,
        help_text="Lease term in months"
    )
    lease_commence = models.DateField(
        blank=True,
        null=True,
        help_text="Lease commencement date"
    )
    lease_expiration = models.DateField(
        blank=True,
        null=True,
        help_text="Lease expiration date"
    )
    
    # Credit and Risk Assessment
    credit_category = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ('AAA', 'AAA - Excellent Credit'),
            ('AA', 'AA - Very Good Credit'),
            ('A', 'A - Good Credit'),
            ('BBB', 'BBB - Fair Credit'),
            ('BB', 'BB - Below Average Credit'),
            ('B', 'B - Poor Credit'),
            ('UNKNOWN', 'Unknown Credit Rating'),
        ],
        help_text="Credit rating category"
    )
    
    # =============================================================================
    # STATUS FIELDS
    # =============================================================================
    
    is_anchor = models.BooleanField(
        default=False,
        help_text="Is this tenant an anchor tenant?"
    )
    occupancy_status = models.CharField(
        max_length=20,
        choices=[
            ('OCCUPIED', 'Occupied'),
            ('VACANT', 'Vacant'),
            ('PENDING', 'Pending'),
            ('UNKNOWN', 'Unknown'),
        ],
        default='UNKNOWN',
        help_text="Current occupancy status"
    )
    
    # =============================================================================
    # MODEL METHODS
    # =============================================================================
    
    def save(self, *args, **kwargs):
        """Custom save method with business logic."""
        # Auto-detect vacancy from tenant name
        if self.tenant_name and 'vacant' in self.tenant_name.lower():
            self.occupancy_status = 'VACANT'
        elif self.occupancy_status == 'UNKNOWN' and self.tenant_name:
            self.occupancy_status = 'OCCUPIED'
        
        # Generate suite number if missing
        if not self.tenant_suite_number:
            # Use a simple counter or generate based on existing tenants
            tenant_count = self.shopping_center.tenants.count()
            self.tenant_suite_number = f'UNIT_{tenant_count + 1}'
        
        super().save(*args, **kwargs)
        
        # Update shopping center's calculated GLA if needed
        if self.shopping_center.total_gla is None:
            self._update_shopping_center_calculated_gla()
    
    def _update_shopping_center_calculated_gla(self):
        """Update shopping center's calculated GLA from tenant square footage."""
        from django.db.models import Sum
        
        total_sf = self.shopping_center.tenants.aggregate(
            total=Sum('square_footage')
        )['total']
        
        if total_sf:
            self.shopping_center.calculated_gla = total_sf
            self.shopping_center.save()
    
    def get_rent_per_sq_ft(self):
        """Calculate rent per square foot if data available."""
        if self.base_rent and self.square_footage:
            return round(float(self.base_rent) / self.square_footage, 2)
        return None
    
    def is_lease_expiring_soon(self, months=12):
        """Check if lease expires within specified months."""
        if not self.lease_expiration:
            return None
        
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        warning_date = date.today() + relativedelta(months=months)
        return self.lease_expiration <= warning_date
    
    def get_lease_status(self):
        """Get current lease status based on dates."""
        if not self.lease_commence or not self.lease_expiration:
            return 'UNKNOWN'
        
        from datetime import date
        today = date.today()
        
        if today < self.lease_commence:
            return 'FUTURE'
        elif today > self.lease_expiration:
            return 'EXPIRED'
        else:
            return 'ACTIVE'
    
    # =============================================================================
    # MODEL CONFIGURATION
    # =============================================================================
    
    class Meta:
        db_table = 'tenants'
        ordering = ['shopping_center', 'tenant_suite_number']
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'
        
        # Business rule: Suite numbers unique within a shopping center
        unique_together = [['shopping_center', 'tenant_suite_number']]
        
        indexes = [
            # Core business queries
            models.Index(fields=['tenant_name']),
            models.Index(fields=['shopping_center', 'tenant_name']),
            models.Index(fields=['occupancy_status']),
            models.Index(fields=['is_anchor']),
            
            # Lease management queries
            models.Index(fields=['lease_expiration']),
            models.Index(fields=['lease_commence']),
            
            # Financial queries
            models.Index(fields=['base_rent']),
            models.Index(fields=['square_footage']),
            
            # Category searches
            models.Index(fields=['retail_category']),
            models.Index(fields=['ownership_type']),
        ]
        
        constraints = [
            models.CheckConstraint(
                check=models.Q(square_footage__gte=0),
                name='positive_square_footage'
            ),
            models.CheckConstraint(
                check=models.Q(base_rent__gte=0),
                name='positive_base_rent'
            ),
        ]
    
    def __str__(self):
        suite = f" - {self.tenant_suite_number}" if self.tenant_suite_number else ""
        return f"{self.tenant_name}{suite}"
    
    def __repr__(self):
        return f"<Tenant: {self.tenant_name} @ {self.shopping_center.shopping_center_name}>"


# =============================================================================
# DATA QUALITY FLAG MODEL
# =============================================================================

class DataQualityFlag(models.Model):
    """
    Data quality monitoring and issue tracking system.
    
    Uses Django's generic foreign key to flag issues on any model.
    Supports the progressive data enrichment workflow by identifying
    missing, invalid, or suspicious data that requires attention.
    
    Business Rules:
    - Can be attached to any model (ShoppingCenter, Tenant, etc.)
    - Severity levels determine priority for resolution
    - Flags can be resolved by users with tracking
    - Automatic flagging via data validation processes
    """
    
    # =============================================================================
    # FLAG TYPE CHOICES
    # =============================================================================
    
    FLAG_TYPE_CHOICES = [
        ('MISSING_DATA', 'Missing Required Data'),
        ('INVALID_FORMAT', 'Invalid Data Format'),
        ('SUSPICIOUS_VALUE', 'Suspicious Data Value'), 
        ('DUPLICATE_DETECTED', 'Duplicate Record Detected'),
        ('GEOCODING_FAILED', 'Geocoding Failed'),
        ('CALCULATION_ERROR', 'Calculation Error'),
        ('IMPORT_WARNING', 'Import Process Warning'),
        ('VALIDATION_FAILED', 'Validation Rule Failed'),
        ('INCONSISTENT_DATA', 'Data Inconsistency Detected'),
        ('MANUAL_REVIEW', 'Manual Review Required'),
    ]
    
    SEVERITY_CHOICES = [
        ('LOW', 'Low - Informational'),
        ('MEDIUM', 'Medium - Should Fix'),
        ('HIGH', 'High - Important'),
        ('CRITICAL', 'Critical - Must Fix'),
    ]
    
    # =============================================================================
    # MODEL FIELDS
    # =============================================================================
    
    id = models.AutoField(primary_key=True)
    
    # Generic Foreign Key - can point to any model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Model type this flag applies to"
    )
    object_id = models.PositiveIntegerField(
        help_text="Primary key of the flagged object"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Flag Details
    flag_type = models.CharField(
        max_length=30,
        choices=FLAG_TYPE_CHOICES,
        db_index=True,
        help_text="Type of data quality issue"
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='MEDIUM',
        db_index=True,
        help_text="Severity level for prioritization"
    )
    
    field_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Specific field that has the issue"
    )
    
    message = models.TextField(
        help_text="Detailed description of the data quality issue"
    )
    
    # Resolution Tracking
    is_resolved = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this flag has been resolved"
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_flags',
        help_text="User who resolved this flag"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this flag was resolved"
    )
    resolution_notes = models.TextField(
        blank=True,
        help_text="Notes about how the issue was resolved"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # =============================================================================
    # MODEL METHODS
    # =============================================================================
    
    def mark_resolved(self, user=None, notes=""):
        """Mark this flag as resolved."""
        self.is_resolved = True
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save()
    
    def mark_unresolved(self):
        """Mark this flag as unresolved."""
        self.is_resolved = False
        self.resolved_by = None
        self.resolved_at = None
        self.resolution_notes = ""
        self.save()
    
    def get_severity_display_color(self):
        """Get color for severity display."""
        colors = {
            'LOW': '#28a745',      # Green
            'MEDIUM': '#ffc107',   # Yellow
            'HIGH': '#fd7e14',     # Orange  
            'CRITICAL': '#dc3545'  # Red
        }
        return colors.get(self.severity, '#6c757d')
    
    @classmethod
    def create_flag(cls, content_object, flag_type, severity='MEDIUM', field_name=None, message=""):
        """
        Convenience method to create a data quality flag.
        
        Args:
            content_object: The model instance to flag
            flag_type: Type of flag (from FLAG_TYPE_CHOICES)
            severity: Severity level (from SEVERITY_CHOICES)
            field_name: Specific field with the issue
            message: Detailed description
        
        Returns:
            DataQualityFlag instance
        """
        return cls.objects.create(
            content_object=content_object,
            flag_type=flag_type,
            severity=severity,
            field_name=field_name,
            message=message
        )
    
    # =============================================================================
    # MODEL CONFIGURATION
    # =============================================================================
    
    class Meta:
        db_table = 'data_quality_flags'
        ordering = ['-created_at', '-severity']
        verbose_name = 'Data Quality Flag'
        verbose_name_plural = 'Data Quality Flags'
        
        indexes = [
            # Performance indexes for common queries
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['flag_type', 'severity']),
            models.Index(fields=['is_resolved', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['resolved_by']),
        ]
        
        constraints = [
            # Ensure content_type and object_id are both provided
            models.CheckConstraint(
                check=models.Q(object_id__gt=0),
                name='valid_object_id'
            ),
        ]
    
    def __str__(self):
        model_name = self.content_type.model if self.content_type else "Unknown"
        field_info = f" ({self.field_name})" if self.field_name else ""
        return f"{self.get_flag_type_display()}{field_info} - {model_name} #{self.object_id}"
    
    def __repr__(self):
        return f"<DataQualityFlag: {self.flag_type} - {self.severity}>"


# =============================================================================
# TENANT CATEGORY TAXONOMY MODEL
# =============================================================================

class TenantCategoryTaxonomy(models.Model):
    """
    Standardized retail category classification system.
    
    Implements hierarchical taxonomy for tenant categorization using
    ICSC (International Council of Shopping Centers) standards where applicable.
    
    Business Rules:
    - Hierarchical structure (parent/child categories)
    - ICSC codes for standardization
    - Supports multiple classification levels
    - Used for tenant categorization and analysis
    """
    
    # =============================================================================
    # MODEL FIELDS
    # =============================================================================
    
    id = models.AutoField(primary_key=True)
    
    category_name = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Category name (e.g., 'Restaurants & Food Service')"
    )
    
    parent_category = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories',
        help_text="Parent category for hierarchical structure"
    )
    
    icsc_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="ICSC standard category code"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Detailed description of this category"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # =============================================================================
    # MODEL METHODS
    # =============================================================================
    
    def get_full_category_path(self):
        """Get full hierarchical path (e.g., 'Retail > Apparel > Shoes')."""
        path_parts = [self.category_name]
        current = self.parent_category
        
        while current:
            path_parts.insert(0, current.category_name)
            current = current.parent_category
        
        return ' > '.join(path_parts)
    
    def get_all_children(self):
        """Get all child categories recursively."""
        children = list(self.subcategories.all())
        for child in list(children):
            children.extend(child.get_all_children())
        return children
    
    def is_root_category(self):
        """Check if this is a root-level category."""
        return self.parent_category is None
    
    def get_depth_level(self):
        """Get the depth level in hierarchy (root = 0)."""
        depth = 0
        current = self.parent_category
        while current:
            depth += 1
            current = current.parent_category
        return depth
    
    @classmethod
    def get_root_categories(cls):
        """Get all root-level categories."""
        return cls.objects.filter(parent_category__isnull=True)
    
    @classmethod
    def create_category_hierarchy(cls, category_data):
        """
        Create a hierarchical category structure from nested data.
        
        Args:
            category_data: Dict with category info and optional 'children' list
            
        Example:
            {
                'name': 'Retail',
                'icsc_code': 'R001',
                'description': 'Retail businesses',
                'children': [
                    {
                        'name': 'Apparel',
                        'icsc_code': 'R001-A',
                        'description': 'Clothing stores'
                    }
                ]
            }
        """
        category, created = cls.objects.get_or_create(
            category_name=category_data['name'],
            defaults={
                'icsc_code': category_data.get('icsc_code'),
                'description': category_data.get('description', ''),
            }
        )
        
        # Process children if provided
        if 'children' in category_data:
            for child_data in category_data['children']:
                child_category, child_created = cls.objects.get_or_create(
                    category_name=child_data['name'],
                    defaults={
                        'parent_category': category,
                        'icsc_code': child_data.get('icsc_code'),
                        'description': child_data.get('description', ''),
                    }
                )
                
                # Recursively process nested children
                if 'children' in child_data:
                    child_data_copy = child_data.copy()
                    cls.create_category_hierarchy(child_data_copy)
        
        return category
    
    # =============================================================================
    # MODEL CONFIGURATION
    # =============================================================================
    
    class Meta:
        db_table = 'tenant_category_taxonomy'
        ordering = ['category_name']
        verbose_name = 'Tenant Category'
        verbose_name_plural = 'Tenant Categories'
        
        indexes = [
            models.Index(fields=['category_name']),
            models.Index(fields=['parent_category']),
            models.Index(fields=['icsc_code']),
        ]
        
        constraints = [
            # Prevent self-referential parent categories
            models.CheckConstraint(
                check=~models.Q(id=models.F('parent_category')),
                name='no_self_parent'
            ),
        ]
    
    def __str__(self):
        if self.parent_category:
            return f"{self.parent_category.category_name} > {self.category_name}"
        return self.category_name
    
    def __repr__(self):
        return f"<TenantCategoryTaxonomy: {self.category_name}>"


# =============================================================================
# MODEL SIGNALS AND UTILITIES
# =============================================================================

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Tenant)
def update_shopping_center_on_tenant_save(sender, instance, created, **kwargs):
    """Update shopping center data quality score when tenants are added/updated."""
    instance.shopping_center.save()  # This will recalculate quality score

@receiver(post_delete, sender=Tenant) 
def update_shopping_center_on_tenant_delete(sender, instance, **kwargs):
    """Update shopping center data quality score when tenants are deleted."""
    if hasattr(instance, 'shopping_center') and instance.shopping_center:
        instance.shopping_center.save()  # This will recalculate quality score

@receiver(post_save, sender=ShoppingCenter)
def create_quality_flags_on_shopping_center_save(sender, instance, created, **kwargs):
    """Automatically create data quality flags for new shopping centers."""
    if created:
        # Create flags for missing critical data
        if not instance.address_street:
            DataQualityFlag.create_flag(
                content_object=instance,
                flag_type='MISSING_DATA',
                severity='HIGH',
                field_name='address_street',
                message='Street address is required for geocoding and mapping'
            )
        
        if not instance.total_gla:
            DataQualityFlag.create_flag(
                content_object=instance,
                flag_type='MISSING_DATA', 
                severity='MEDIUM',
                field_name='total_gla',
                message='Total GLA is required for property analysis'
            )


# =============================================================================
# CUSTOM MANAGERS
# =============================================================================

class ShoppingCenterManager(models.Manager):
    """Custom manager for ShoppingCenter with common queries."""
    
    def with_coordinates(self):
        """Get shopping centers that have been geocoded."""
        return self.exclude(latitude__isnull=True, longitude__isnull=True)
    
    def by_quality_score(self, min_score=50):
        """Get shopping centers above minimum quality score."""
        return self.filter(data_quality_score__gte=min_score)
    
    def by_center_type(self, center_type):
        """Get shopping centers by type."""
        return self.filter(center_type=center_type)
    
    def in_city_state(self, city, state):
        """Get shopping centers in specific city and state."""
        return self.filter(address_city__icontains=city, address_state__iexact=state)


class TenantManager(models.Manager):
    """Custom manager for Tenant with common queries."""
    
    def occupied(self):
        """Get only occupied tenants."""
        return self.filter(occupancy_status='OCCUPIED')
    
    def vacant(self):
        """Get only vacant spaces."""
        return self.filter(occupancy_status='VACANT')
    
    def by_category(self, category):
        """Get tenants in specific retail category."""
        return self.filter(retail_category__contains=[category])
    
    def anchor_tenants(self):
        """Get only anchor tenants."""
        return self.filter(is_anchor=True)
    
    def expiring_leases(self, months=12):
        """Get tenants with leases expiring within specified months."""
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        warning_date = date.today() + relativedelta(months=months)
        return self.filter(lease_expiration__lte=warning_date, lease_expiration__gte=date.today())


class DataQualityFlagManager(models.Manager):
    """Custom manager for DataQualityFlag with common queries."""
    
    def unresolved(self):
        """Get only unresolved flags."""
        return self.filter(is_resolved=False)
    
    def by_severity(self, severity):
        """Get flags by severity level."""
        return self.filter(severity=severity)
    
    def critical_flags(self):
        """Get only critical flags."""
        return self.filter(severity='CRITICAL')
    
    def for_model(self, model_class):
        """Get flags for a specific model type."""
        content_type = ContentType.objects.get_for_model(model_class)
        return self.filter(content_type=content_type)
    
    def for_object(self, obj):
        """Get flags for a specific object instance."""
        content_type = ContentType.objects.get_for_model(obj.__class__)
        return self.filter(content_type=content_type, object_id=obj.pk)


# Add custom managers to models
ShoppingCenter.add_to_class('objects', ShoppingCenterManager())
Tenant.add_to_class('objects', TenantManager())
DataQualityFlag.add_to_class('objects', DataQualityFlagManager())