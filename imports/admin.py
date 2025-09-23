# ===== IMPORTS APP ADMIN CONFIGURATION =====
"""
Django Admin interface for import management
File: imports/admin.py

This module provides comprehensive admin tools for managing CSV imports,
monitoring import batch progress, and troubleshooting import issues.

Admin Features:
- Import batch monitoring and management
- CSV processing status tracking
- Quality score visualization
- Bulk import operations
- Error investigation tools
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from django.http import HttpResponse
import csv
from datetime import datetime, timedelta

from .models import ImportBatch

# =============================================================================
# IMPORT BATCH ADMIN
# =============================================================================

@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    """
    Admin interface for ImportBatch model
    Provides comprehensive tools for monitoring and managing CSV imports
    """
    
    # =============================================================================
    # LIST VIEW CONFIGURATION
    # =============================================================================
    
    list_display = [
        'batch_id_display',
        'file_name_display', 
        'status_badge',
        'records_processed',
        'quality_score_display',
        'created_at_display',
        'processing_time_display',
        'actions_column'
    ]
    
    list_filter = [
        'status',
        'import_type',
        ('created_at', admin.DateFieldListFilter),
        'has_errors'
    ]
    
    search_fields = [
        'file_name',
        'batch_id',
        'notes',
        'error_message'
    ]
    
    ordering = ['-created_at']
    
    list_per_page = 25
    
    # =============================================================================
    # DETAIL VIEW CONFIGURATION  
    # =============================================================================
    
    readonly_fields = [
        'batch_id',
        'created_at',
        'updated_at',
        'processing_time_display',
        'file_size_display',
        'progress_bar',
        'detailed_status'
    ]
    
    fieldsets = [
        ('Import Information', {
            'fields': [
                'batch_id',
                'file_name',
                'file_size_display',
                'import_type'
            ]
        }),
        ('Processing Status', {
            'fields': [
                'status',
                'detailed_status',
                'progress_bar',
                'records_processed',
                'records_total',
                'quality_score'
            ]
        }),
        ('Timing Information', {
            'fields': [
                'created_at',
                'updated_at', 
                'processing_time_display'
            ]
        }),
        ('Results and Errors', {
            'fields': [
                'has_errors',
                'error_message',
                'validation_results',
                'notes'
            ],
            'classes': ['collapse']
        })
    ]
    
    # =============================================================================
    # CUSTOM DISPLAY METHODS
    # =============================================================================
    
    def batch_id_display(self, obj):
        """Display batch ID with link to detail view"""
        return format_html(
            '<strong>#{}</strong>',
            obj.batch_id
        )
    batch_id_display.short_description = 'Batch ID'
    batch_id_display.admin_order_field = 'batch_id'
    
    def file_name_display(self, obj):
        """Display file name with truncation for long names"""
        if len(obj.file_name) > 30:
            return format_html(
                '<span title="{}">{}</span>',
                obj.file_name,
                obj.file_name[:27] + '...'
            )
        return obj.file_name
    file_name_display.short_description = 'File Name'
    file_name_display.admin_order_field = 'file_name'
    
    def status_badge(self, obj):
        """Display status as colored badge"""
        status_colors = {
            'pending': '#ffc107',     # Yellow
            'processing': '#007bff',  # Blue  
            'completed': '#28a745',   # Green
            'failed': '#dc3545',      # Red
            'cancelled': '#6c757d'    # Gray
        }
        
        color = status_colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def quality_score_display(self, obj):
        """Display quality score with color coding"""
        if obj.quality_score is None:
            return mark_safe('<span style="color: #999;">N/A</span>')
        
        # Color coding based on score
        if obj.quality_score >= 90:
            color = '#28a745'  # Green
        elif obj.quality_score >= 70:
            color = '#ffc107'  # Yellow
        else:
            color = '#dc3545'  # Red
            
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}/100</span>',
            color,
            obj.quality_score
        )
    quality_score_display.short_description = 'Quality'
    quality_score_display.admin_order_field = 'quality_score'
    
    def created_at_display(self, obj):
        """Display creation time in readable format"""
        return obj.created_at.strftime('%m/%d/%y %I:%M %p')
    created_at_display.short_description = 'Created'
    created_at_display.admin_order_field = 'created_at'
    
    def processing_time_display(self, obj):
        """Calculate and display processing time"""
        if obj.status == 'completed' and obj.updated_at:
            delta = obj.updated_at - obj.created_at
            total_seconds = int(delta.total_seconds())
            
            if total_seconds < 60:
                return f'{total_seconds}s'
            elif total_seconds < 3600:
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                return f'{minutes}m {seconds}s'
            else:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f'{hours}h {minutes}m'
        elif obj.status == 'processing':
            delta = datetime.now() - obj.created_at.replace(tzinfo=None)
            total_seconds = int(delta.total_seconds())
            return f'{total_seconds}s (running)'
        return 'N/A'
    processing_time_display.short_description = 'Processing Time'
    
    def actions_column(self, obj):
        """Display action buttons for each import batch"""
        actions = []
        
        if obj.status == 'failed':
            retry_url = reverse('admin:imports_importbatch_retry', args=[obj.pk])
            actions.append(f'<a href="{retry_url}" style="color: #007bff;">Retry</a>')
        
        if obj.status == 'completed':
            view_url = reverse('admin:imports_importbatch_view_results', args=[obj.pk])
            actions.append(f'<a href="{view_url}" style="color: #28a745;">View Results</a>')
        
        if obj.has_errors:
            errors_url = reverse('admin:imports_importbatch_view_errors', args=[obj.pk])
            actions.append(f'<a href="{errors_url}" style="color: #dc3545;">View Errors</a>')
        
        return mark_safe(' | '.join(actions)) if actions else 'N/A'
    actions_column.short_description = 'Actions'
    
    def file_size_display(self, obj):
        """Display file size in human readable format"""
        if hasattr(obj, 'file_size') and obj.file_size:
            size = obj.file_size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f'{size:.1f} {unit}'
                size /= 1024.0
            return f'{size:.1f} TB'
        return 'Unknown'
    file_size_display.short_description = 'File Size'
    
    def progress_bar(self, obj):
        """Display progress bar for processing imports"""
        if obj.records_total and obj.records_total > 0:
            percentage = (obj.records_processed / obj.records_total) * 100
            return format_html(
                '''
                <div style="width: 200px; background: #f0f0f0; border-radius: 5px; overflow: hidden;">
                    <div style="width: {}%; background: #007bff; height: 20px; line-height: 20px; color: white; text-align: center; font-size: 11px;">
                        {}/{} ({}%)
                    </div>
                </div>
                ''',
                percentage,
                obj.records_processed,
                obj.records_total,
                int(percentage)
            )
        return 'N/A'
    progress_bar.short_description = 'Progress'
    
    def detailed_status(self, obj):
        """Provide detailed status information"""
        status_info = [f'Status: {obj.status.title()}']
        
        if obj.records_processed:
            status_info.append(f'Records Processed: {obj.records_processed}')
        
        if obj.records_total:
            status_info.append(f'Total Records: {obj.records_total}')
        
        if obj.has_errors:
            status_info.append('⚠️ Contains Errors')
        
        if obj.quality_score:
            status_info.append(f'Quality Score: {obj.quality_score}/100')
        
        return mark_safe('<br>'.join(status_info))
    detailed_status.short_description = 'Detailed Status'
    
    # =============================================================================
    # CUSTOM ADMIN ACTIONS
    # =============================================================================
    
    actions = [
        'mark_as_cancelled',
        'retry_failed_imports', 
        'export_import_log',
        'clear_old_imports'
    ]
    
    def mark_as_cancelled(self, request, queryset):
        """Mark selected imports as cancelled"""
        updated = queryset.filter(
            status__in=['pending', 'processing']
        ).update(status='cancelled')
        
        self.message_user(
            request,
            f'{updated} import batch(es) marked as cancelled.'
        )
    mark_as_cancelled.short_description = 'Cancel selected imports'
    
    def retry_failed_imports(self, request, queryset):
        """Retry selected failed imports"""
        failed_imports = queryset.filter(status='failed')
        count = 0
        
        for import_batch in failed_imports:
            import_batch.status = 'pending'
            import_batch.error_message = ''
            import_batch.save()
            count += 1
            # Here you would trigger the import processing
        
        self.message_user(
            request,
            f'{count} failed import(s) queued for retry.'
        )
    retry_failed_imports.short_description = 'Retry failed imports'
    
    def export_import_log(self, request, queryset):
        """Export import log as CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="import_log_{datetime.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Batch ID', 'File Name', 'Status', 'Records Processed', 
            'Quality Score', 'Created At', 'Has Errors'
        ])
        
        for import_batch in queryset:
            writer.writerow([
                import_batch.batch_id,
                import_batch.file_name,
                import_batch.status,
                import_batch.records_processed or 0,
                import_batch.quality_score or 'N/A',
                import_batch.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'Yes' if import_batch.has_errors else 'No'
            ])
        
        return response
    export_import_log.short_description = 'Export import log as CSV'
    
    def clear_old_imports(self, request, queryset):
        """Clear imports older than 30 days"""
        cutoff_date = datetime.now() - timedelta(days=30)
        old_imports = queryset.filter(created_at__lt=cutoff_date)
        count = old_imports.count()
        old_imports.delete()
        
        self.message_user(
            request,
            f'Cleared {count} import batch(es) older than 30 days.'
        )
    clear_old_imports.short_description = 'Clear old imports (30+ days)'
    
    # =============================================================================
    # ADMIN INTERFACE CUSTOMIZATION
    # =============================================================================
    
    def get_queryset(self, request):
        """Optimize queryset with annotations"""
        return super().get_queryset(request).select_related()
    
    def changelist_view(self, request, extra_context=None):
        """Add summary statistics to changelist view"""
        extra_context = extra_context or {}
        
        # Calculate summary statistics
        queryset = self.get_queryset(request)
        
        extra_context['summary_stats'] = {
            'total_imports': queryset.count(),
            'completed_imports': queryset.filter(status='completed').count(),
            'failed_imports': queryset.filter(status='failed').count(),
            'processing_imports': queryset.filter(status='processing').count(),
            'avg_quality_score': queryset.exclude(
                quality_score__isnull=True
            ).aggregate(avg_score=models.Avg('quality_score'))['avg_score']
        }
        
        return super().changelist_view(request, extra_context=extra_context)


# =============================================================================
# ADMIN SITE CUSTOMIZATION
# =============================================================================

# Customize admin site header
admin.site.site_header = 'Shop Window Admin - Import Management'
admin.site.site_title = 'Shop Window Import Admin'
admin.site.index_title = 'Import Management Dashboard'
