# services/geocoding.py
"""
Google Maps Geocoding Service for Shop Window Backend
Converts property addresses to lat/lng coordinates
"""

import os
import time
import logging
from typing import Optional, Tuple
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GeocodingService:
    """
    Service for geocoding addresses using Google Maps Geocoding API.
    Handles rate limiting, error handling, and coordinate extraction.
    """
    
    def __init__(self):
        self.api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_API_KEY not set in environment variables")
        
        self.base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        self.rate_limit_delay = 0.2  # 200ms between requests (5 per second max)
    
    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Geocode a single address and return (latitude, longitude).
        
        Args:
            address: Full address string (e.g., "1234 Main St, Wilmington, DE 19342")
        
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not self.api_key:
            logger.error("Cannot geocode: GOOGLE_MAPS_API_KEY not configured")
            return None
        
        if not address or not address.strip():
            logger.warning("Cannot geocode: Empty address provided")
            return None
        
        try:
            # Make API request
            params = {
                'address': address,
                'key': self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check response status
            if data['status'] == 'OK' and len(data['results']) > 0:
                location = data['results'][0]['geometry']['location']
                lat = float(location['lat'])
                lng = float(location['lng'])
                
                logger.info(f"Successfully geocoded: {address} -> ({lat}, {lng})")
                return (lat, lng)
            
            elif data['status'] == 'ZERO_RESULTS':
                logger.warning(f"No results found for address: {address}")
                return None
            
            elif data['status'] == 'OVER_QUERY_LIMIT':
                logger.error("Google Maps API query limit exceeded")
                return None
            
            else:
                logger.warning(f"Geocoding failed with status: {data['status']} for address: {address}")
                return None
        
        except requests.RequestException as e:
            logger.error(f"Network error during geocoding: {str(e)}")
            return None
        
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing geocoding response: {str(e)}")
            return None
    
    def geocode_shopping_center(self, shopping_center) -> bool:
        """
        Geocode a ShoppingCenter model instance and update its lat/lng fields.
        
        Args:
            shopping_center: ShoppingCenter model instance
        
        Returns:
            True if geocoding succeeded and coordinates were saved, False otherwise
        """
        # Skip if already geocoded
        if shopping_center.latitude is not None and shopping_center.longitude is not None:
            logger.info(f"Skipping already geocoded property: {shopping_center.shopping_center_name}")
            return True
        
        # Build address string
        address_parts = []
        
        if shopping_center.address_street:
            address_parts.append(shopping_center.address_street)
        
        if shopping_center.address_city:
            address_parts.append(shopping_center.address_city)
        
        if shopping_center.address_state:
            address_parts.append(shopping_center.address_state)
        
        if shopping_center.address_zip:
            address_parts.append(shopping_center.address_zip)
        
        if not address_parts:
            logger.warning(f"Cannot geocode {shopping_center.shopping_center_name}: No address information")
            return False
        
        address = ', '.join(address_parts)
        
        # Geocode the address
        coordinates = self.geocode_address(address)
        
        if coordinates:
            latitude, longitude = coordinates
            shopping_center.latitude = latitude
            shopping_center.longitude = longitude
            shopping_center.save()
            
            logger.info(f"Updated coordinates for {shopping_center.shopping_center_name}")
            return True
        
        return False
    
    def batch_geocode_shopping_centers(self, queryset, delay: float = None) -> dict:
        """
        Geocode multiple shopping centers with rate limiting.
        
        Args:
            queryset: QuerySet of ShoppingCenter objects to geocode
            delay: Optional custom delay between requests (seconds)
        
        Returns:
            Dictionary with success/failure counts and details
        """
        if delay is None:
            delay = self.rate_limit_delay
        
        results = {
            'total': queryset.count(),
            'success': 0,
            'skipped': 0,
            'failed': 0,
            'failed_ids': []
        }
        
        logger.info(f"Starting batch geocoding of {results['total']} properties")
        
        for shopping_center in queryset:
            # Check if already geocoded
            if shopping_center.latitude is not None and shopping_center.longitude is not None:
                results['skipped'] += 1
                continue
            
            # Geocode the property
            success = self.geocode_shopping_center(shopping_center)
            
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
                results['failed_ids'].append(shopping_center.id)
            
            # Rate limiting - wait between requests
            if delay > 0:
                time.sleep(delay)
        
        logger.info(
            f"Batch geocoding complete: {results['success']} success, "
            f"{results['skipped']} skipped, {results['failed']} failed"
        )
        
        return results


# Singleton instance
geocoding_service = GeocodingService()
# Backward compatibility function for existing imports
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Standalone function that uses the singleton geocoding service.
    Maintained for backward compatibility with existing code.
    
    Args:
        address: Full address string
        
    Returns:
        Tuple of (latitude, longitude) or None if geocoding fails
    """
    return geocoding_service.geocode_address(address)
