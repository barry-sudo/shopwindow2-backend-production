"""
Import endpoints for Shop Window.

Handles file uploads and processes CSV data imports.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import tempfile
import os


@api_view(['POST'])
def upload_csv(request):
    """
    CSV upload endpoint.
    
    Accepts CSV file upload, saves temporarily, processes import, and returns stats.
    
    Request:
        POST /api/v1/imports/csv/
        Content-Type: multipart/form-data
        Body: file (CSV file)
    
    Response:
        {
            "success": true,
            "stats": {
                "centers_created": 5,
                "centers_updated": 0,
                "geocoding_success": 5,
                "geocoding_failed": 0,
                "tenants_created": 127,
                "tenants_updated": 0,
                "rows_processed": 132,
                "errors": []
            },
            "message": "Import completed successfully"
        }
    
    Error Response:
        {
            "success": false,
            "error": "Error message",
            "details": "Additional error details"
        }
    """
    
    # Check if file was uploaded
    if 'file' not in request.FILES:
        return Response(
            {
                'success': False,
                'error': 'No file provided',
                'details': 'Please upload a CSV file using the "file" field'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    uploaded_file = request.FILES['file']
    
    # Validate file extension
    if not uploaded_file.name.endswith('.csv'):
        return Response(
            {
                'success': False,
                'error': 'Invalid file type',
                'details': 'Only CSV files are supported'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Save file temporarily
    temp_file = None
    try:
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, 
            suffix='.csv',
            mode='wb'
        )
        
        # Write uploaded file to temp location
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        
        temp_file.close()
        
        # Import the CSV using the refactored function
        from properties.management.commands.import_csv_simple import run_import
        
        # Run import (clear_data=False by default - progressive enrichment)
        stats = run_import(temp_file.name, clear_data=False)
        
        # Clean up temp file
        os.unlink(temp_file.name)
        
        # Return success response
        if stats['success']:
            return Response(
                {
                    'success': True,
                    'stats': stats,
                    'message': 'Import completed successfully'
                },
                status=status.HTTP_200_OK
            )
        else:
            # Import function returned success=False
            return Response(
                {
                    'success': False,
                    'error': stats.get('error_message', 'Import failed'),
                    'stats': stats
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    except ValueError as e:
        # API key or validation errors
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        
        return Response(
            {
                'success': False,
                'error': 'Configuration error',
                'details': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    except FileNotFoundError as e:
        # File system errors
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        
        return Response(
            {
                'success': False,
                'error': 'File not found',
                'details': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    except Exception as e:
        # Unexpected errors
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        
        return Response(
            {
                'success': False,
                'error': 'Import failed',
                'details': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def upload_pdf(request):
    """
    PDF upload endpoint - NOT YET IMPLEMENTED.
    
    Returns HTTP 501 Not Implemented with helpful message.
    """
    return Response(
        {
            'success': False,
            'error': 'PDF import not yet implemented',
            'details': 'This feature is planned for a future release. Please use CSV import for now.',
            'alternative': '/api/v1/imports/csv/'
        },
        status=status.HTTP_501_NOT_IMPLEMENTED
    )


@api_view(['GET'])
def import_status(request):
    """
    Get import statistics and system status.
    
    Returns current database counts and import readiness.
    """
    try:
        from properties.models import ShoppingCenter, Tenant
        
        # Check Google Maps API key
        google_maps_configured = bool(os.environ.get('GOOGLE_MAPS_API_KEY'))
        
        return Response(
            {
                'success': True,
                'ready': google_maps_configured,
                'stats': {
                    'total_centers': ShoppingCenter.objects.count(),
                    'geocoded_centers': ShoppingCenter.objects.exclude(
                        latitude__isnull=True
                    ).count(),
                    'total_tenants': Tenant.objects.count(),
                },
                'configuration': {
                    'google_maps_api_key': google_maps_configured
                }
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'error': 'Failed to get import status',
                'details': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
