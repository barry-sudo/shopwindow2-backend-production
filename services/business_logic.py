"""
Business Logic Services for Shop Window Application.

This module implements the core business logic functions that power the
progressive data enrichment system and commercial real estate analytics.

Key Features:
- ICSC (International Council of Shopping Centers) classification standards
- Data quality scoring algorithms with weighted metrics
- Progressive data enrichment business rules
- Tenant analysis and classification functions
- Financial calculations and market analysis
- Validation and data cleaning utilities

Business Philosophy:
- EXTRACT fields: Direct from source data (CSV, PDF, manual entry)
- DETERMINE fields: Calculated via business logic functions
- DEFINE fields: Manual entry with business validation

All functions support the "stocking shelves" approach - process data
first, improve quality iteratively through progressive enrichment.
"""

import logging
import re
import math
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES FOR BUSINESS LOGIC
# =============================================================================

@dataclass
class QualityScoreBreakdown:
    """Detailed breakdown of data quality score calculation."""
    extract_score: float
    extract_weight: float
    determine_score: float
    determine_weight: float
    define_score: float
    define_weight: float
    tenant_bonus: float
    total_score: int
    field_breakdown: Dict[str, bool]


@dataclass
class TenantAnalysis:
    """Analysis results for tenant mix and performance."""
    total_tenants: int
    occupied_count: int
    vacant_count: int
    anchor_count: int
    vacancy_rate: float
    avg_tenant_size: float
    category_breakdown: Dict[str, int]
    lease_expiration_analysis: Dict[str, int]


@dataclass
class FinancialMetrics:
    """Financial performance metrics for shopping centers."""
    total_gla: int
    leased_gla: int
    avg_rent_psf: float
    total_annual_rent: float
    occupancy_rate: float
    rent_roll_analysis: Dict[str, Any]


# =============================================================================
# ICSC CENTER TYPE CLASSIFICATION
# =============================================================================

def calculate_center_type(gla: Optional[int]) -> Optional[str]:
    """
    Determine shopping center type based on GLA using ICSC standards.
    
    International Council of Shopping Centers (ICSC) Classification:
    - Strip/Convenience: < 30,000 SF
    - Neighborhood Center: 30,000 - 125,000 SF
    - Community Center: 125,000 - 400,000 SF
    - Regional Mall: 400,000 - 800,000 SF
    - Super-Regional Mall: > 800,000 SF
    
    Args:
        gla: Gross Leasable Area in square feet
        
    Returns:
        String classification or None if GLA not provided
    """
    if not gla or gla <= 0:
        return None
    
    try:
        gla = int(gla)
        
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
            
    except (ValueError, TypeError):
        logger.warning(f"Invalid GLA value for center type calculation: {gla}")
        return None


def get_center_type_characteristics(center_type: str) -> Dict[str, Any]:
    """
    Get detailed characteristics for each center type.
    
    Returns market positioning, typical tenants, and operational metrics
    for different shopping center classifications.
    """
    characteristics = {
        "Strip/Convenience": {
            "typical_gla_range": "5,000 - 30,000 SF",
            "trade_area_radius": "1-3 miles",
            "anchor_tenants": ["Convenience stores", "Fast food", "Service businesses"],
            "typical_tenant_size": "1,000 - 5,000 SF",
            "parking_ratio": "4-5 spaces per 1,000 SF",
            "market_position": "Neighborhood convenience shopping"
        },
        "Neighborhood Center": {
            "typical_gla_range": "30,000 - 125,000 SF",
            "trade_area_radius": "3-5 miles",
            "anchor_tenants": ["Supermarket", "Drug store", "Large discount store"],
            "typical_tenant_size": "2,000 - 15,000 SF",
            "parking_ratio": "4-5 spaces per 1,000 SF",
            "market_position": "Weekly shopping needs"
        },
        "Community Center": {
            "typical_gla_range": "125,000 - 400,000 SF",
            "trade_area_radius": "5-10 miles",
            "anchor_tenants": ["Department store", "Large specialty stores", "Category killers"],
            "typical_tenant_size": "5,000 - 25,000 SF",
            "parking_ratio": "5-6 spaces per 1,000 SF",
            "market_position": "Comparison shopping destination"
        },
        "Regional Mall": {
            "typical_gla_range": "400,000 - 800,000 SF",
            "trade_area_radius": "10-20 miles",
            "anchor_tenants": ["2+ department stores", "National chain retailers"],
            "typical_tenant_size": "1,000 - 50,000 SF",
            "parking_ratio": "5-6 spaces per 1,000 SF",
            "market_position": "Primary shopping destination"
        },
        "Super-Regional Mall": {
            "typical_gla_range": "800,000+ SF",
            "trade_area_radius": "20+ miles",
            "anchor_tenants": ["3+ department stores", "Entertainment venues"],
            "typical_tenant_size": "1,000 - 100,000 SF",
            "parking_ratio": "5-6 spaces per 1,000 SF",
            "market_position": "Regional shopping destination"
        }
    }
    
    return characteristics.get(center_type, {})


# =============================================================================
# DATA QUALITY SCORING SYSTEM
# =============================================================================

def calculate_data_quality_score(shopping_center) -> int:
    """
    Calculate comprehensive data quality score (0-100) for shopping center.
    
    Scoring weights based on business value:
    - EXTRACT fields: 40% (data directly from imports)
    - DETERMINE fields: 20% (calculated business logic)
    - DEFINE fields: 40% (manual entry for strategic data)
    
    Args:
        shopping_center: ShoppingCenter model instance
        
    Returns:
        Integer score from 0-100
    """
    try:
        # Initialize scoring variables
        total_weight = 0
        completed_weight = 0
        
        # =============================================================================
        # EXTRACT FIELDS SCORING (40% weight)
        # =============================================================================
        
        extract_fields = [
            (shopping_center.shopping_center_name, 3.0),  # Critical identifier
            (shopping_center.address_street, 2.0),        # Essential for geocoding
            (shopping_center.address_city, 1.5),          # Important for location
            (shopping_center.address_state, 1.0),         # Standard location data
            (shopping_center.address_zip, 1.0),           # Standard location data
            (shopping_center.contact_name, 0.5),          # Nice to have
            (shopping_center.contact_phone, 0.5),         # Nice to have
            (shopping_center.total_gla, 2.5),             # Critical for classification
        ]
        
        for field_value, weight in extract_fields:
            total_weight += weight
            if field_value and str(field_value).strip():
                completed_weight += weight
        
        # =============================================================================
        # DETERMINE FIELDS SCORING (20% weight)
        # =============================================================================
        
        determine_fields = [
            (shopping_center.center_type, 2.0),           # Calculated from GLA
            (shopping_center.latitude and shopping_center.longitude, 3.0),  # Geocoded coordinates
            (shopping_center.calculated_gla, 1.0),        # Calculated from tenants
        ]
        
        for field_value, weight in determine_fields:
            total_weight += weight
            if field_value:
                completed_weight += weight
        
        # =============================================================================
        # DEFINE FIELDS SCORING (40% weight)
        # =============================================================================
        
        define_fields = [
            (shopping_center.owner, 2.5),                 # Critical business info
            (shopping_center.property_manager, 2.5),      # Critical operations info
            (shopping_center.county, 1.0),                # Administrative data
            (shopping_center.municipality, 1.0),          # Zoning/regulatory data
            (shopping_center.year_built, 1.5),            # Asset characteristics
            (shopping_center.leasing_agent, 1.0),         # Business relationships
            (shopping_center.leasing_brokerage, 1.0),     # Business relationships
            (shopping_center.zoning_authority, 0.5),      # Regulatory data
        ]
        
        for field_value, weight in define_fields:
            total_weight += weight
            if field_value and str(field_value).strip():
                completed_weight += weight
        
        # =============================================================================
        # TENANT DATA BONUS SCORING
        # =============================================================================
        
        # Bonus points for having tenant data (demonstrates data richness)
        if hasattr(shopping_center, 'tenants'):
            tenant_count = shopping_center.tenants.count() if shopping_center.tenants else 0
            
            if tenant_count > 0:
                total_weight += 2.0
                completed_weight += 2.0
                
                # Additional bonus for detailed tenant information
                tenants_with_size = shopping_center.tenants.filter(
                    square_footage__isnull=False
                ).count() if shopping_center.tenants else 0
                
                if tenants_with_size > 0:
                    total_weight += 1.0
                    completed_weight += min(1.0, tenants_with_size / tenant_count)
        
        # =============================================================================
        # FINAL SCORE CALCULATION
        # =============================================================================
        
        if total_weight > 0:
            score = (completed_weight / total_weight) * 100
            return min(int(round(score)), 100)
        else:
            return 0
            
    except Exception as e:
        logger.error(f"Error calculating data quality score: {str(e)}")
        return 0


def get_quality_score_breakdown(shopping_center) -> QualityScoreBreakdown:
    """
    Get detailed breakdown of quality score calculation.
    
    Provides transparency into how the quality score is calculated
    and which fields are contributing to or detracting from the score.
    """
    try:
        # Track individual field completion
        field_breakdown = {}
        
        # EXTRACT fields analysis
        extract_fields = {
            'shopping_center_name': bool(shopping_center.shopping_center_name),
            'address_street': bool(shopping_center.address_street and shopping_center.address_street.strip()),
            'address_city': bool(shopping_center.address_city and shopping_center.address_city.strip()),
            'address_state': bool(shopping_center.address_state and shopping_center.address_state.strip()),
            'address_zip': bool(shopping_center.address_zip and shopping_center.address_zip.strip()),
            'contact_name': bool(shopping_center.contact_name and shopping_center.contact_name.strip()),
            'contact_phone': bool(shopping_center.contact_phone and shopping_center.contact_phone.strip()),
            'total_gla': bool(shopping_center.total_gla),
        }
        
        extract_completed = sum(extract_fields.values())
        extract_total = len(extract_fields)
        extract_score = (extract_completed / extract_total) * 100 if extract_total > 0 else 0
        
        # DETERMINE fields analysis
        determine_fields = {
            'center_type': bool(shopping_center.center_type),
            'coordinates': bool(shopping_center.latitude and shopping_center.longitude),
            'calculated_gla': bool(shopping_center.calculated_gla),
        }
        
        determine_completed = sum(determine_fields.values())
        determine_total = len(determine_fields)
        determine_score = (determine_completed / determine_total) * 100 if determine_total > 0 else 0
        
        # DEFINE fields analysis
        define_fields = {
            'owner': bool(shopping_center.owner and shopping_center.owner.strip()),
            'property_manager': bool(shopping_center.property_manager and shopping_center.property_manager.strip()),
            'county': bool(shopping_center.county and shopping_center.county.strip()),
            'municipality': bool(shopping_center.municipality and shopping_center.municipality.strip()),
            'year_built': bool(shopping_center.year_built),
            'leasing_agent': bool(shopping_center.leasing_agent and shopping_center.leasing_agent.strip()),
            'leasing_brokerage': bool(shopping_center.leasing_brokerage and shopping_center.leasing_brokerage.strip()),
            'zoning_authority': bool(shopping_center.zoning_authority and shopping_center.zoning_authority.strip()),
        }
        
        define_completed = sum(define_fields.values())
        define_total = len(define_fields)
        define_score = (define_completed / define_total) * 100 if define_total > 0 else 0
        
        # Tenant bonus calculation
        tenant_bonus = 0
        if hasattr(shopping_center, 'tenants'):
            tenant_count = shopping_center.tenants.count() if shopping_center.tenants else 0
            if tenant_count > 0:
                tenant_bonus = min(10, tenant_count)  # Max 10 point bonus
        
        # Combine field breakdowns
        field_breakdown.update(extract_fields)
        field_breakdown.update(determine_fields)
        field_breakdown.update(define_fields)
        
        # Weighted total calculation
        extract_weight = 0.4
        determine_weight = 0.2
        define_weight = 0.4
        
        total_score = int(
            (extract_score * extract_weight) +
            (determine_score * determine_weight) +
            (define_score * define_weight) +
            tenant_bonus
        )
        
        return QualityScoreBreakdown(
            extract_score=extract_score,
            extract_weight=extract_weight,
            determine_score=determine_score,
            determine_weight=determine_weight,
            define_score=define_score,
            define_weight=define_weight,
            tenant_bonus=tenant_bonus,
            total_score=min(total_score, 100),
            field_breakdown=field_breakdown
        )
        
    except Exception as e:
        logger.error(f"Error calculating quality score breakdown: {str(e)}")
        return QualityScoreBreakdown(0, 0, 0, 0, 0, 0, 0, 0, {})


# =============================================================================
# TENANT ANALYSIS FUNCTIONS
# =============================================================================

def analyze_tenant_mix(shopping_center) -> TenantAnalysis:
    """
    Comprehensive analysis of tenant mix and performance.
    
    Analyzes occupancy, tenant categories, sizes, and lease terms
    to provide insights into shopping center performance.
    """
    try:
        if not hasattr(shopping_center, 'tenants'):
            return TenantAnalysis(0, 0, 0, 0, 0.0, 0.0, {}, {})
        
        tenants = shopping_center.tenants.all()
        total_tenants = tenants.count()
        
        if total_tenants == 0:
            return TenantAnalysis(0, 0, 0, 0, 0.0, 0.0, {}, {})
        
        # Occupancy analysis
        occupied_count = tenants.filter(occupancy_status='OCCUPIED').count()
        vacant_count = tenants.filter(occupancy_status='VACANT').count()
        anchor_count = tenants.filter(is_anchor=True).count()
        
        vacancy_rate = (vacant_count / total_tenants) * 100 if total_tenants > 0 else 0
        
        # Size analysis
        tenants_with_size = tenants.exclude(square_footage__isnull=True)
        total_sf = sum(t.square_footage for t in tenants_with_size if t.square_footage)
        avg_tenant_size = total_sf / tenants_with_size.count() if tenants_with_size.count() > 0 else 0
        
        # Category breakdown
        category_breakdown = {}
        for tenant in tenants:
            if tenant.retail_category:
                for category in tenant.retail_category:
                    if category:
                        category_breakdown[category] = category_breakdown.get(category, 0) + 1
        
        # Lease expiration analysis
        lease_expiration_analysis = {
            'expiring_6_months': 0,
            'expiring_12_months': 0,
            'expiring_24_months': 0,
            'expired': 0,
            'no_expiration_date': 0
        }
        
        today = date.today()
        for tenant in tenants:
            if not tenant.lease_expiration:
                lease_expiration_analysis['no_expiration_date'] += 1
            else:
                days_until_expiration = (tenant.lease_expiration - today).days
                if days_until_expiration < 0:
                    lease_expiration_analysis['expired'] += 1
                elif days_until_expiration <= 180:  # 6 months
                    lease_expiration_analysis['expiring_6_months'] += 1
                elif days_until_expiration <= 365:  # 12 months
                    lease_expiration_analysis['expiring_12_months'] += 1
                elif days_until_expiration <= 730:  # 24 months
                    lease_expiration_analysis['expiring_24_months'] += 1
        
        return TenantAnalysis(
            total_tenants=total_tenants,
            occupied_count=occupied_count,
            vacant_count=vacant_count,
            anchor_count=anchor_count,
            vacancy_rate=round(vacancy_rate, 2),
            avg_tenant_size=round(avg_tenant_size, 0),
            category_breakdown=category_breakdown,
            lease_expiration_analysis=lease_expiration_analysis
        )
        
    except Exception as e:
        logger.error(f"Error analyzing tenant mix: {str(e)}")
        return TenantAnalysis(0, 0, 0, 0, 0.0, 0.0, {}, {})


def calculate_financial_metrics(shopping_center) -> FinancialMetrics:
    """
    Calculate financial performance metrics for shopping center.
    
    Analyzes rent rolls, occupancy rates, and financial performance
    indicators based on available tenant data.
    """
    try:
        if not hasattr(shopping_center, 'tenants'):
            return FinancialMetrics(0, 0, 0.0, 0.0, 0.0, {})
        
        tenants = shopping_center.tenants.all()
        
        # GLA calculations
        total_gla = shopping_center.total_gla or shopping_center.calculated_gla or 0
        
        occupied_tenants = tenants.filter(occupancy_status='OCCUPIED')
        leased_gla = sum(t.square_footage for t in occupied_tenants if t.square_footage) or 0
        
        occupancy_rate = (leased_gla / total_gla * 100) if total_gla > 0 else 0
        
        # Rent analysis
        tenants_with_rent = occupied_tenants.exclude(base_rent__isnull=True, square_footage__isnull=True)
        
        total_annual_rent = 0
        rent_psf_values = []
        
        for tenant in tenants_with_rent:
            if tenant.base_rent and tenant.square_footage:
                annual_rent = float(tenant.base_rent) * 12  # Assuming base_rent is monthly
                total_annual_rent += annual_rent
                
                rent_psf = float(tenant.base_rent) * 12 / tenant.square_footage
                rent_psf_values.append(rent_psf)
        
        avg_rent_psf = sum(rent_psf_values) / len(rent_psf_values) if rent_psf_values else 0
        
        # Rent roll analysis
        rent_roll_analysis = {
            'total_tenants_with_rent_data': len(rent_psf_values),
            'rent_range': {
                'min_psf': min(rent_psf_values) if rent_psf_values else 0,
                'max_psf': max(rent_psf_values) if rent_psf_values else 0,
                'median_psf': sorted(rent_psf_values)[len(rent_psf_values)//2] if rent_psf_values else 0
            },
            'anchor_vs_inline': analyze_anchor_vs_inline_rents(tenants),
            'category_rent_analysis': analyze_rent_by_category(tenants)
        }
        
        return FinancialMetrics(
            total_gla=total_gla,
            leased_gla=leased_gla,
            avg_rent_psf=round(avg_rent_psf, 2),
            total_annual_rent=round(total_annual_rent, 2),
            occupancy_rate=round(occupancy_rate, 2),
            rent_roll_analysis=rent_roll_analysis
        )
        
    except Exception as e:
        logger.error(f"Error calculating financial metrics: {str(e)}")
        return FinancialMetrics(0, 0, 0.0, 0.0, 0.0, {})


def analyze_anchor_vs_inline_rents(tenants) -> Dict[str, Any]:
    """Analyze rent differences between anchor and inline tenants."""
    try:
        anchor_rents = []
        inline_rents = []
        
        for tenant in tenants:
            if tenant.base_rent and tenant.square_footage:
                rent_psf = float(tenant.base_rent) * 12 / tenant.square_footage
                
                if tenant.is_anchor:
                    anchor_rents.append(rent_psf)
                else:
                    inline_rents.append(rent_psf)
        
        return {
            'anchor_avg_psf': round(sum(anchor_rents) / len(anchor_rents), 2) if anchor_rents else 0,
            'inline_avg_psf': round(sum(inline_rents) / len(inline_rents), 2) if inline_rents else 0,
            'anchor_count': len(anchor_rents),
            'inline_count': len(inline_rents)
        }
        
    except Exception as e:
        logger.error(f"Error analyzing anchor vs inline rents: {str(e)}")
        return {}


def analyze_rent_by_category(tenants) -> Dict[str, float]:
    """Analyze average rents by retail category."""
    try:
        category_rents = {}
        
        for tenant in tenants:
            if tenant.base_rent and tenant.square_footage and tenant.retail_category:
                rent_psf = float(tenant.base_rent) * 12 / tenant.square_footage
                
                for category in tenant.retail_category:
                    if category not in category_rents:
                        category_rents[category] = []
                    category_rents[category].append(rent_psf)
        
        # Calculate averages
        category_averages = {}
        for category, rents in category_rents.items():
            category_averages[category] = round(sum(rents) / len(rents), 2)
        
        return category_averages
        
    except Exception as e:
        logger.error(f"Error analyzing rent by category: {str(e)}")
        return {}


# =============================================================================
# DATA VALIDATION AND CLEANING
# =============================================================================

def validate_address_components(address_street: str, address_city: str, 
                               address_state: str, address_zip: str) -> Dict[str, Any]:
    """
    Validate and clean address components for geocoding readiness.
    
    Returns validation results and cleaned address components.
    """
    validation_results = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'cleaned_address': {},
        'geocoding_ready': False
    }
    
    try:
        # Clean and validate street address
        if address_street:
            cleaned_street = clean_street_address(address_street)
            validation_results['cleaned_address']['street'] = cleaned_street
            
            if len(cleaned_street.strip()) < 5:
                validation_results['warnings'].append("Street address appears incomplete")
        else:
            validation_results['errors'].append("Street address is required")
            validation_results['is_valid'] = False
        
        # Clean and validate city
        if address_city:
            cleaned_city = clean_city_name(address_city)
            validation_results['cleaned_address']['city'] = cleaned_city
        else:
            validation_results['errors'].append("City is required")
            validation_results['is_valid'] = False
        
        # Validate state
        if address_state:
            cleaned_state = validate_state_code(address_state)
            if cleaned_state:
                validation_results['cleaned_address']['state'] = cleaned_state
            else:
                validation_results['errors'].append(f"Invalid state code: {address_state}")
                validation_results['is_valid'] = False
        else:
            validation_results['errors'].append("State is required")
            validation_results['is_valid'] = False
        
        # Validate ZIP code
        if address_zip:
            cleaned_zip = clean_zip_code(address_zip)
            if cleaned_zip:
                validation_results['cleaned_address']['zip'] = cleaned_zip
            else:
                validation_results['warnings'].append(f"Invalid ZIP code format: {address_zip}")
        
        # Determine if ready for geocoding
        validation_results['geocoding_ready'] = (
            validation_results['is_valid'] and
            len(validation_results['errors']) == 0
        )
        
    except Exception as e:
        logger.error(f"Error validating address components: {str(e)}")
        validation_results['is_valid'] = False
        validation_results['errors'].append("Address validation failed")
    
    return validation_results


def clean_street_address(address: str) -> str:
    """Clean and standardize street address."""
    if not address:
        return ""
    
    # Basic cleaning
    cleaned = address.strip()
    
    # Standardize directionals
    directional_replacements = {
        r'\bN\b': 'North',
        r'\bS\b': 'South', 
        r'\bE\b': 'East',
        r'\bW\b': 'West',
        r'\bNE\b': 'Northeast',
        r'\bNW\b': 'Northwest',
        r'\bSE\b': 'Southeast',
        r'\bSW\b': 'Southwest',
    }
    
    for pattern, replacement in directional_replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    
    # Standardize street suffixes
    suffix_replacements = {
        r'\bSt\b': 'Street',
        r'\bAve\b': 'Avenue',
        r'\bRd\b': 'Road',
        r'\bDr\b': 'Drive',
        r'\bLn\b': 'Lane',
        r'\bCt\b': 'Court',
        r'\bPl\b': 'Place',
        r'\bBlvd\b': 'Boulevard',
        r'\bPkwy\b': 'Parkway',
    }
    
    for pattern, replacement in suffix_replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    
    return cleaned


def clean_city_name(city: str) -> str:
    """Clean and standardize city name."""
    if not city:
        return ""
    
    # Basic cleaning
    cleaned = city.strip().title()
    
    # Handle special cases
    cleaned = re.sub(r'\bSt\b', 'Saint', cleaned)
    cleaned = re.sub(r'\bMt\b', 'Mount', cleaned)
    
    return cleaned


def validate_state_code(state: str) -> Optional[str]:
    """Validate and return standardized state code."""
    if not state:
        return None
    
    state = state.strip().upper()
    
    # US state codes
    valid_states = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
        'DC'  # District of Columbia
    }
    
    return state if state in valid_states else None


def clean_zip_code(zip_code: str) -> Optional[str]:
    """Clean and validate ZIP code format."""
    if not zip_code:
        return None
    
    # Remove all non-digits
    cleaned = re.sub(r'[^\d]', '', zip_code.strip())
    
    # Validate length and format
    if len(cleaned) == 5:
        return cleaned
    elif len(cleaned) == 9:
        return f"{cleaned[:5]}-{cleaned[5:]}"
    else:
        return None


def validate_gla(gla: Any) -> Optional[int]:
    """Validate and clean GLA (Gross Leasable Area) value."""
    if gla is None:
        return None
    
    try:
        # Handle string inputs with commas
        if isinstance(gla, str):
            gla = re.sub(r'[,\s]', '', gla.strip())
        
        gla_int = int(float(gla))
        
        # Sanity checks
        if gla_int < 0:
            logger.warning("Negative GLA value provided")
            return None
        
        if gla_int > 10000000:  # 10 million sq ft seems unreasonable
            logger.warning(f"Unusually large GLA value: {gla_int}")
            return None
        
        return gla_int
        
    except (ValueError, TypeError):
        logger.warning(f"Invalid GLA format: {gla}")
        return None


def validate_year_built(year: Any) -> Optional[int]:
    """Validate year built value."""
    if year is None:
        return None
    
    try:
        year_int = int(year)
        current_year = date.today().year
        
        if year_int < 1800 or year_int > current_year + 5:
            logger.warning(f"Invalid year built: {year_int}")
            return None
        
        return year_int
        
    except (ValueError, TypeError):
        logger.warning(f"Invalid year format: {year}")
        return None


# =============================================================================
# PROGRESSIVE DATA ENRICHMENT UTILITIES
# =============================================================================

def should_update_field(current_value: Any, new_value: Any) -> bool:
    """
    Determine if a field should be updated based on progressive enrichment rules.
    
    Rules:
    1. If current value is empty/null, update with any non-empty new value
    2. If new value is empty/null, keep current value
    3. For specific field types, apply additional logic
    """
    # Handle None/empty cases
    if not current_value and new_value:
        return True
    
    if not new_value:
        return False
    
    # Both values exist - apply field-specific logic
    if isinstance(current_value, str) and isinstance(new_value, str):
        current_cleaned = current_value.strip()
        new_cleaned = new_value.strip()
        
        # Don't overwrite with obviously worse data
        if len(new_cleaned) < len(current_cleaned) / 2:
            return False
        
        # Update if new value is significantly more detailed
        if len(new_cleaned) > len(current_cleaned) * 1.5:
            return True
    
    # Default: keep existing data (progressive enrichment philosophy)
    return False


def merge_shopping_center_data(existing_center, new_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge new shopping center data with existing data using progressive enrichment rules.
    
    Returns dictionary of fields that should be updated.
    """
    updates = {}
    
    field_mapping = {
        'address_street': 'address_street',
        'address_city': 'address_city',
        'address_state': 'address_state',
        'address_zip': 'address_zip',
        'contact_name': 'contact_name',
        'contact_phone': 'contact_phone',
        'total_gla': 'total_gla',
        'county': 'county',
        'municipality': 'municipality',
        'zoning_authority': 'zoning_authority',
        'year_built': 'year_built',
        'owner': 'owner',
        'property_manager': 'property_manager',
        'leasing_agent': 'leasing_agent',
        'leasing_brokerage': 'leasing_brokerage',
    }
    
    for new_field, model_field in field_mapping.items():
        if new_field in new_data:
            current_value = getattr(existing_center, model_field, None)
            new_value = new_data[new_field]
            
            if should_update_field(current_value, new_value):
                updates[model_field] = new_value
    
    return updates


def calculate_import_statistics(import_batch) -> Dict[str, Any]:
    """
    Calculate comprehensive statistics for an import batch.
    
    Provides detailed metrics for import success analysis and reporting.
    """
    stats = {
        'processing_summary': {
            'total_records': import_batch.total_records,
            'successful_records': import_batch.successful_records,
            'failed_records': import_batch.failed_records,
            'skipped_records': import_batch.skipped_records,
            'success_rate': import_batch.get_success_rate(),
            'processing_duration': import_batch.get_processing_duration()
        },
        'business_objects': {
            'shopping_centers_created': import_batch.shopping_centers_created,
            'shopping_centers_updated': import_batch.shopping_centers_updated,
            'tenants_created': import_batch.tenants_created,
            'tenants_updated': import_batch.tenants_updated
        },
        'data_enrichment': {
            'fields_extracted': import_batch.fields_extracted,
            'fields_determined': import_batch.fields_determined,
            'fields_pending_manual': import_batch.fields_pending_manual
        },
        'quality_metrics': {
            'quality_flags_count': import_batch.quality_flags.count() if hasattr(import_batch, 'quality_flags') else 0,
            'unresolved_flags': import_batch.quality_flags.filter(is_resolved=False).count() if hasattr(import_batch, 'quality_flags') else 0,
            'high_severity_flags': import_batch.quality_flags.filter(severity__gte=4).count() if hasattr(import_batch, 'quality_flags') else 0
        }
    }
    
    return stats


# =============================================================================
# MARKET ANALYSIS UTILITIES
# =============================================================================

def calculate_market_positioning_score(shopping_center, comparable_centers: List) -> Dict[str, Any]:
    """
    Calculate market positioning score compared to similar centers.
    
    Analyzes how a shopping center performs relative to comparable
    properties in terms of size, tenant mix, and data completeness.
    """
    if not comparable_centers:
        return {'error': 'No comparable centers provided'}
    
    try:
        # Size comparison
        center_gla = shopping_center.total_gla or 0
        comparable_glas = [c.total_gla for c in comparable_centers if c.total_gla]
        
        size_percentile = 0
        if comparable_glas:
            smaller_count = sum(1 for gla in comparable_glas if gla < center_gla)
            size_percentile = (smaller_count / len(comparable_glas)) * 100
        
        # Quality comparison
        center_quality = shopping_center.data_quality_score
        comparable_qualities = [c.data_quality_score for c in comparable_centers]
        quality_percentile = (sum(1 for q in comparable_qualities if q < center_quality) / len(comparable_qualities)) * 100
        
        # Tenant count comparison
        center_tenant_count = shopping_center.get_tenant_count() if hasattr(shopping_center, 'get_tenant_count') else 0
        comparable_tenant_counts = []
        
        for c in comparable_centers:
            if hasattr(c, 'get_tenant_count'):
                comparable_tenant_counts.append(c.get_tenant_count())
        
        tenant_percentile = 0
        if comparable_tenant_counts:
            tenant_percentile = (sum(1 for count in comparable_tenant_counts if count < center_tenant_count) / len(comparable_tenant_counts)) * 100
        
        return {
            'size_percentile': round(size_percentile, 1),
            'quality_percentile': round(quality_percentile, 1),
            'tenant_count_percentile': round(tenant_percentile, 1),
            'overall_positioning': round((size_percentile + quality_percentile + tenant_percentile) / 3, 1),
            'comparable_centers_count': len(comparable_centers)
        }
        
    except Exception as e:
        logger.error(f"Error calculating market positioning: {str(e)}")
        return {'error': 'Failed to calculate market positioning'}


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

# Make key functions available for import
__all__ = [
    'calculate_center_type',
    'get_center_type_characteristics',
    'calculate_data_quality_score',
    'get_quality_score_breakdown',
    'analyze_tenant_mix',
    'calculate_financial_metrics',
    'validate_address_components',
    'clean_street_address',
    'clean_city_name',
    'validate_state_code',
    'clean_zip_code',
    'validate_gla',
    'validate_year_built',
    'should_update_field',
    'merge_shopping_center_data',
    'calculate_import_statistics',
    'calculate_market_positioning_score'
]
