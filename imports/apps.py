# ===== IMPORTS APP CONFIGURATION =====
"""
Django App Configuration for Imports
File: imports/apps.py

This module defines the configuration for the imports Django app,
which handles CSV data ingestion and processing workflows for the
Shop Window application.

App Configuration:
- Manages CSV import batch tracking and processing
- Handles data validation and quality scoring
- Integrates with properties app for data creation
- Supports "stocking shelves" data philosophy
"""

from django.apps import AppConfig


class ImportsConfig(AppConfig):
    """
    Configuration class for the Imports Django app
    
    This app manages data ingestion workflows:
    - CSV file upload and processing
    - Import batch tracking and monitoring
    - Data validation and quality scoring
    - Integration with properties for record creation
    """
    
    # =============================================================================
    # BASIC APP CONFIGURATION
    # =============================================================================
    
    # Use BigAutoField for primary keys (Django 3.2+ best practice)
    default_auto_field = 'django.db.models.BigAutoField'
    
    # App name must match the directory name
    name = 'imports'
    
    # Human-readable name for admin interface
    verbose_name = 'Data Import Management'
    
    # Detailed description for documentation
    verbose_name_plural = 'CSV Import & Data Processing'
    
    # =============================================================================
    # APP INITIALIZATION
    # =============================================================================
    
    def ready(self):
        """
        App initialization method - called when Django starts
        
        This method is called once the app is loaded and all models are available.
        Use this for:
        - Importing signal handlers for import processing
        - Registering custom checks for import functionality
        - Setting up background task integration
        """
        
        # Import signal handlers for import processing automation
        try:
            from . import signals
        except ImportError:
            # signals.py doesn't exist yet - that's okay
            pass
        
        # Import custom management commands for data operations
        try:
            from .management.commands import process_imports
        except ImportError:
            # Management commands not created yet - that's okay
            pass
        
        # Register custom Django checks for import system validation
        from django.core.checks import register, Tags
        from django.conf import settings
        
        @register(Tags.models)
        def check_imports_configuration(app_configs, **kwargs):
            """
            Custom Django check for imports app configuration
            Validates that required settings and dependencies are properly configured
            """
            errors = []
            
            # Check file upload configuration
            if not hasattr(settings, 'FILE_UPLOAD_MAX_MEMORY_SIZE'):
                from django.core.checks import Warning
                errors.append(
                    Warning(
                        'FILE_UPLOAD_MAX_MEMORY_SIZE not configured',
                        hint='Consider setting FILE_UPLOAD_MAX_MEMORY_SIZE for large CSV uploads',
                        obj='imports.views.CSVUploadView',
                        id='imports.W001',
                    )
                )
            
            # Check for required data upload directory
            if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT:
                import os
                upload_dir = os.path.join(settings.MEDIA_ROOT, 'imports')
                if not os.path.exists(upload_dir):
                    from django.core.checks import Warning
                    errors.append(
                        Warning(
                            'Import upload directory does not exist',
                            hint=f'Create directory: {upload_dir}',
                            obj='imports.models.ImportBatch',
                            id='imports.W002',
                        )
                    )
            
            # Check CSV processing dependencies
            try:
                import csv
                import pandas as pd
            except ImportError as e:
                from django.core.checks import Error
                errors.append(
                    Error(
                        f'Required CSV processing library not available: {e}',
                        hint='Install required packages: pip install pandas',
                        obj='imports.services',
                        id='imports.E001',
                    )
                )
            
            # Check properties app integration
            if 'properties' not in settings.INSTALLED_APPS:
                from django.core.checks import Error
                errors.append(
                    Error(
                        'Properties app required but not installed',
                        hint='Add "properties" to INSTALLED_APPS',
                        obj='imports.services',
                        id='imports.E002',
                    )
                )
            
            # Validate sample data availability for development
            if settings.DEBUG:
                try:
                    from properties.management.commands.load_sample_data import Command
                except ImportError:
                    from django.core.checks import Info
                    errors.append(
                        Info(
                            'Sample data command not available',
                            hint='Consider creating load_sample_data management command for development',
                            obj='imports.development',
                            id='imports.I001',
                        )
                    )
            
            return errors
        
        @register(Tags.security)
        def check_import_security(app_configs, **kwargs):
            """
            Security checks for import functionality
            """
            errors = []
            
            # Check file upload security
            if hasattr(settings, 'FILE_UPLOAD_HANDLERS'):
                handlers = settings.FILE_UPLOAD_HANDLERS
                if 'django.core.files.uploadhandler.MemoryFileUploadHandler' in handlers:
                    from django.core.checks import Warning
                    errors.append(
                        Warning(
                            'Memory file upload handler may cause issues with large CSVs',
                            hint='Consider using TemporaryFileUploadHandler for production',
                            obj='imports.security',
                            id='imports.S001',
                        )
                    )
            
            # Check for secure file validation
            allowed_extensions = getattr(settings, 'IMPORT_ALLOWED_EXTENSIONS', ['.csv'])
            if '.exe' in allowed_extensions or '.zip' in allowed_extensions:
                from django.core.checks import Error
                errors.append(
                    Error(
                        'Potentially dangerous file extensions allowed',
                        hint='Restrict IMPORT_ALLOWED_EXTENSIONS to safe formats like .csv',
                        obj='imports.security',
                        id='imports.S002',
                    )
                )
            
            return errors


# =============================================================================
# APP METADATA AND BUSINESS CONTEXT
# =============================================================================

"""
Imports App Business Logic:
==========================

Primary Purpose:
- Handle CSV file uploads and processing for property data
- Track import batches with status monitoring and quality scoring
- Support "stocking shelves" data philosophy: import first, validate later
- Provide admin tools for import management and troubleshooting

Core Workflows:
1. CSV Upload → File Validation → Import Batch Creation
2. Background Processing → Data Extraction → Property Record Creation
3. Quality Scoring → Error Tracking → Completion Notification
4. Admin Review → Data Validation → Quality Improvement

Business Rules:
- Shopping center names are unique identifiers for deduplication
- Newer data can override existing data (rolling CSV approach)
- Quality scores track data completeness and accuracy
- Import batches provide audit trail for data changes

Data Processing Pipeline:
- EXTRACT: Read CSV data and validate structure
- DETERMINE: Process addresses for geocoding and validation
- DEFINE: Create or update shopping center and tenant records

Integration Points:
- Properties App: Creates ShoppingCenter and Tenant model instances
- Services Layer: Uses geocoding for location data enhancement
- Admin Interface: Provides comprehensive import monitoring tools
- API Layer: Exposes import status and management endpoints

MVP Requirements Support:
- CSV import capability for rapid data ingestion
- Import batch tracking for operational monitoring  
- Quality scoring for data improvement workflows
- Admin tools for import management and troubleshooting

Technical Architecture:
- ImportBatch model for tracking import operations
- CSV processing services for data transformation
- Django signals for automation and business logic
- Background task integration for scalable processing
- File upload handling with security validation

Security Considerations:
- File type validation (CSV only)
- File size limits for server protection
- Input sanitization for CSV data
- User authentication for import operations
- Audit logging for data changes

Performance Optimizations:
- Bulk database operations for large datasets
- Streaming CSV processing for memory efficiency
- Background processing for non-blocking operations
- Database indexing for import batch queries
- File cleanup for storage management

Error Handling:
- Comprehensive error logging and reporting
- Partial import support (continue on errors)
- Retry mechanisms for failed imports
- User-friendly error messages and guidance
- Admin tools for error investigation and resolution

Quality Assurance:
- Data validation rules for CSV structure
- Business logic validation for property data
- Quality scoring algorithms for completeness
- Progress tracking for long-running imports
- Success metrics and reporting
"""
