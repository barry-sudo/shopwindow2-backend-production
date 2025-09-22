# ===== IMPORTS SERIALIZERS =====
"""
Serializers for Import Management API endpoints.
Handles ImportBatch model serialization, file upload validation,
and import status/progress tracking.
"""

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from decimal import Decimal
import hashlib
import logging

from .models import ImportBatch, ImportError

logger = logging.getLogger(__name__)


# =============================================================================
# IMPORT BATCH SERIALIZERS
# =============================================================================

class ImportBatchListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for import batch list views.
    Shows essential information for monitoring and management.
    """
    
    # Computed fields
    processing_duration = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    import_type_display = serializers.CharField(source='get_import_type_display', read_only=True)
    
    class Meta:
        model = ImportBatch
        fields = [
            'id',
            'batch_id', 
            'import_type',
            'import_type_display',
            'status',
            'status_display',
            'file_name',
            'file_size',
            'records_total',
            'records_processed',
            'records_created',
            'records_updated',
            'records_skipped',
            'quality_score',
            'has_errors',
            'created_at',
            'started_at',
            'completed_at',
            'processing_duration',
            'success_rate'
        ]
        read_only_fields = [
            'id', 'batch_id', 'created_at', 'processing_duration', 'success_rate'
        ]
    
    def get_processing_duration(self, obj):
        """Get processing duration in seconds."""
        duration = obj.processing_duration
        return duration.total_seconds() if duration else None
    
    def get_success_rate(self, obj):
        """Get success rate percentage."""
        return obj.success_rate


class ImportBatchDetailSerializer(serializers.ModelSerializer):
    """
    Complete serializer for import batch detail views.
    Includes all fields, related errors, and computed properties.
    """
    
    # Computed fields
    processing_duration = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    import_type_display = serializers.CharField(source='get_import_type_display', read_only=True)
    
    # Related fields
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    error_count = serializers.SerializerMethodField()
    recent_errors = serializers.SerializerMethodField()
    
    class Meta:
        model = ImportBatch
        fields = [
            'id',
            'batch_id',
            'import_type',
            'import_type_display', 
            'status',
            'status_display',
            'file_name',
            'file_size',
            'file_hash',
            'records_total',
            'records_processed',
            'records_created',
            'records_updated',
            'records_skipped',
            'quality_score',
            'has_errors',
            'error_message',
            'validation_results',
            'notes',
            'metadata',
            'created_at',
            'updated_at',
            'started_at',
            'completed_at',
            'created_by_username',
            'processing_duration',
            'success_rate',
            'error_count',
            'recent_errors'
        ]
        read_only_fields = [
            'id', 'batch_id', 'file_hash', 'created_at', 'updated_at',
            'processing_duration', 'success_rate', 'error_count', 'recent_errors'
        ]
    
    def get_processing_duration(self, obj):
        """Get processing duration in seconds."""
        duration = obj.processing_duration
        return duration.total_seconds() if duration else None
    
    def get_success_rate(self, obj):
        """Get success rate percentage."""
        return obj.success_rate
    
    def get_error_count(self, obj):
        """Get total number of import errors."""
        return obj.errors.count()
    
    def get_recent_errors(self, obj):
        """Get recent import errors (last 10)."""
        recent_errors = obj.errors.order_by('-created_at')[:10]
        return ImportErrorSerializer(recent_errors, many=True).data


class ImportBatchCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new import batches.
    Handles file upload validation and initial batch setup.
    """
    
    # File upload field (not stored in model directly)
    file = serializers.FileField(write_only=True, required=False)
    
    class Meta:
        model = ImportBatch
        fields = [
            'import_type',
            'file',
            'notes'
        ]
        
    def validate_file(self, file):
        """Validate uploaded file."""
        if not file:
            return file
            
        # File size validation (50MB limit)
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size > max_size:
            raise serializers.ValidationError(
                f"File size exceeds limit of {max_size // (1024*1024)}MB"
            )
        
        # File type validation
        allowed_extensions = {'.csv', '.xlsx', '.xls', '.pdf'}
        file_extension = self._get_file_extension(file.name)
        
        if file_extension not in allowed_extensions:
            raise serializers.ValidationError(
                f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # MIME type validation
        allowed_mime_types = {
            'text/csv',
            'application/csv',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/pdf'
        }
        
        if file.content_type not in allowed_mime_types:
            raise serializers.ValidationError(
                f"Invalid file type: {file.content_type}"
            )
        
        return file
    
    def validate_import_type(self, import_type):
        """Validate import type matches file type."""
        file = self.initial_data.get('file')
        if file and hasattr(file, 'name'):
            file_extension = self._get_file_extension(file.name)
            
            # Validate import type matches file extension
            if import_type == 'CSV' and file_extension not in ['.csv']:
                raise serializers.ValidationError(
                    "Import type 'CSV' requires a .csv file"
                )
            elif import_type == 'PDF' and file_extension not in ['.pdf']:
                raise serializers.ValidationError(
                    "Import type 'PDF' requires a .pdf file"
                )
        
        return import_type
    
    def create(self, validated_data):
        """Create import batch with file processing."""
        file = validated_data.pop('file', None)
        
        # Create import batch
        import_batch = ImportBatch.objects.create(
            **validated_data,
            created_by=self.context['request'].user
        )
        
        # Process file if provided
        if file:
            import_batch.file_name = file.name
            import_batch.file_size = file.size
            import_batch.file_hash = self._calculate_file_hash(file)
            import_batch.save()
            
            # TODO: Trigger background processing
            # process_import_file.delay(import_batch.id, file)
        
        return import_batch
    
    def _get_file_extension(self, filename):
        """Get file extension in lowercase."""
        return '.' + filename.lower().split('.')[-1] if '.' in filename else ''
    
    def _calculate_file_hash(self, file):
        """Calculate SHA256 hash of uploaded file."""
        hasher = hashlib.sha256()
        for chunk in file.chunks():
            hasher.update(chunk)
        return hasher.hexdigest()


# =============================================================================
# IMPORT ERROR SERIALIZERS
# =============================================================================

class ImportErrorSerializer(serializers.ModelSerializer):
    """
    Serializer for import errors.
    Used in error reporting and troubleshooting.
    """
    
    error_type_display = serializers.CharField(source='get_error_type_display', read_only=True)
    
    class Meta:
        model = ImportError
        fields = [
            'id',
            'error_type',
            'error_type_display',
            'row_number',
            'field_name',
            'error_message',
            'raw_data',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# =============================================================================
# FILE UPLOAD SERIALIZERS
# =============================================================================

class FileUploadSerializer(serializers.Serializer):
    """
    Serializer for standalone file uploads.
    Used for CSV/PDF upload endpoints.
    """
    
    file = serializers.FileField()
    import_type = serializers.ChoiceField(
        choices=ImportBatch.IMPORT_TYPE_CHOICES,
        required=False
    )
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    
    def validate_file(self, file):
        """Comprehensive file validation."""
        # File size validation
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size > max_size:
            raise serializers.ValidationError(
                f"File size ({file.size} bytes) exceeds limit of {max_size} bytes"
            )
        
        # File extension validation
        allowed_extensions = {'.csv', '.xlsx', '.xls', '.pdf'}
        file_extension = self._get_file_extension(file.name)
        
        if file_extension not in allowed_extensions:
            raise serializers.ValidationError(
                f"File extension '{file_extension}' not allowed. "
                f"Allowed extensions: {', '.join(allowed_extensions)}"
            )
        
        # Content validation
        try:
            if file_extension == '.csv':
                # Basic CSV validation
                file.seek(0)
                first_line = file.readline(1024).decode('utf-8', errors='ignore')
                file.seek(0)
                
                if not first_line or ',' not in first_line:
                    raise serializers.ValidationError(
                        "Invalid CSV format - no comma separators found"
                    )
            
            elif file_extension == '.pdf':
                # Basic PDF validation
                file.seek(0)
                first_bytes = file.read(4)
                file.seek(0)
                
                if first_bytes != b'%PDF':
                    raise serializers.ValidationError(
                        "Invalid PDF file format"
                    )
        
        except Exception as e:
            raise serializers.ValidationError(
                f"File content validation failed: {str(e)}"
            )
        
        return file
    
    def _get_file_extension(self, filename):
        """Get file extension in lowercase."""
        return '.' + filename.lower().split('.')[-1] if '.' in filename else ''


# =============================================================================
# IMPORT PROGRESS SERIALIZERS
# =============================================================================

class ImportProgressSerializer(serializers.Serializer):
    """
    Serializer for import progress tracking.
    Used for real-time progress updates.
    """
    
    batch_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    records_processed = serializers.IntegerField(read_only=True)
    records_total = serializers.IntegerField(read_only=True)
    estimated_time_remaining = serializers.SerializerMethodField()
    current_operation = serializers.CharField(read_only=True, required=False)
    
    def get_progress_percentage(self, obj):
        """Calculate progress percentage."""
        if hasattr(obj, 'records_total') and obj.records_total > 0:
            return (obj.records_processed / obj.records_total) * 100
        return 0
    
    def get_estimated_time_remaining(self, obj):
        """Estimate time remaining based on current progress."""
        if (hasattr(obj, 'started_at') and obj.started_at and 
            hasattr(obj, 'records_total') and obj.records_total > 0 and
            hasattr(obj, 'records_processed') and obj.records_processed > 0):
            
            elapsed = timezone.now() - obj.started_at
            rate = obj.records_processed / elapsed.total_seconds()
            remaining_records = obj.records_total - obj.records_processed
            
            if rate > 0:
                return remaining_records / rate
        
        return None


# =============================================================================
# BULK OPERATION SERIALIZERS
# =============================================================================

class BulkImportSerializer(serializers.Serializer):
    """
    Serializer for bulk import operations.
    Handles multiple file uploads and batch processing.
    """
    
    files = serializers.ListField(
        child=serializers.FileField(),
        min_length=1,
        max_length=10,  # Maximum 10 files per bulk upload
        help_text="List of files to import (max 10)"
    )
    import_type = serializers.ChoiceField(choices=ImportBatch.IMPORT_TYPE_CHOICES)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    
    def validate_files(self, files):
        """Validate all uploaded files."""
        validated_files = []
        
        for file in files:
            # Use FileUploadSerializer for individual file validation
            file_serializer = FileUploadSerializer(data={'file': file})
            if file_serializer.is_valid(raise_exception=True):
                validated_files.append(file)
        
        return validated_files


# =============================================================================
# IMPORT TEMPLATE SERIALIZERS
# =============================================================================

class ImportTemplateSerializer(serializers.Serializer):
    """
    Serializer for generating import templates.
    Provides CSV templates for data imports.
    """
    
    template_type = serializers.ChoiceField(
        choices=[
            ('shopping_centers', 'Shopping Centers'),
            ('tenants', 'Tenants'),
            ('combined', 'Combined Data')
        ]
    )
    include_sample_data = serializers.BooleanField(default=False)
    format = serializers.ChoiceField(
        choices=[('csv', 'CSV'), ('xlsx', 'Excel')],
        default='csv'
    )