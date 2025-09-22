"""
Geocoding Service for Shop Window Application.

This module provides comprehensive address geocoding functionality using
the Google Maps API. Transforms shopping center addresses into precise
coordinates for mapping, spatial analysis, and business intelligence.

Key Features:
- Google Maps API integration with rate limiting
- Address validation and cleaning before geocoding
- PostGIS Point field integration for spatial queries
- Batch geocoding operations for efficiency
- Caching to minimize API calls and costs
- Comprehensive error handling and logging
- Fallback mechanisms for failed requests
- Integration with business logic address validation

Production Considerations:
- API key security and rotation
- Rate limiting and quota management
- Error recovery and retry logic
- Performance optimization for bulk operations
- Cost monitoring and usage analytics
"""

import googlemaps
import logging
import time
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone

from .business_logic import validate_address_components, clean_street_address

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES FOR GEOCODING RESULTS
# =============================================================================

@dataclass
class GeocodingResult:
    """Structured result from geocoding operation."""
    success: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: Optional[str] = None
    place_id: Optional[str] = None
    address_components: Optional[Dict] = None
    geometry_type: Optional[str] = None
    location_type: Optional[str] = None
    viewport: Optional[Dict] = None
    error_message: Optional[str] = None
    api_status: Optional[str] = None
    confidence_score: float = 0.0


@dataclass  
class BatchGeocodingResult:
    """Results from batch geocoding operation."""
    total_addresses: int
    successful_geocodes: int
    failed_geocodes: int
    api_calls_used: int
    processing_time_seconds: float
    results: List[Tuple[int, GeocodingResult]]  # (shopping_center_id, result)
    errors: List[str]


@dataclass
class GeocodingQuotaStatus:
    """Current API quota and usage status."""
    daily_limit: int
    current_usage: int
    remaining_requests: int
    reset_time: datetime
    rate_limit_per_second: int
    estimated_cost_usd: float


# =============================================================================
# MAIN GEOCODING SERVICE
# =============================================================================

class GeocodingService:
    """
    Comprehensive geocoding service with Google Maps API integration.
    
    Handles individual and batch geocoding operations with intelligent
    caching, error handling, and rate limiting.
    """
    
    def __init__(self):
        """Initialize geocoding service with Google Maps client."""
        try:
            self.api_key = settings.GOOGLE_MAPS_API_KEY
            if not self.api_key:
                raise ValueError("Google Maps API key not configured in settings")
            
            self.client = googlemaps.Client(key=self.api_key)
            
            # Configuration from settings with defaults
            self.requests_per_day = getattr(settings, 'GOOGLE_MAPS_REQUESTS_PER_DAY', 40000)
            self.requests_per_second = getattr(settings, 'GOOGLE_MAPS_REQUESTS_PER_SECOND', 50)
            
            # Cache configuration
            self.cache_timeout = 60 * 60 * 24 * 30  # 30 days
            self.cache_prefix = 'geocoding'
            
            logger.info("GeocodingService initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize GeocodingService: {str(e)}")
            raise
    
    def geocode_shopping_center(self, shopping_center) -> Optional[GeocodingResult]:
        """
        Geocode a single shopping center and update its coordinates.
        
        Args:
            shopping_center: ShoppingCenter model instance
            
        Returns:
            GeocodingResult with success status and coordinates
        """
        try:
            # Build address string from shopping center fields
            address_components = [
                shopping_center.address_street,
                shopping_center.address_city,
                shopping_center.address_state,
                shopping_center.address_zip
            ]
            
            # Create full address string, filtering out empty components
            full_address = ', '.join([comp.strip() for comp in address_components if comp and comp.strip()])
            
            if not full_address:
                logger.warning(f"No address components available for {shopping_center.shopping_center_name}")
                return GeocodingResult(success=False, error_message="No address components available")
            
            # Validate address before geocoding
            validation_result = validate_address_components(
                shopping_center.address_street or "",
                shopping_center.address_city or "",
                shopping_center.address_state or "",
                shopping_center.address_zip or ""
            )
            
            if not validation_result['geocoding_ready']:
                logger.warning(f"Address not ready for geocoding: {shopping_center.shopping_center_name}")
                error_msg = "; ".join(validation_result['errors'])
                return GeocodingResult(success=False, error_message=f"Address validation failed: {error_msg}")
            
            # Perform geocoding
            result = self.geocode_address(full_address)
            
            if result.success:
                # Update shopping center with geocoding results
                self._update_shopping_center_coordinates(shopping_center, result)
                logger.info(f"Successfully geocoded {shopping_center.shopping_center_name}")
            else:
                logger.warning(f"Geocoding failed for {shopping_center.shopping_center_name}: {result.error_message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error geocoding shopping center {shopping_center.shopping_center_name}: {str(e)}")
            return GeocodingResult(success=False, error_message=str(e))
    
    def geocode_address(self, address: str, use_cache: bool = True) -> GeocodingResult:
        """
        Geocode a single address string.
        
        Args:
            address: Full address string to geocode
            use_cache: Whether to use cached results
            
        Returns:
            GeocodingResult with geocoding outcome
        """
        try:
            # Clean the address
            cleaned_address = clean_street_address(address)
            
            # Check cache first if enabled
            if use_cache:
                cached_result = self._get_cached_result(cleaned_address)
                if cached_result:
                    logger.debug(f"Using cached result for address: {cleaned_address}")
                    return cached_result
            
            # Check rate limits before making API call
            if not self._check_rate_limits():
                return GeocodingResult(
                    success=False,
                    error_message="API rate limit exceeded. Please try again later."
                )
            
            # Make Google Maps API call
            logger.debug(f"Geocoding address: {cleaned_address}")
            geocode_result = self.client.geocode(cleaned_address)
            
            if not geocode_result:
                result = GeocodingResult(
                    success=False,
                    error_message="No results found for address",
                    api_status="ZERO_RESULTS"
                )
            else:
                # Parse the first (best) result
                first_result = geocode_result[0]
                location = first_result['geometry']['location']
                
                result = GeocodingResult(
                    success=True,
                    latitude=location['lat'],
                    longitude=location['lng'],
                    formatted_address=first_result.get('formatted_address'),
                    place_id=first_result.get('place_id'),
                    address_components=first_result.get('address_components'),
                    geometry_type=first_result['geometry'].get('location_type'),
                    location_type=first_result['geometry'].get('location_type'),
                    viewport=first_result['geometry'].get('viewport'),
                    confidence_score=self._calculate_confidence_score(first_result),
                    api_status="OK"
                )
            
            # Cache successful results
            if use_cache and result.success:
                self._cache_result(cleaned_address, result)
            
            # Update usage tracking
            self._update_usage_stats()
            
            return result
            
        except googlemaps.exceptions.ApiError as e:
            logger.error(f"Google Maps API error for address '{address}': {str(e)}")
            return GeocodingResult(
                success=False,
                error_message=f"Google Maps API error: {str(e)}",
                api_status=str(e)
            )
        except Exception as e:
            logger.error(f"Unexpected error geocoding address '{address}': {str(e)}")
            return GeocodingResult(
                success=False,
                error_message=f"Geocoding error: {str(e)}"
            )
    
    def batch_geocode_shopping_centers(self, shopping_center_ids: List[int], 
                                     max_concurrent: int = 10) -> BatchGeocodingResult:
        """
        Geocode multiple shopping centers in batch with rate limiting.
        
        Args:
            shopping_center_ids: List of shopping center IDs to geocode
            max_concurrent: Maximum concurrent API requests
            
        Returns:
            BatchGeocodingResult with comprehensive results
        """
        start_time = time.time()
        results = []
        errors = []
        successful_geocodes = 0
        api_calls_used = 0
        
        try:
            from properties.models import ShoppingCenter
            
            # Get shopping centers that need geocoding
            centers_to_geocode = ShoppingCenter.objects.filter(
                id__in=shopping_center_ids
            ).filter(
                latitude__isnull=True,
                longitude__isnull=True
            )
            
            total_centers = centers_to_geocode.count()
            logger.info(f"Starting batch geocoding of {total_centers} shopping centers")
            
            # Process in batches to respect rate limits
            batch_size = min(max_concurrent, self.requests_per_second)
            
            for i in range(0, total_centers, batch_size):
                batch = centers_to_geocode[i:i + batch_size]
                
                # Process current batch
                for center in batch:
                    try:
                        result = self.geocode_shopping_center(center)
                        results.append((center.id, result))
                        api_calls_used += 1
                        
                        if result.success:
                            successful_geocodes += 1
                        else:
                            errors.append(f"Failed to geocode {center.shopping_center_name}: {result.error_message}")
                        
                        # Rate limiting delay
                        time.sleep(1.0 / self.requests_per_second)
                        
                    except Exception as e:
                        error_msg = f"Error processing {center.shopping_center_name}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Brief pause between batches
                if i + batch_size < total_centers:
                    time.sleep(1)
            
            processing_time = time.time() - start_time
            
            batch_result = BatchGeocodingResult(
                total_addresses=total_centers,
                successful_geocodes=successful_geocodes,
                failed_geocodes=total_centers - successful_geocodes,
                api_calls_used=api_calls_used,
                processing_time_seconds=round(processing_time, 2),
                results=results,
                errors=errors
            )
            
            logger.info(f"Batch geocoding completed: {successful_geocodes}/{total_centers} successful in {processing_time:.2f}s")
            return batch_result
            
        except Exception as e:
            logger.error(f"Error in batch geocoding: {str(e)}")
            processing_time = time.time() - start_time
            
            return BatchGeocodingResult(
                total_addresses=len(shopping_center_ids),
                successful_geocodes=successful_geocodes,
                failed_geocodes=len(shopping_center_ids) - successful_geocodes,
                api_calls_used=api_calls_used,
                processing_time_seconds=round(processing_time, 2),
                results=results,
                errors=errors + [f"Batch processing error: {str(e)}"]
            )
    
    def reverse_geocode(self, latitude: float, longitude: float) -> GeocodingResult:
        """
        Reverse geocode coordinates to address.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            GeocodingResult with address information
        """
        try:
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                return GeocodingResult(
                    success=False,
                    error_message="Invalid coordinate range"
                )
            
            # Check rate limits
            if not self._check_rate_limits():
                return GeocodingResult(
                    success=False,
                    error_message="API rate limit exceeded"
                )
            
            # Make reverse geocoding API call
            reverse_result = self.client.reverse_geocode((latitude, longitude))
            
            if not reverse_result:
                return GeocodingResult(
                    success=False,
                    error_message="No address found for coordinates",
                    api_status="ZERO_RESULTS"
                )
            
            first_result = reverse_result[0]
            
            result = GeocodingResult(
                success=True,
                latitude=latitude,
                longitude=longitude,
                formatted_address=first_result.get('formatted_address'),
                place_id=first_result.get('place_id'),
                address_components=first_result.get('address_components'),
                confidence_score=self._calculate_confidence_score(first_result),
                api_status="OK"
            )
            
            self._update_usage_stats()
            return result
            
        except Exception as e:
            logger.error(f"Error reverse geocoding ({latitude}, {longitude}): {str(e)}")
            return GeocodingResult(
                success=False,
                error_message=f"Reverse geocoding error: {str(e)}"
            )
    
    def validate_coordinates(self, latitude: float, longitude: float) -> bool:
        """
        Validate that coordinates are within reasonable bounds for US commercial real estate.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            True if coordinates appear valid
        """
        try:
            # Basic coordinate range validation
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                return False
            
            # US bounds validation (approximate)
            us_bounds = {
                'north': 49.3457868,  # Northern border
                'south': 24.7433195,  # Southern border  
                'east': -66.9513812,  # Eastern border
                'west': -171.791110,  # Western border (including Alaska)
            }
            
            if not (us_bounds['south'] <= latitude <= us_bounds['north']):
                logger.warning(f"Latitude {latitude} outside US bounds")
                return False
            
            if not (us_bounds['west'] <= longitude <= us_bounds['east']):
                logger.warning(f"Longitude {longitude} outside US bounds")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating coordinates: {str(e)}")
            return False
    
    def get_quota_status(self) -> GeocodingQuotaStatus:
        """
        Get current API quota and usage status.
        
        Returns:
            GeocodingQuotaStatus with usage information
        """
        try:
            # Get usage stats from cache
            today = datetime.now().date()
            usage_key = f"{self.cache_prefix}_usage_{today}"
            current_usage = cache.get(usage_key, 0)
            
            remaining = max(0, self.requests_per_day - current_usage)
            
            # Calculate reset time (midnight)
            reset_time = datetime.combine(today + timedelta(days=1), datetime.min.time())
            
            # Estimate cost (approximate Google Maps pricing)
            estimated_cost = current_usage * 0.005  # $0.005 per request
            
            return GeocodingQuotaStatus(
                daily_limit=self.requests_per_day,
                current_usage=current_usage,
                remaining_requests=remaining,
                reset_time=reset_time,
                rate_limit_per_second=self.requests_per_second,
                estimated_cost_usd=round(estimated_cost, 2)
            )
            
        except Exception as e:
            logger.error(f"Error getting quota status: {str(e)}")
            return GeocodingQuotaStatus(0, 0, 0, datetime.now(), 0, 0.0)
    
    # =============================================================================
    # PRIVATE HELPER METHODS
    # =============================================================================
    
    def _update_shopping_center_coordinates(self, shopping_center, result: GeocodingResult):
        """Update shopping center with geocoding results."""
        try:
            with transaction.atomic():
                shopping_center.latitude = Decimal(str(result.latitude))
                shopping_center.longitude = Decimal(str(result.longitude))
                
                # Update PostGIS Point field if it exists
                if hasattr(shopping_center, 'location'):
                    shopping_center.location = Point(result.longitude, result.latitude)
                
                # Store additional geocoding metadata if available
                if result.formatted_address:
                    # Could store formatted address in a separate field if needed
                    pass
                
                # Save only the coordinate fields
                save_fields = ['latitude', 'longitude']
                if hasattr(shopping_center, 'location'):
                    save_fields.append('location')
                
                shopping_center.save(update_fields=save_fields)
                
        except Exception as e:
            logger.error(f"Error updating shopping center coordinates: {str(e)}")
            raise
    
    def _get_cached_result(self, address: str) -> Optional[GeocodingResult]:
        """Get cached geocoding result for address."""
        try:
            cache_key = self._get_cache_key(address)
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return GeocodingResult(**cached_data)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error retrieving cached result: {str(e)}")
            return None
    
    def _cache_result(self, address: str, result: GeocodingResult):
        """Cache successful geocoding result."""
        try:
            if result.success:
                cache_key = self._get_cache_key(address)
                
                # Convert dataclass to dict for caching
                cache_data = {
                    'success': result.success,
                    'latitude': result.latitude,
                    'longitude': result.longitude,
                    'formatted_address': result.formatted_address,
                    'place_id': result.place_id,
                    'confidence_score': result.confidence_score,
                    'api_status': result.api_status,
                    'cached_at': timezone.now().isoformat()
                }
                
                cache.set(cache_key, cache_data, self.cache_timeout)
                logger.debug(f"Cached geocoding result for: {address}")
                
        except Exception as e:
            logger.warning(f"Error caching result: {str(e)}")
    
    def _get_cache_key(self, address: str) -> str:
        """Generate cache key for address."""
        # Normalize address for consistent caching
        normalized = address.lower().strip()
        address_hash = hashlib.md5(normalized.encode()).hexdigest()
        return f"{self.cache_prefix}_addr_{address_hash}"
    
    def _check_rate_limits(self) -> bool:
        """Check if we can make an API request within rate limits."""
        try:
            # Check daily limit
            today = datetime.now().date()
            usage_key = f"{self.cache_prefix}_usage_{today}"
            current_usage = cache.get(usage_key, 0)
            
            if current_usage >= self.requests_per_day:
                logger.warning("Daily API request limit exceeded")
                return False
            
            # Check per-second limit (simplified)
            second_key = f"{self.cache_prefix}_second_{int(time.time())}"
            second_usage = cache.get(second_key, 0)
            
            if second_usage >= self.requests_per_second:
                logger.warning("Per-second API request limit exceeded")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limits: {str(e)}")
            return True  # Allow request if we can't check limits
    
    def _update_usage_stats(self):
        """Update API usage statistics."""
        try:
            # Update daily usage
            today = datetime.now().date()
            usage_key = f"{self.cache_prefix}_usage_{today}"
            current_usage = cache.get(usage_key, 0)
            cache.set(usage_key, current_usage + 1, 60 * 60 * 24)  # 24 hour expiry
            
            # Update per-second usage
            second_key = f"{self.cache_prefix}_second_{int(time.time())}"
            second_usage = cache.get(second_key, 0)
            cache.set(second_key, second_usage + 1, 2)  # 2 second expiry
            
        except Exception as e:
            logger.warning(f"Error updating usage stats: {str(e)}")
    
    def _calculate_confidence_score(self, geocode_result: Dict) -> float:
        """
        Calculate confidence score for geocoding result.
        
        Args:
            geocode_result: Raw Google Maps geocoding result
            
        Returns:
            Confidence score from 0.0 to 1.0
        """
        try:
            base_score = 0.7  # Base confidence for any successful geocoding
            
            # Boost score based on location precision
            location_type = geocode_result.get('geometry', {}).get('location_type', '')
            
            type_bonuses = {
                'ROOFTOP': 0.3,         # Exact address
                'RANGE_INTERPOLATED': 0.2,  # Street address range
                'GEOMETRIC_CENTER': 0.1,    # Geometric center
                'APPROXIMATE': 0.05         # Approximate location
            }
            
            base_score += type_bonuses.get(location_type, 0)
            
            # Boost score based on address component completeness
            address_components = geocode_result.get('address_components', [])
            component_types = [comp.get('types', []) for comp in address_components]
            
            # Check for important address components
            has_street_number = any('street_number' in types for types in component_types)
            has_route = any('route' in types for types in component_types) 
            has_locality = any('locality' in types for types in component_types)
            has_postal_code = any('postal_code' in types for types in component_types)
            
            if has_street_number:
                base_score += 0.05
            if has_route:
                base_score += 0.05
            if has_locality:
                base_score += 0.03
            if has_postal_code:
                base_score += 0.02
            
            return min(1.0, base_score)
            
        except Exception as e:
            logger.warning(f"Error calculating confidence score: {str(e)}")
            return 0.5  # Default moderate confidence
    
    def clear_geocoding_cache(self, older_than_days: int = 30):
        """
        Clear old geocoding cache entries.
        
        Args:
            older_than_days: Clear entries older than this many days
        """
        try:
            # This would require a more sophisticated cache implementation
            # to track cache entry ages. For now, just log the request.
            logger.info(f"Geocoding cache cleanup requested for entries older than {older_than_days} days")
            
            # In a production environment, you might implement this with
            # a custom cache backend or periodic cleanup task
            
        except Exception as e:
            logger.error(f"Error clearing geocoding cache: {str(e)}")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def geocode_address_simple(address: str) -> Optional[Tuple[float, float]]:
    """
    Simple address geocoding function that returns just coordinates.
    
    Args:
        address: Address string to geocode
        
    Returns:
        Tuple of (latitude, longitude) or None if failed
    """
    try:
        service = GeocodingService()
        result = service.geocode_address(address)
        
        if result.success and result.latitude and result.longitude:
            return (result.latitude, result.longitude)
        
        return None
        
    except Exception as e:
        logger.error(f"Error in simple geocoding: {str(e)}")
        return None


def geocode_address(address: str) -> Tuple[float, float]:
    """
    Simple wrapper for geocode_address_simple that matches views.py expectations.
    
    Args:
        address: Address string to geocode
        
    Returns:
        Tuple of (latitude, longitude)
        
    Raises:
        Exception if geocoding fails
    """
    result = geocode_address_simple(address)
    if result is None:
        raise Exception("Geocoding failed: No coordinates returned")
    return result


def is_valid_us_coordinates(latitude: float, longitude: float) -> bool:
    """
    Quick validation for US coordinates.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        
    Returns:
        True if coordinates are within US bounds
    """
    service = GeocodingService()
    return service.validate_coordinates(latitude, longitude)


def get_geocoding_stats() -> Dict[str, Any]:
    """
    Get current geocoding service statistics.
    
    Returns:
        Dictionary with usage and performance stats
    """
    try:
        service = GeocodingService()
        quota_status = service.get_quota_status()
        
        return {
            'api_quota': {
                'daily_limit': quota_status.daily_limit,
                'current_usage': quota_status.current_usage,
                'remaining': quota_status.remaining_requests,
                'usage_percentage': round((quota_status.current_usage / quota_status.daily_limit) * 100, 1)
            },
            'estimated_cost_today': quota_status.estimated_cost_usd,
            'rate_limit_per_second': quota_status.rate_limit_per_second,
            'cache_prefix': service.cache_prefix,
            'service_status': 'operational'
        }
        
    except Exception as e:
        logger.error(f"Error getting geocoding stats: {str(e)}")
        return {
            'service_status': 'error',
            'error_message': str(e)
        }


# =============================================================================
# DJANGO MANAGEMENT COMMAND HELPERS
# =============================================================================

def geocode_all_missing_coordinates(batch_size: int = 50, 
                                  max_daily_requests: int = 1000) -> Dict[str, Any]:
    """
    Geocode all shopping centers missing coordinates.
    
    Args:
        batch_size: Number of centers to process per batch
        max_daily_requests: Maximum API requests to make today
        
    Returns:
        Summary of geocoding operation
    """
    try:
        from properties.models import ShoppingCenter
        
        # Find shopping centers without coordinates
        centers_needing_geocoding = ShoppingCenter.objects.filter(
            latitude__isnull=True,
            longitude__isnull=True
        ).exclude(
            address_street__isnull=True,
            address_city__isnull=True
        )
        
        total_centers = centers_needing_geocoding.count()
        
        if total_centers == 0:
            return {
                'status': 'complete',
                'message': 'All shopping centers already have coordinates',
                'centers_processed': 0
            }
        
        # Check current API usage
        service = GeocodingService()
        quota_status = service.get_quota_status()
        
        available_requests = min(
            quota_status.remaining_requests,
            max_daily_requests
        )
        
        if available_requests <= 0:
            return {
                'status': 'quota_exceeded',
                'message': 'API quota exceeded for today',
                'centers_remaining': total_centers
            }
        
        # Process in batches
        centers_to_process = min(total_centers, available_requests)
        center_ids = list(centers_needing_geocoding.values_list('id', flat=True)[:centers_to_process])
        
        result = service.batch_geocode_shopping_centers(center_ids, batch_size)
        
        return {
            'status': 'completed',
            'centers_processed': result.successful_geocodes,
            'centers_failed': result.failed_geocodes,
            'api_calls_used': result.api_calls_used,
            'processing_time': result.processing_time_seconds,
            'success_rate': round((result.successful_geocodes / result.total_addresses) * 100, 1),
            'remaining_centers': total_centers - centers_to_process,
            'errors': result.errors[:10]  # First 10 errors
        }
        
    except Exception as e:
        logger.error(f"Error in batch geocoding operation: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'centers_processed': 0
        }


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

__all__ = [
    'GeocodingService',
    'GeocodingResult', 
    'BatchGeocodingResult',
    'GeocodingQuotaStatus',
    'geocode_address_simple',
    'geocode_address',  # Added wrapper function
    'is_valid_us_coordinates',
    'get_geocoding_stats',
    'geocode_all_missing_coordinates'
]
