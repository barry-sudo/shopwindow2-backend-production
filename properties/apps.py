"""
Properties App Configuration - Shop Window Backend
Django app configuration for the properties application.

Handles app initialization, signals, and custom app-level settings.
"""

from django.apps import AppConfig
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class PropertiesConfig(AppConfig):
    """
    Configuration for the Properties app.
    
    This app manages:
    - Shopping centers and their spatial data
    - Tenant relationships and lease information
    - Data quality tracking and progressive enrichment
    - Business logic for EXTRACT → DETERMINE → DEFINE workflow
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'properties'
    verbose_name = 'Shopping Centers & Tenants'
    
    def ready(self):
        """
        App initialization - called when Django starts.
        
        Sets up:
        - Signal handlers for business logic automation
        - Model validation and data quality triggers
        - PostGIS spatial index optimization
        """
        # Import signals to register them
        from . import signals
        
        # Register custom model managers and QuerySets
        self.setup_custom_managers()
        
        # Initialize spatial indexing for PostGIS
        self.setup_spatial_indexes()
        
        # Register data quality monitoring
        self.setup_quality_monitoring()
    
    def setup_custom_managers(self):
        """Configure custom model managers for optimized queries"""
        pass  # Custom managers defined in models.py
    
    def setup_spatial_indexes(self):
        """
        Ensure PostGIS spatial indexes are properly configured.
        
        Critical for map performance with large datasets.
        """
        try:
            from django.db import connection
            
            # This will be executed after migrations
            # PostGIS indexes should be created via migrations
            # But we can add runtime optimization here if needed
            
            with connection.cursor() as cursor:
                # Check if spatial indexes exist (non-blocking)
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM pg_indexes 
                    WHERE schemaname = 'public' 
                    AND tablename = 'shopping_centers'
                    AND indexname LIKE '%_geom_%'
                """)
                
                spatial_index_count = cursor.fetchone()[0]
                if spatial_index_count == 0:
                    print("Warning: No spatial indexes found for shopping_centers. Performance may be impacted.")
                
        except Exception as e:
            # Don't block app startup on spatial index issues
            print(f"Spatial index check failed: {str(e)}")
    
    def setup_quality_monitoring(self):
        """Initialize data quality monitoring and auto-scoring"""
        pass  # Quality monitoring handled via signals.py


# =============================================================================
# APP METADATA AND CONFIGURATION
# =============================================================================

# App-level constants and configuration
APP_CONFIG = {
    'version': '1.0.0',
    'description': 'Shopping Centers and Tenants Management',
    'features': {
        'spatial_queries': True,
        'progressive_enrichment': True, 
        'data_quality_scoring': True,
        'multi_location_tenants': True,
        'geocoding_integration': True
    },
    'business_rules': {
        'unique_shopping_center_names': True,
        'tenant_multi_location_support': True,
        'non_blocking_validation': True,
        'progressive_data_philosophy': 'EXTRACT → DETERMINE → DEFINE'
    },
    'data_sources': {
        'csv_import': 'Sprint 2',
        'pdf_extraction': 'Sprint 2', 
        'manual_entry': 'Sprint 1',
        'api_integration': 'Future'
    }
}

# Export app configuration for external access
def get_app_config():
    """Return app configuration for API info endpoint"""
    return APP_CONFIG


# =============================================================================
# CUSTOM APP CHECKS
# =============================================================================

def check_postgis_extension():
    """
    Django system check for PostGIS extension.
    
    Ensures PostGIS is properly installed and configured.
    Critical for spatial functionality.
    """
    from django.core.checks import Error, register, Tags
    from django.db import connection
    
    @register(Tags.database)
    def check_postgis(app_configs, **kwargs):
        errors = []
        
        try:
            with connection.cursor() as cursor:
                # Check if PostGIS extension is installed
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_extension 
                        WHERE extname = 'postgis'
                    )
                """)
                
                postgis_installed = cursor.fetchone()[0]
                
                if not postgis_installed:
                    errors.append(
                        Error(
                            'PostGIS extension is not installed.',
                            hint='Install PostGIS extension: CREATE EXTENSION postgis;',
                            obj='properties.apps.PropertiesConfig',
                            id='properties.E001',
                        )
                    )
                
                # Check PostGIS version compatibility
                cursor.execute("SELECT PostGIS_Version()")
                postgis_version = cursor.fetchone()[0]
                
                # Log PostGIS version for debugging
                print(f"PostGIS version detected: {postgis_version}")
                
        except Exception as e:
            errors.append(
                Error(
                    f'PostGIS check failed: {str(e)}',
                    hint='Ensure PostgreSQL database is running and accessible.',
                    obj='properties.apps.PropertiesConfig',
                    id='properties.E002',
                )
            )
        
        return errors
    
    return check_postgis


def check_required_services():
    """
    Django system check for required external services.
    
    Validates that required services are configured:
    - Google Maps API key
    - Database connectivity
    - Import service dependencies
    """
    from django.core.checks import Warning, register, Tags
    from django.conf import settings
    
    @register(Tags.compatibility)
    def check_services(app_configs, **kwargs):
        warnings = []
        
        # Check Google Maps API key
        if not hasattr(settings, 'GOOGLE_MAPS_API_KEY') or not settings.GOOGLE_MAPS_API_KEY:
            warnings.append(
                Warning(
                    'Google Maps API key not configured.',
                    hint='Set GOOGLE_MAPS_API_KEY in environment variables.',
                    obj='properties.apps.PropertiesConfig',
                    id='properties.W001',
                )
            )
        
        # Check database configuration
        db_config = settings.DATABASES.get('default', {})
        if db_config.get('ENGINE') != 'django.contrib.gis.db.backends.postgis':
            warnings.append(
                Warning(
                    'PostGIS database backend not configured.',
                    hint='Use django.contrib.gis.db.backends.postgis as DATABASE ENGINE.',
                    obj='properties.apps.PropertiesConfig',
                    id='properties.W002',
                )
            )
        
        return warnings
    
    return check_services


# Initialize custom checks
check_postgis_extension()
check_required_services()


# =============================================================================
# APP READY HOOKS
# =============================================================================

def initialize_default_data():
    """
    Initialize default data for the app.
    
    Called during app ready() to set up:
    - Default tenant categories
    - Sample data for development
    - System configuration defaults
    """
    try:
        from .models import TenantCategoryTaxonomy
        
        # Create default tenant categories if they don't exist
        default_categories = [
            'Restaurants & Food Service',
            'Retail - Apparel', 
            'Retail - Electronics',
            'Retail - Grocery & Pharmacy',
            'Professional Services',
            'Health & Beauty',
            'Entertainment & Recreation',
            'Financial Services',
            'Other Services'
        ]
        
        for category_name in default_categories:
            TenantCategoryTaxonomy.objects.get_or_create(
                category_name=category_name,
                defaults={'description': f'Default category: {category_name}'}
            )
        
        print(f"Initialized {len(default_categories)} default tenant categories")
        
    except Exception as e:
        # Don't block app startup on default data issues
        print(f"Default data initialization failed: {str(e)}")


# =============================================================================
# DEVELOPMENT AND DEBUGGING UTILITIES
# =============================================================================

def get_app_status():
    """
    Return current app status for debugging and monitoring.
    
    Provides information about:
    - Database connectivity
    - Spatial functionality status
    - Data counts and quality metrics
    - Configuration status
    """
    try:
        from .models import ShoppingCenter, Tenant
        from django.db import connection
        
        status = {
            'app_name': 'properties',
            'version': APP_CONFIG['version'],
            'database_connected': True,
            'postgis_available': False,
            'data_counts': {
                'shopping_centers': 0,
                'tenants': 0
            },
            'spatial_functionality': False
        }
        
        # Test database connectivity
        try:
            status['data_counts']['shopping_centers'] = ShoppingCenter.objects.count()
            status['data_counts']['tenants'] = Tenant.objects.count()
        except Exception:
            status['database_connected'] = False
        
        # Test PostGIS functionality
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version()")
                postgis_version = cursor.fetchone()[0]
                status['postgis_available'] = True
                status['postgis_version'] = postgis_version
                status['spatial_functionality'] = True
        except Exception:
            pass
        
        return status
        
    except Exception as e:
        return {
            'app_name': 'properties',
            'status': 'error',
            'error': str(e)
        }
