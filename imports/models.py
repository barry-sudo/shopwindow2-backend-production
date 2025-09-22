# ===== IMPORTS MODELS - COMPLETE IMPLEMENTATION =====
"""
Import tracking models for Shop Window CSV processing system.
Implements comprehensive audit trail and batch processing management.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.postgres.fields import JSONField
from django.utils import timezone


class ImportBatch(models.Model):
    """
    Track import operations for comprehensive audit trail.
    
    Business Rules:
    - Each import operation gets a unique batch ID
    - Files are tracked by hash to prevent duplicate processing
    - Quality scores calculated after successful import
    - Error logging for troubleshooting and data quality
    """
    
    # =============================================================================
    # CHOICES
    # =============================================================================
    
    IMPORT_TYPE_CHOICES = [
        ('CSV', 'CSV Import'),
        ('PDF', 'PDF Extraction'), 
        ('MANUAL', 'Manual Entry'),
        ('API', 'API Integration'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # =============================================================================
    # IDENTITY AND TRACKING
    # =============================================================================
    
    id = models.AutoField(primary_key=True)
    batch_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        help_text="User who initiated the import"
    )
    
    # =============================================================================
    # IMPORT CONFIGURATION
    # =============================================================================
    
    import_type = models.CharField(
        max_length=10, 
        choices=IMPORT_TYPE_CHOICES,
        help_text="Type of import operation"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        db_index=True,
        help_text="Current processing status"
    )
    
    # =============================================================================
    # FILE INFORMATION
    # =============================================================================
    
    file_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Original uploaded file name"
    )
    file_size = models.BigIntegerField(
        blank=True, 
        null=True,
        help_text="File size in bytes"
    )
    file_hash = models.CharField(
        max_length=64, 
        blank=True, 
        null=True,
        db_index=True,
        help_text="SHA256 hash for duplicate detection"
    )
    
    # =============================================================================
    # PROCESSING METRICS
    # =============================================================================
    
    records_total = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total records in import file"
    )
    records_processed = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of records processed"
    )
    records_created = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="New records created"
    )
    records_updated = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Existing records updated"
    )
    records_skipped = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Records skipped due to errors"
    )
    
    # =============================================================================
    # QUALITY AND VALIDATION
    # =============================================================================
    
    quality_score = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall data quality score (0-100)"
    )
    has_errors = models.BooleanField(
        default=False,
        help_text="Whether import encountered any errors"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Primary error message if import failed"
    )
    validation_results = JSONField(
        default=dict,
        blank=True,
        help_text="Detailed validation results and warnings"
    )
    
    # =============================================================================
    # PROCESSING TIMESTAMPS
    # =============================================================================
    
    started_at = models.DateTimeField(
        blank=True, 
        null=True,
        help_text="When processing actually began"
    )
    completed_at = models.DateTimeField(
        blank=True, 
        null=True,
        help_text="When processing completed (success or failure)"
    )
    
    # =============================================================================
    # NOTES AND METADATA
    # =============================================================================
    
    notes = models.TextField(
        blank=True,
        help_text="User notes about this import"
    )
    metadata = JSONField(
        default=dict,
        blank=True,
        help_text="Additional import metadata and processing details"
    )
    
    class Meta:
        db_table = 'import_batches'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['import_type', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['has_errors']),
        ]
        
    def __str__(self):
        return f"Import Batch {self.batch_id} - {self.get_import_type_display()}"
    
    # =============================================================================
    # PROPERTIES AND METHODS
    # =============================================================================
    
    @property
    def is_processing(self):
        """Check if import is currently being processed."""
        return self.status == 'processing'
    
    @property
    def is_completed(self):
        """Check if import completed successfully."""
        return self.status == 'completed'
    
    @property
    def is_failed(self):
        """Check if import failed."""
        return self.status == 'failed'
    
    @property
    def processing_duration(self):
        """Get processing duration if available."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def success_rate(self):
        """Calculate success rate percentage."""
        if self.records_total == 0:
            return 0
        processed = self.records_created + self.records_updated
        return (processed / self.records_total) * 100
    
    def mark_as_processing(self):
        """Mark batch as currently processing."""
        self.status = 'processing'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_as_completed(self, quality_score=None):
        """Mark batch as successfully completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if quality_score is not None:
            self.quality_score = quality_score
        self.save(update_fields=['status', 'completed_at', 'quality_score', 'updated_at'])
    
    def mark_as_failed(self, error_message):
        """Mark batch as failed with error message."""
        self.status = 'failed'
        self.has_errors = True
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'has_errors', 'error_message', 'completed_at', 'updated_at'])


# =============================================================================
# IMPORT ERROR TRACKING
# =============================================================================

class ImportError(models.Model):
    """
    Track individual import errors for detailed troubleshooting.
    Allows granular error analysis and data quality improvement.
    """
    
    ERROR_TYPE_CHOICES = [
        ('VALIDATION', 'Validation Error'),
        ('PROCESSING', 'Processing Error'),
        ('DUPLICATE', 'Duplicate Record'),
        ('MISSING_DATA', 'Missing Required Data'),
        ('FORMAT', 'Format Error'),
        ('GEOCODING', 'Geocoding Error'),
        ('BUSINESS_LOGIC', 'Business Logic Error'),
    ]
    
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name='errors'
    )
    error_type = models.CharField(max_length=20, choices=ERROR_TYPE_CHOICES)
    row_number = models.IntegerField(validators=[MinValueValidator(1)])
    field_name = models.CharField(max_length=100, blank=True)
    error_message = models.TextField()
    raw_data = JSONField(default=dict, help_text="Original row data that caused error")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'import_errors'
        ordering = ['row_number']
        indexes = [
            models.Index(fields=['import_batch', 'error_type']),
            models.Index(fields=['error_type']),
        ]
    
    def __str__(self):
        return f"Row {self.row_number}: {self.get_error_type_display()}"