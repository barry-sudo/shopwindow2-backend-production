"""
Django application configuration for the services app.

The services app provides business logic and utility services for the Shop Window platform,
including geocoding, data quality management, and shared business logic components.
"""

from django.apps import AppConfig


class ServicesConfig(AppConfig):
    """
    Application configuration for the services app.
    
    This app provides core business logic and utility services that are shared
    across other Django apps in the Shop Window platform.
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'services'
    verbose_name = 'Services'
    
    def ready(self):
        """
        Perform application initialization.
        
        This method is called when Django starts up and after all apps are loaded.
        Use this for registering signal handlers or performing other initialization.
        """
        # Import signal handlers if any
        # from . import signals
        pass
