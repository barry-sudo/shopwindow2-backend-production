# ===== SERVICES INTEGRATION LAYER =====
"""
Centralized service integration layer for Shop Window backend.
Provides consistent interfaces and error handling for all business services.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.conf import settings

logger = logging.getLogger(__name__)


# =============================================================================
# SERVICE INTEGRATION EXCEPTIONS
# =============================================================================

class ServiceIntegrationError(Exception):
    """Base exception for service integration errors."""
    pass


class GeocodingServiceError(ServiceIntegrationError):
    """Raised when geocoding operations fail."""
    pass


class BusinessLogicError(ServiceIntegrationError):
    """Raised when business logic calculations fail."""
    pass


# =============================================================================
# GEOCODING SERVICE INTEGRATION
# =============================================================================

def safe_geocode_address(full_address: str) -> Optional[Tuple[float, float]]:
    """
    Safely geocode an address with comprehensive error handling.
    
    Args:
        full_address: Complete address string
        
    Returns:
        Tuple of (latitude, longitude) or None if geocoding fails
        
    Raises:
        GeocodingServiceError: If service is misconfigured
    """
    try:
        from .geocoding import geocode_address
        return geocode_address(full_address)
    except ImportError:
        logger.error("Geocoding service not available - check geocoding.py implementation")
        return None
    except Exception as e:
        logger.warning(f"Geocoding failed for address '{full_address}': {str(e)}")
        return None


def batch_geocode_centers(shopping_centers, batch_size: int = 10) -> Dict[int, Optional[Tuple[float, float]]]:
    """
    Geocode multiple shopping centers with rate limiting.
    
    Args:
        shopping_centers: QuerySet or list of ShoppingCenter objects
        batch_size: Number of requests per batch
        
    Returns:
        Dictionary mapping shopping center IDs to coordinates or None
    """
    results = {}
    
    for i, center in enumerate(shopping_centers):
        if i > 0 and i % batch_size == 0:
            # Rate limiting - pause between batches
            import time
            time.sleep(1)
        
        if hasattr(center, 'full_address') and center.full_address:
            results[center.id] = safe_geocode_address(center.full_address)
        else:
            results[center.id] = None
            
    return results


# =============================================================================
# BUSINESS LOGIC SERVICE INTEGRATION
# =============================================================================

def safe_calculate_quality_score(shopping_center) -> int:
    """
    Safely calculate data quality score with error handling.
    
    Args:
        shopping_center: ShoppingCenter instance
        
    Returns:
        Quality score (0-100) or 0 if calculation fails
    """
    try:
        from .business_logic import calculate_quality_score
        return calculate_quality_score(shopping_center)
    except ImportError:
        logger.error("Business logic service not available - check business_logic.py")
        return 0
    except Exception as e:
        logger.warning(f"Quality score calculation failed for {shopping_center}: {str(e)}")
        return 0


def safe_calculate_center_type(gla: Optional[int]) -> Optional[str]:
    """
    Safely determine center type from GLA with error handling.
    
    Args:
        gla: Gross Leasable Area in square feet
        
    Returns:
        Center type string or None if calculation fails
    """
    try:
        from .business_logic import calculate_center_type
        return calculate_center_type(gla)
    except ImportError:
        logger.error("Business logic service not available for center type calculation")
        return None
    except Exception as e:
        logger.warning(f"Center type calculation failed for GLA {gla}: {str(e)}")
        return None


def safe_validate_shopping_center_data(data: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    """
    Safely validate shopping center data with comprehensive error handling.
    
    Args:
        data: Dictionary of shopping center data
        
    Returns:
        Tuple of (is_valid, validation_errors)
    """
    try:
        from .business_logic import validate_shopping_center_data
        return validate_shopping_center_data(data)
    except ImportError:
        logger.error("Business logic validation service not available")
        return False, {"service": "Validation service not available"}
    except Exception as e:
        logger.warning(f"Validation failed: {str(e)}")
        return False, {"validation": str(e)}


# =============================================================================
# IMPORT SERVICE INTEGRATION
# =============================================================================

def safe_process_csv_import(file_data, import_batch):
    """
    Safely process CSV import with comprehensive error handling.
    
    Args:
        file_data: CSV file data
        import_batch: ImportBatch instance
        
    Returns:
        Processing results dictionary
    """
    try:
        # Import here to avoid circular imports
        from imports.services import CSVImportService
        
        service = CSVImportService(import_batch)
        return service.process_file(file_data)
        
    except ImportError as e:
        error_msg = f"CSV import service not available: {str(e)}"
        logger.error(error_msg)
        import_batch.mark_as_failed(error_msg)
        return {"success": False, "error": error_msg}
        
    except Exception as e:
        error_msg = f"CSV import processing failed: {str(e)}"
        logger.error(error_msg)
        import_batch.mark_as_failed(error_msg)
        return {"success": False, "error": error_msg}


# =============================================================================
# HEALTH CHECK SERVICES
# =============================================================================

def check_service_health() -> Dict[str, Dict[str, Any]]:
    """
    Check health of all integrated services.
    
    Returns:
        Dictionary with health status of each service
    """
    health_status = {}
    
    # Check geocoding service
    try:
        from .geocoding import geocode_address
        health_status['geocoding'] = {
            'available': True,
            'api_key_configured': bool(getattr(settings, 'GOOGLE_MAPS_API_KEY', None))
        }
    except ImportError:
        health_status['geocoding'] = {
            'available': False,
            'error': 'Module not found'
        }
    
    # Check business logic service
    try:
        from .business_logic import calculate_quality_score
        health_status['business_logic'] = {
            'available': True
        }
    except ImportError:
        health_status['business_logic'] = {
            'available': False,
            'error': 'Module not found'
        }
    
    # Check import service
    try:
        from imports.services import CSVImportService
        health_status['import_service'] = {
            'available': True
        }
    except ImportError:
        health_status['import_service'] = {
            'available': False,
            'error': 'Module not found'
        }
    
    return health_status


# =============================================================================
# SERVICE CONFIGURATION VALIDATION
# =============================================================================

def validate_service_configuration() -> Tuple[bool, list]:
    """
    Validate that all required services are properly configured.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check Google Maps API configuration
    if not getattr(settings, 'GOOGLE_MAPS_API_KEY', None):
        errors.append("GOOGLE_MAPS_API_KEY not configured in settings")
    
    # Check database configuration
    if not getattr(settings, 'DATABASES', {}).get('default'):
        errors.append("Database configuration missing")
    
    # Check required Django apps
    required_apps = ['django.contrib.gis', 'rest_framework', 'properties', 'imports']
    installed_apps = getattr(settings, 'INSTALLED_APPS', [])
    
    for app in required_apps:
        if app not in installed_apps:
            errors.append(f"Required app '{app}' not in INSTALLED_APPS")
    
    return len(errors) == 0, errors


# =============================================================================
# EXPORT FOR EASY IMPORTS
# =============================================================================

__all__ = [
    'safe_geocode_address',
    'batch_geocode_centers', 
    'safe_calculate_quality_score',
    'safe_calculate_center_type',
    'safe_validate_shopping_center_data',
    'safe_process_csv_import',
    'check_service_health',
    'validate_service_configuration',
    'ServiceIntegrationError',
    'GeocodingServiceError',
    'BusinessLogicError',
]