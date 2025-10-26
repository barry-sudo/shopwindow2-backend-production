# ===== IMPORTS API VIEWS - CSV IMPORT ENDPOINTS =====
"""
Django REST Framework Views for CSV Import Management
File: imports/views.py

This module provides comprehensive API endpoints for CSV import workflows,
supporting Barry Gilbert's "stocking shelves" data philosophy and 
complete import batch management.

API Endpoints:
- CSV file upload and processing
- Import batch management and monitoring
- Import status tracking and quality reporting
- Validation and template generation
- Admin tools for import management
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from django.http import HttpResponse, Http404
from django.core.files.storage import default_storage
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.conf import settings

from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FileUploadParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser

# Import models and serializers
from .models import ImportBatch
from .serializers import (
    ImportBatchListSerializer,
    ImportBatchDetailSerializer,
    ImportBatchCreateSerializer
)
from .services import CSVImportService, process_csv_import, validate_csv_structure, create_sample_csv

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# IMPORT BATCH VIEWSET
# =============================================================================

class ImportBatchViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ImportBatch model - provides CRUD operations for import batches
    Supports listing, creating, retrieving, updating, and deleting import batches
    """
    queryset = ImportBatch.objects.all().order_by('-created_at')
    serializer_class = ImportBatchListSerializer  # Default for list action
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        This implements different serializers for different operations.
        """
        if self.action == 'retrieve':
            return ImportBatchDetailSerializer
        elif self.action == 'create':
            return ImportBatchCreateSerializer
        return ImportBatchListSerializer
    
    def get_queryset(self):
        """
        Filter queryset based on query parameters and user permissions
        """
        queryset = super().get_queryset()
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by import type if provided
        import_type = self.request.query_params.get('import_type')
        if import_type:
            queryset = queryset.filter(import_type=import_type)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__gte=from_date)
            except ValueError:
                pass
        
        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__lte=to_date)
            except ValueError:
                pass
        
        # Filter by quality score range
        min_quality = self.request.query_params.get('min_quality')
        max_quality = self.request.query_params.get('max_quality')
        
        if min_quality:
            try:
                queryset = queryset.filter(quality_score__gte=int(min_quality))
            except ValueError:
                pass
        
        if max_quality:
            try:
                queryset = queryset.filter(quality_score__lte=int(max_quality))
            except ValueError:
                pass
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Custom creation logic for import batches
        """
        # Set created by user if authenticated
        if self.request.user.is_authenticated:
            serializer.save(created_by=self.request.user)
        else:
            serializer.save()
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Get detailed status of specific import batch
        GET /api/v1/imports/batches/{id}/status/
        """
        import_batch = self.get_object()
        
        status_data = {
            'batch_id': import_batch.batch_id,
            'status': import_batch.status,
            'records_processed': import_batch.records_processed or 0,
            'records_total': import_batch.records_total or 0,
            'quality_score': import_batch.quality_score,
            'has_errors': import_batch.has_errors,
            'error_message': import_batch.error_message,
            'created_at': import_batch.created_at,
            'updated_at': import_batch.updated_at,
            'processing_time': None
        }
        
        # Calculate processing time if completed
        if import_batch.status in ['completed', 'completed_with_errors', 'failed']:
            if import_batch.updated_at and import_batch.created_at:
                delta = import_batch.updated_at - import_batch.created_at
                status_data['processing_time'] = delta.total_seconds()
        
        # Calculate progress percentage
        if import_batch.records_total and import_batch.records_total > 0:
            progress = (import_batch.records_processed or 0) / import_batch.records_total * 100
            status_data['progress_percentage'] = round(progress, 1)
        else:
            status_data['progress_percentage'] = 0
        
        return Response(status_data)
    
    @action(detail=True, methods=['get'])
    def quality(self, request, pk=None):
        """
        Get quality report for specific import batch
        GET /api/v1/imports/batches/{id}/quality/
        """
        import_batch = self.get_object()
        
        quality_data = {
            'batch_id': import_batch.batch_id,
            'quality_score': import_batch.quality_score,
            'has_errors': import_batch.has_errors,
            'error_message': import_batch.error_message,
            'validation_results': import_batch.validation_results,
            'records_processed': import_batch.records_processed,
            'records_total': import_batch.records_total
        }
        
        # Add quality breakdown if validation results exist
        if import_batch.validation_results:
            quality_data['quality_breakdown'] = {
                'warnings': import_batch.validation_results.get('warnings', []),
                'warning_count': import_batch.validation_results.get('warning_count', 0)
            }
        
        return Response(quality_data)
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """
        Retry failed import batch
        POST /api/v1/imports/batches/{id}/retry/
        """
        import_batch = self.get_object()
        
        if import_batch.status != 'failed':
            return Response(
                {'error': 'Only failed imports can be retried'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reset batch for retry
        import_batch.status = 'pending'
        import_batch.error_message = ''
        import_batch.has_errors = False
        import_batch.records_processed = 0
        import_batch.quality_score = None
        import_batch.validation_results = None
        import_batch.save()
        
        # Here you would typically trigger background processing
        # For now, we'll just return success
        
        return Response({
            'message': 'Import batch queued for retry',
            'batch_id': import_batch.batch_id,
            'status': import_batch.status
        })


# =============================================================================
# CSV UPLOAD VIEW
# =============================================================================

class CSVUploadView(APIView):
    """
    Handle CSV file uploads and initiate processing
    POST /api/v1/imports/upload/csv/
    """
    parser_classes = [MultiPartParser, FileUploadParser]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        """
        Upload and process CSV file
        
        Expected form data:
        - file: CSV file to upload
        - import_type: Type of import (optional, defaults to 'csv')
        - notes: Optional notes about the import
        """
        try:
            # Validate file upload
            if 'file' not in request.FILES:
                return Response(
                    {'error': 'No file provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            uploaded_file = request.FILES['file']
            
            # Validate file type
            if not uploaded_file.name.lower().endswith('.csv'):
                return Response(
                    {'error': 'Only CSV files are allowed'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate file size (max 10MB by default)
            max_size = getattr(settings, 'IMPORT_MAX_FILE_SIZE', 10 * 1024 * 1024)  # 10MB
            if uploaded_file.size > max_size:
                return Response(
                    {'error': f'File too large. Maximum size is {max_size // (1024*1024)}MB'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Read file content
            try:
                file_content = uploaded_file.read().decode('utf-8-sig')  # Handle BOM
            except UnicodeDecodeError:
                try:
                    uploaded_file.seek(0)  # Reset file pointer
                    file_content = uploaded_file.read().decode('latin-1')
                except UnicodeDecodeError:
                    return Response(
                        {'error': 'Unable to decode CSV file. Please ensure it is UTF-8 or Latin-1 encoded'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validate CSV structure
            validation_result = validate_csv_structure(file_content)
            if not validation_result['valid']:
                return Response(
                    {
                        'error': 'Invalid CSV structure',
                        'details': validation_result
                    }, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create import batch
            import_batch = ImportBatch.objects.create(
                file_name=uploaded_file.name,
                import_type=request.data.get('import_type', 'csv'),
                status='pending',
                notes=request.data.get('notes', ''),
                file_size=uploaded_file.size,
                records_total=validation_result.get('row_count', 0)
            )
            
            # Process CSV file
            try:
                processing_result = process_csv_import(import_batch, file_content)
                
                return Response({
                    'message': 'CSV upload and processing completed',
                    'import_batch_id': import_batch.batch_id,
                    'batch_id': import_batch.batch_id,
                    'status': import_batch.status,
                    'processing_result': processing_result
                }, status=status.HTTP_201_CREATED)
                
            except Exception as processing_error:
                logger.error(f"CSV processing failed: {str(processing_error)}")
                
                # Update batch with error
                import_batch.status = 'failed'
                import_batch.error_message = str(processing_error)
                import_batch.has_errors = True
                import_batch.save()
                
                return Response({
                    'error': 'CSV processing failed',
                    'import_batch_id': import_batch.batch_id,
                    'details': str(processing_error)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            logger.error(f"CSV upload failed: {str(e)}")
            return Response(
                {'error': f'Upload failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# CSV VALIDATION VIEW
# =============================================================================

class CSVValidationView(APIView):
    """
    Validate CSV structure without processing data
    POST /api/v1/imports/validate/csv/
    """
    parser_classes = [MultiPartParser, FileUploadParser]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        """
        Validate CSV file structure without importing data
        """
        try:
            if 'file' not in request.FILES:
                return Response(
                    {'error': 'No file provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            uploaded_file = request.FILES['file']
            
            # Read and decode file
            try:
                file_content = uploaded_file.read().decode('utf-8-sig')
            except UnicodeDecodeError:
                try:
                    uploaded_file.seek(0)
                    file_content = uploaded_file.read().decode('latin-1')
                except UnicodeDecodeError:
                    return Response(
                        {'error': 'Unable to decode CSV file'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validate structure
            validation_result = validate_csv_structure(file_content)
            
            return Response({
                'file_name': uploaded_file.name,
                'file_size': uploaded_file.size,
                'validation_result': validation_result
            })
            
        except Exception as e:
            logger.error(f"CSV validation failed: {str(e)}")
            return Response(
                {'error': f'Validation failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# CSV TEMPLATE VIEW
# =============================================================================

class CSVTemplateView(APIView):
    """
    Download CSV template with proper headers
    GET /api/v1/imports/template/csv/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        """
        Generate and return CSV template file
        """
        try:
            # Create sample CSV content
            csv_content = create_sample_csv()
            
            # Create HTTP response with CSV
            response = HttpResponse(csv_content, content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="shop_window_import_template.csv"'
            
            return response
            
        except Exception as e:
            logger.error(f"Template generation failed: {str(e)}")
            return Response(
                {'error': f'Template generation failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# IMPORT STATISTICS VIEW
# =============================================================================

class ImportStatsView(APIView):
    """
    Get import statistics and dashboard data
    GET /api/v1/imports/stats/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        """
        Return comprehensive import statistics
        """
        try:
            # Get date range for filtering (default: last 30 days)
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)
            
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            if date_from:
                try:
                    start_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                except ValueError:
                    pass
            
            if date_to:
                try:
                    end_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                except ValueError:
                    pass
            
            # Get base queryset
            queryset = ImportBatch.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date
            )
            
            # Calculate statistics
            total_imports = queryset.count()
            completed_imports = queryset.filter(status='completed').count()
            failed_imports = queryset.filter(status='failed').count()
            processing_imports = queryset.filter(status='processing').count()
            pending_imports = queryset.filter(status='pending').count()
            
            # Calculate average quality score
            avg_quality = queryset.exclude(
                quality_score__isnull=True
            ).aggregate(
                avg_score=Avg('quality_score')
            )['avg_score']
            
            # Calculate total records processed
            total_records = queryset.aggregate(
                total_processed=Count('records_processed')
            )['total_processed'] or 0
            
            # Get recent activity
            recent_imports = queryset.order_by('-created_at')[:10]
            recent_activity = [
                {
                    'batch_id': batch.batch_id,
                    'file_name': batch.file_name,
                    'status': batch.status,
                    'created_at': batch.created_at,
                    'records_processed': batch.records_processed,
                    'quality_score': batch.quality_score
                }
                for batch in recent_imports
            ]
            
            # Status distribution
            status_distribution = {
                'completed': completed_imports,
                'failed': failed_imports,
                'processing': processing_imports,
                'pending': pending_imports
            }
            
            return Response({
                'date_range': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'summary': {
                    'total_imports': total_imports,
                    'completed_imports': completed_imports,
                    'failed_imports': failed_imports,
                    'processing_imports': processing_imports,
                    'pending_imports': pending_imports,
                    'success_rate': round((completed_imports / total_imports * 100) if total_imports > 0 else 0, 1),
                    'average_quality_score': round(avg_quality, 1) if avg_quality else None,
                    'total_records_processed': total_records
                },
                'status_distribution': status_distribution,
                'recent_activity': recent_activity
            })
            
        except Exception as e:
            logger.error(f"Stats generation failed: {str(e)}")
            return Response(
                {'error': f'Stats generation failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# RECENT IMPORTS VIEW
# =============================================================================

class RecentImportsView(APIView):
    """
    Get recent import activity
    GET /api/v1/imports/recent/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        """
        Return recent import batches
        """
        try:
            # Get limit parameter (default: 20, max: 100)
            limit = min(int(request.query_params.get('limit', 20)), 100)
            
            # Get recent imports
            recent_imports = ImportBatch.objects.order_by('-created_at')[:limit]
            
            # Serialize data
            serializer = ImportBatchListSerializer(recent_imports, many=True)
            
            return Response({
                'count': len(serializer.data),
                'results': serializer.data
            })
            
        except Exception as e:
            logger.error(f"Recent imports query failed: {str(e)}")
            return Response(
                {'error': f'Query failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# IMPORT STATUS VIEW
# =============================================================================

class ImportStatusView(APIView):
    """
    Get status of specific import batch by batch ID
    GET /api/v1/imports/batches/{batch_id}/status/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, batch_id, format=None):
        """
        Get detailed status of import batch
        """
        try:
            import_batch = ImportBatch.objects.get(batch_id=batch_id)
            
            status_data = {
                'batch_id': import_batch.batch_id,
                'status': import_batch.status,
                'file_name': import_batch.file_name,
                'records_processed': import_batch.records_processed or 0,
                'records_total': import_batch.records_total or 0,
                'quality_score': import_batch.quality_score,
                'has_errors': import_batch.has_errors,
                'error_message': import_batch.error_message,
                'created_at': import_batch.created_at,
                'updated_at': import_batch.updated_at
            }
            
            # Calculate progress
            if import_batch.records_total and import_batch.records_total > 0:
                progress = (import_batch.records_processed or 0) / import_batch.records_total * 100
                status_data['progress_percentage'] = round(progress, 1)
            else:
                status_data['progress_percentage'] = 0
            
            return Response(status_data)
            
        except ImportBatch.DoesNotExist:
            raise Http404("Import batch not found")
        except Exception as e:
            logger.error(f"Status query failed: {str(e)}")
            return Response(
                {'error': f'Status query failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# ADMIN VIEWS
# =============================================================================

class LoadSampleDataView(APIView):
    """
    Load sample data for development and testing
    POST /api/v1/imports/sample-data/load/
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request, format=None):
        """
        Load sample property data
        """
        try:
            # Create sample CSV content
            sample_csv = create_sample_csv()
            
            # Create import batch for sample data
            import_batch = ImportBatch.objects.create(
                file_name='sample_data.csv',
                import_type='sample',
                status='pending',
                notes='System generated sample data'
            )
            
            # Process sample data
            processing_result = process_csv_import(import_batch, sample_csv)
            
            return Response({
                'message': 'Sample data loaded successfully',
                'import_batch_id': import_batch.batch_id,
                'processing_result': processing_result
            })
            
        except Exception as e:
            logger.error(f"Sample data loading failed: {str(e)}")
            return Response(
                {'error': f'Sample data loading failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClearImportsView(APIView):
    """
    Clear import data (admin only)
    DELETE /api/v1/imports/admin/clear/
    """
    permission_classes = [IsAdminUser]
    
    def delete(self, request, format=None):
        """
        Clear old import batches
        """
        try:
            # Get parameters
            days_old = int(request.query_params.get('days_old', 30))
            status_filter = request.query_params.get('status')
            
            # Calculate cutoff date
            cutoff_date = timezone.now() - timedelta(days=days_old)
            
            # Build queryset
            queryset = ImportBatch.objects.filter(created_at__lt=cutoff_date)
            
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            
            # Count and delete
            count = queryset.count()
            queryset.delete()
            
            return Response({
                'message': f'Cleared {count} import batch(es)',
                'deleted_count': count,
                'cutoff_date': cutoff_date.isoformat()
            })
            
        except Exception as e:
            logger.error(f"Import clearing failed: {str(e)}")
            return Response(
                {'error': f'Import clearing failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
