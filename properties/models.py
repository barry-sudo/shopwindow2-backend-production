"""
Properties models for Shop Window application - Simplified Version.

This module implements the core business entities:
- ShoppingCenter: Commercial real estate properties
- Tenant: Retail businesses within shopping centers

Design Philosophy: Simple, predictable, no automatic behaviors.
Data enrichment (geocoding, calculations) happens as separate processes.
"""

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# TENANT CATEGORIZATION SYSTEM
# =============================================================================

# Tenant Major Group Choices (8 high-level categories for tenant mix analysis)
MAJOR_GROUP_CHOICES = [
    ('anchors_majors', 'Anchors & Majors'),
    ('inline_retail', 'Inline Retail'),
    ('food_beverage', 'Food & Beverage'),
    ('services', 'Services'),
    ('entertainment_leisure', 'Entertainment / Leisure'),
    ('other_nonretail', 'Other / Non-Retail'),
    ('seasonal_popup', 'Seasonal / Pop-Up'),
    ('vacant', 'Vacant'),
]

# Comprehensive Retail Category to Major Group Mapping
# Maps specific retail_category values to their corresponding major_group
# Updated 2025-10-08 with complete corrected taxonomy
RETAIL_CATEGORY_TO_MAJOR_GROUP = {
    # =========================================================================
    # ANCHORS & MAJORS
    # =========================================================================
    'Big Box | Retail': 'anchors_majors',
    'Big Box | Home Improvement': 'anchors_majors',
    'Pharmacy | Anchor': 'anchors_majors',
    'Department Store': 'anchors_majors',
    'Supermarket': 'anchors_majors',
    'Discount Store': 'anchors_majors',
    'Hypermarket': 'anchors_majors',
    'Wholesale Club': 'anchors_majors',
    
    # =========================================================================
    # INLINE RETAIL
    # =========================================================================
    'Apparel (Adult)': 'inline_retail',
    'Apparel (Athletic)': 'inline_retail',
    'Apparel (Activewear)': 'inline_retail',  
    'Apparel (Childrens)': 'inline_retail',
    'Apparel (Discounted)': 'inline_retail',
    'Apparel (Family)': 'inline_retail',
    'Apparel (Maternity)': 'inline_retail',
    'Apparel (Mens)': 'inline_retail',
    'Apparel (Outlet)': 'inline_retail',
    'Apparel (Plus sizes)': 'inline_retail',
    'Apparel (Uniforms)': 'inline_retail',
    'Apparel (Upscale)': 'inline_retail',
    'Apparel (Womens)': 'inline_retail',
    'Art Gallery': 'inline_retail',
    'Art Supplies': 'inline_retail',
    'Auto Parts': 'inline_retail',
    'Bagels': 'inline_retail',
    'Bakery': 'inline_retail',
    'Beauty Supplies': 'inline_retail',
    'Beer Distributor': 'inline_retail',
    'Bookstore': 'inline_retail',
    'Boutique': 'inline_retail',
    'Butcher / Meat Products': 'inline_retail',
    'Cannabis & CBD': 'inline_retail',
    'Cabinetry': 'inline_retail',
    'Camera Store': 'inline_retail',
    'Cards': 'inline_retail',
    'Cigars and Cigarettes': 'inline_retail',
    'Computers': 'inline_retail',
    'Consignment': 'inline_retail',
    'Crafts': 'inline_retail',
    'Electronics': 'inline_retail',
    'Fabrics': 'inline_retail',
    'Farming Supplies': 'inline_retail',
    'Florists': 'inline_retail',
    'Flooring Materials': 'inline_retail',
    'Food or Beverage Specialty': 'inline_retail',
    'Formalwear (Bridal)': 'inline_retail',
    'Formalwear (Tuxedo)': 'inline_retail',
    'Framing & Supplies': 'inline_retail',
    'Furniture': 'inline_retail',
    'Gift Specialties': 'inline_retail',
    'Health': 'inline_retail',
    'Home Appliances': 'inline_retail',
    'Home Building': 'inline_retail',
    'Home Furnishings': 'inline_retail',
    'Housewares': 'inline_retail',
    'Jewelry': 'inline_retail',
    'Leather Goods': 'inline_retail',
    'Lingerie': 'inline_retail',
    'Liquor & Wine': 'inline_retail',
    'Martial Arts': 'inline_retail',
    'Mattress Store': 'inline_retail',
    'Mobile Phone Sales': 'inline_retail',
    'Music Store': 'inline_retail',
    'Musical Instruments': 'inline_retail',
    'Paint Stores': 'inline_retail',
    'Party Goods': 'inline_retail',
    'Pawn Shop': 'inline_retail',
    'Pet Supplies': 'inline_retail',
    'Pet Sales': 'inline_retail',
    'Plants': 'inline_retail',
    'Pools': 'inline_retail',
    'Shoes': 'inline_retail',
    'Signs & Banners': 'inline_retail',
    'Sporting Goods': 'inline_retail',
    'Stationery': 'inline_retail',
    'Sunglasses': 'inline_retail',
    'Surplus': 'inline_retail',
    'Thrift Stores': 'inline_retail',
    'Tobacco': 'inline_retail',
    'Toys & Hobbies': 'inline_retail',
    'Variety Store': 'inline_retail',
    'Upscale/Luxury': 'inline_retail',
    
    # =========================================================================
    # FOOD & BEVERAGE
    # =========================================================================
    'Bar': 'food_beverage',
    'Brewery': 'food_beverage',
    'Coffee Shop': 'food_beverage',
    'Craft Beer Bar': 'food_beverage',
    'Craft Beer Sales': 'food_beverage',
    'Delicatessen': 'food_beverage',
    'Desserts (Casual)': 'food_beverage',
    'Ice Cream Shop': 'food_beverage',
    'Restaurant | Asian': 'food_beverage',
    'Restaurant | Breakfast': 'food_beverage',
    'Restaurant | Burger': 'food_beverage',
    'Restaurant | Chinese': 'food_beverage',
    'Restaurant | Fast Casual': 'food_beverage',
    'Restaurant | Fast Food': 'food_beverage',
    'Restaurant | Full Service': 'food_beverage',
    'Restaurant | Healthy': 'food_beverage',
    'Restaurant | Indian': 'food_beverage',
    'Restaurant | Italian': 'food_beverage',
    'Restaurant | Japanese': 'food_beverage',
    'Restaurant | Mexican': 'food_beverage',
    'Restaurant | Thai': 'food_beverage',
    'Restaurant | Vegan': 'food_beverage',
    'Pizza (Casual)': 'food_beverage',
    'Pizza (Full Service)': 'food_beverage',
    'Sports Bar': 'food_beverage',
    
    # =========================================================================
    # SERVICES
    # =========================================================================
    'Auto Body & Collision': 'services',
    'Auto Retailers': 'services',
    'Bank': 'services',
    'bank': 'services',  # Lowercase variation in CSV
    'Car Audio': 'services',
    'Car Care and Service': 'services',
    'Car Rental': 'services',
    'Car Wash': 'services',
    'Check Cashing': 'services',
    'Cosmetic/Aesthetic Services': 'services',
    'Delivery/Fulfillment Services': 'services',
    'Dentistry': 'services',
    'Dry Cleaning': 'services',
    'Education (Childcare)': 'services',
    'Education (Learning Centers)': 'services',
    'Education (Schools)': 'services',
    'Eye Care': 'services',
    'Eyewear': 'services',
    'Eyelash Salon': 'services',
    'Exercise Studio': 'services',
    'Financial': 'services',
    'Flooring Installation (Carpet)': 'services',  
    'Gas Station': 'services',
    'Gym': 'services',
    'Hair Salon (Womens)': 'services',
    'Hair Salon (Mens)': 'services',
    'Hair Salon (Childrens)': 'services',
    'Hair Salon (Unisex)': 'services',
    'Insurance Agent/Broker': 'services',
    'Laundromat': 'services',
    'Mail/Shipping Services': 'services',
    'Massage': 'services',
    'Medical Center': 'services',
    'Medical Practice': 'services',
    'Nail Salon': 'services',
    'Office Supplies': 'services',
    'Other': 'services',
    'Physical Therapy': 'services',
    'Printing': 'services',
    'Real Estate Agency': 'services',
    'Shipping': 'services',
    'Shoe Repair': 'services',
    'Tailoring': 'services',
    'Tax Services': 'services',
    'Therapy Services': 'services',
    'Tires': 'services',
    'Tutoring': 'services',
    'Weight Control': 'services',
    'Wellness Treatments': 'services',
    
    # =========================================================================
    # ENTERTAINMENT / LEISURE
    # =========================================================================
    'Amusement': 'entertainment_leisure',
    'Entertainment (Adult)': 'entertainment_leisure',
    'Entertainment (Family)': 'entertainment_leisure',
    'Indoor Golf': 'entertainment_leisure',
    'Movie Theater': 'entertainment_leisure',
    'Theatre': 'entertainment_leisure',
    'Dance Studio': 'entertainment_leisure',
    'Swim Schools': 'entertainment_leisure',
    'Music': 'entertainment_leisure',
    'Flea Markets': 'entertainment_leisure',
    
    # =========================================================================
    # OTHER / NON-RETAIL
    # =========================================================================
    'Campus Site': 'other_nonretail',
    'Convenience & Gas': 'other_nonretail',
    'Equipment Rental': 'other_nonretail',
    'Funeral Home': 'other_nonretail',
    'Hotel Lobby': 'other_nonretail',
    'Hotel': 'other_nonretail',
    'Law Firm': 'other_nonretail',
    'Mixed Use': 'other_nonretail',
    'Multitenant Unit': 'other_nonretail',
    'On-Site Property Manager': 'other_nonretail',
    'Senior Care Facilities': 'other_nonretail',
    'Storage Facilities': 'other_nonretail',
    'Transit Terminal': 'other_nonretail',
    'Travel Agency': 'other_nonretail',
    'Truck Stop': 'other_nonretail',
    
    # =========================================================================
    # SEASONAL / POP-UP
    # =========================================================================
    'Seasonal & Pop Up': 'seasonal_popup',
    
    # =========================================================================
    # VACANT
    # =========================================================================
    'Vacant': 'vacant',
}


# =============================================================================
# SHOPPING CENTER MODEL
# =============================================================================

class ShoppingCenter(models.Model):
    """
    Represents a commercial retail property/shopping center.
    
    Core Principle: This model stores raw data only. All calculations
    (center_type, quality_score, occupancy) happen elsewhere.
    """
    
    # Identification
    shopping_center_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Primary identifier - must be unique"
    )
    
    # Classification
    center_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ICSC property type classification (determined by GLA thresholds)"
    )
    
    # Location (Address Components)
    address_street = models.CharField(max_length=255, blank=True, null=True)
    address_city = models.CharField(max_length=100, blank=True, null=True)
    address_state = models.CharField(max_length=2, blank=True, null=True)
    address_zip = models.CharField(max_length=10, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    municipality = models.CharField(max_length=100, blank=True, null=True)
    
    # Geospatial
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
        help_text="Decimal degrees, populated by geocoding service"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
        help_text="Decimal degrees, populated by geocoding service"
    )
    
    # Property Characteristics
    year_built = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2100)]
    )
    total_gla = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Gross Leasable Area in square feet"
    )
    
    # Key Parties
    owner = models.CharField(max_length=255, blank=True, null=True)
    property_manager = models.CharField(max_length=255, blank=True, null=True)
    leasing_agent = models.CharField(max_length=255, blank=True, null=True)
    leasing_brokerage = models.CharField(max_length=255, blank=True, null=True)
    
    # Regulatory
    zoning_authority = models.CharField(max_length=255, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'shopping_centers'
        ordering = ['shopping_center_name']
        verbose_name = 'Shopping Center'
        verbose_name_plural = 'Shopping Centers'
        
        indexes = [
            models.Index(fields=['shopping_center_name']),
            models.Index(fields=['address_city', 'address_state']),
            models.Index(fields=['county']),
            models.Index(fields=['center_type']),
        ]
    
    def __str__(self):
        return self.shopping_center_name
    
    def __repr__(self):
        return f"<ShoppingCenter: {self.shopping_center_name}>"
    
    def get_full_address(self):
        """
        Returns formatted full address.
        
        Returns:
            str: Comma-separated full address or empty string if no components
        """
        parts = [
            self.address_street,
            self.address_city,
            self.address_state,
            self.address_zip
        ]
        return ", ".join(filter(None, parts))
    
    @property
    def has_coordinates(self):
        """Check if property has been geocoded."""
        return self.latitude is not None and self.longitude is not None
    
    # =========================================================================
    # COMPUTED FIELDS - Added 2025-10-10 to support serializers
    # =========================================================================
    
    def get_tenant_count(self):
        """
        Get total number of tenants (including vacant units).
        
        Returns:
            int: Total count of all tenant records for this shopping center
        """
        return self.tenants.count()
    
    def get_occupied_tenant_count(self):
        """
        Get number of occupied (non-vacant) tenants.
        
        Returns:
            int: Count of tenants where tenant_name != 'Vacant'
        """
        return self.tenants.exclude(tenant_name='Vacant').count()
    
    def get_vacancy_rate(self):
        """
        Calculate vacancy rate as percentage.
        
        Returns:
            float: Vacancy rate as percentage (0.0 to 100.0)
                   Returns 0.0 if no tenants exist
        
        Example:
            10 total units, 2 vacant = 20.0% vacancy rate
        """
        total = self.get_tenant_count()
        if total == 0:
            return 0.0
        
        vacant = self.tenants.filter(tenant_name='Vacant').count()
        return round((vacant / total) * 100, 2)


# =============================================================================
# TENANT MODEL
# =============================================================================

class Tenant(models.Model):
    """
    Represents a retail tenant/business within a shopping center.
    
    Unique Constraint: shopping_center + tenant_name
    (If tenant moves suites, update existing record)
    """
    
    # Relationships
    shopping_center = models.ForeignKey(
        ShoppingCenter,
        on_delete=models.CASCADE,
        related_name='tenants'
    )
    
    # Identification
    tenant_name = models.CharField(
        max_length=255,
        help_text="Business/brand name"
    )
    tenant_suite_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Suite/unit number within shopping center"
    )
    
    # Space
    square_footage = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Leased square footage"
    )
    
    # Categorization
    retail_category = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Specific retail business category (from taxonomy)"
    )
    
    major_group = models.CharField(
        max_length=50,
        choices=MAJOR_GROUP_CHOICES,
        blank=True,
        null=True,
        help_text="High-level tenant categorization for tenant mix analysis"
    )
    
    # Lease Terms
    ownership_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Owned vs Leased"
    )
    base_rent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Annual rent per square foot (CRE standard quoting: '$30/SF' means $30/SF/year)"
    )
    lease_term = models.IntegerField(
        blank=True,
        null=True,
        help_text="Lease term in months"
    )
    lease_commence = models.DateField(
        blank=True,
        null=True,
        help_text="Lease start date"
    )
    lease_expiration = models.DateField(
        blank=True,
        null=True,
        help_text="Lease expiration date"
    )
    
    # Additional fields
    credit_category = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Credit rating category"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants'
        ordering = ['shopping_center', 'tenant_suite_number']
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'
        
        indexes = [
            models.Index(fields=['tenant_name']),
            models.Index(fields=['shopping_center', 'tenant_name']),
            models.Index(fields=['major_group']),
        ]
        
        # Unique constraint: shopping_center + tenant_name + tenant_suite_number
        # This allows multiple vacant units per shopping center (different suites)
        # and prevents duplicates on reimport for all tenant types
        constraints = [
            models.UniqueConstraint(
                fields=['shopping_center', 'tenant_name', 'tenant_suite_number'],
                name='unique_tenant_per_center'
            )
        ]
    
    def __str__(self):
        suite = f" - {self.tenant_suite_number}" if self.tenant_suite_number else ""
        return f"{self.tenant_name}{suite}"
    
    def __repr__(self):
        return f"<Tenant: {self.tenant_name} @ {self.shopping_center.shopping_center_name}>"
    
    def save(self, *args, **kwargs):
        """
        Override save to auto-populate major_group from retail_category.
        
        Business Logic:
        - If major_group is not set and retail_category exists, derive it from mapping
        - Default to 'other_nonretail' for unmapped categories
        - Log warning for unmapped categories
        """
        if not self.major_group and self.retail_category:
            # Map retail_category to major_group
            self.major_group = RETAIL_CATEGORY_TO_MAJOR_GROUP.get(
                self.retail_category,
                'other_nonretail'  # Default fallback
            )
            
            # Log warning if category is unmapped
            if self.retail_category not in RETAIL_CATEGORY_TO_MAJOR_GROUP:
                logger.warning(
                    f"Unmapped retail_category '{self.retail_category}' for tenant "
                    f"'{self.tenant_name}' in {self.shopping_center.shopping_center_name}. "
                    f"Defaulting to 'Other / Non-Retail'."
                )
        
        super().save(*args, **kwargs)
    
    def get_rent_per_sq_ft(self):
        """
        Return annual rent per square foot.
        
        Since base_rent is already stored as annual $/SF (CRE standard),
        we simply return it directly.
        
        Returns:
            Decimal: Annual rent per square foot, or None if not available
        
        Example:
            If base_rent = 27.00, returns 27.00 (meaning $27/SF/year)
        """
        if not self.base_rent:
            return None
        return self.base_rent
    
    def get_annual_rent(self):
        """
        Calculate total annual rent.
        
        Formula: base_rent ($/SF/year) × square_footage
        
        Returns:
            float: Total annual rent, or None if data not available
        
        Example:
            base_rent = $27/SF, square_footage = 1,400 SF
            Returns: $37,800/year
        """
        if not self.base_rent or not self.square_footage or self.square_footage == 0:
            return None
        return round(float(self.base_rent) * self.square_footage, 2)
    
    def get_monthly_rent(self):
        """
        Calculate monthly rent.
        
        Formula: annual_rent ÷ 12
        
        Returns:
            float: Monthly rent, or None if data not available
        
        Example:
            Annual rent = $37,800
            Returns: $3,150/month
        """
        annual = self.get_annual_rent()
        if not annual:
            return None
        return round(annual / 12, 2)
    
    def get_lease_status(self):
        """Get current lease status."""
        if not self.lease_expiration:
            return "Unknown"
        
        if self.lease_expiration < date.today():
            return "Expired"
        elif self.lease_expiration <= date.today() + timedelta(days=365):
            return "Expiring Soon"
        return "Active"
    
    def is_lease_expiring_soon(self, months=12):
        """Check if lease expires within specified months."""
        if not self.lease_expiration:
            return False
        
        threshold_date = date.today() + timedelta(days=months*30)
        return self.lease_expiration <= threshold_date
