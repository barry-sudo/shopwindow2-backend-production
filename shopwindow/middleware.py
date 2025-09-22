# ===== SECURITY MIDDLEWARE =====
"""
Custom security middleware for Shop Window application.
Provides rate limiting, file upload validation, and security monitoring.
"""

import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Rate limiting middleware for API endpoints and file uploads.
    Implements sliding window rate limiting with Redis backing.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Rate limit configurations
        self.rate_limits = {
            # API endpoints
            '/api/v1/shopping-centers/': {'requests': 100, 'window': 3600},  # 100/hour
            '/api/v1/tenants/': {'requests': 100, 'window': 3600},
            '/api/v1/imports/': {'requests': 20, 'window': 3600},  # 20/hour for imports
            
            # File upload endpoints (more restrictive)
            '/api/v1/imports/upload/': {'requests': 5, 'window': 3600},  # 5 uploads/hour
            '/api/v1/imports/csv/': {'requests': 5, 'window': 3600},
            
            # Authentication endpoints
            '/api/auth/': {'requests': 10, 'window': 900},  # 10/15min
        }
    
    def __call__(self, request):
        # Check rate limits before processing request
        if not self._check_rate_limit(request):
            return JsonResponse(
                {
                    'error': 'Rate limit exceeded',
                    'message': 'Too many requests. Please try again later.',
                    'retry_after': self._get_retry_after(request)
                },
                status=429
            )
        
        response = self.get_response(request)
        return response
    
    def _check_rate_limit(self, request) -> bool:
        """Check if request is within rate limits."""
        user_id = self._get_user_identifier(request)
        endpoint = self._get_endpoint_pattern(request.path)
        
        if endpoint not in self.rate_limits:
            return True  # No limit configured
        
        limit_config = self.rate_limits[endpoint]
        cache_key = f"rate_limit:{user_id}:{endpoint}"
        
        # Get current request count
        current_count = cache.get(cache_key, 0)
        
        if current_count >= limit_config['requests']:
            logger.warning(f"Rate limit exceeded for {user_id} on {endpoint}")
            return False
        
        # Increment counter
        cache.set(cache_key, current_count + 1, limit_config['window'])
        return True
    
    def _get_user_identifier(self, request) -> str:
        """Get unique identifier for rate limiting."""
        if request.user.is_authenticated:
            return f"user_{request.user.id}"
        
        # Use IP for anonymous users
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        
        return f"ip_{ip}"
    
    def _get_endpoint_pattern(self, path: str) -> str:
        """Match request path to configured endpoint pattern."""
        for pattern in self.rate_limits.keys():
            if path.startswith(pattern):
                return pattern
        return path
    
    def _get_retry_after(self, request) -> int:
        """Get retry-after time in seconds."""
        endpoint = self._get_endpoint_pattern(request.path)
        return self.rate_limits.get(endpoint, {}).get('window', 3600)


class FileUploadSecurityMiddleware:
    """
    Security middleware for file uploads with comprehensive validation.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Allowed file types and extensions
        self.allowed_extensions = {'.csv', '.xlsx', '.xls', '.pdf'}
        self.allowed_mime_types = {
            'text/csv',
            'application/csv', 
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/pdf'
        }
        
        # File size limits (in bytes)
        self.max_file_size = getattr(settings, 'MAX_IMPORT_FILE_SIZE', 50 * 1024 * 1024)  # 50MB
        
        # Malicious patterns to check in filenames
        self.dangerous_patterns = ['../', '..\\', '<script', '<?php', '<%']
    
    def __call__(self, request):
        # Only check file uploads
        if request.method == 'POST' and self._is_upload_endpoint(request.path):
            validation_result = self._validate_file_upload(request)
            if not validation_result['valid']:
                return JsonResponse(
                    {
                        'error': 'Invalid file upload',
                        'message': validation_result['message'],
                        'details': validation_result.get('details', {})
                    },
                    status=400
                )
        
        response = self.get_response(request)
        return response
    
    def _is_upload_endpoint(self, path: str) -> bool:
        """Check if endpoint handles file uploads."""
        upload_endpoints = ['/api/v1/imports/upload/', '/api/v1/imports/csv/']
        return any(path.startswith(endpoint) for endpoint in upload_endpoints)
    
    def _validate_file_upload(self, request) -> Dict[str, Any]:
        """Comprehensive file upload validation."""
        if not request.FILES:
            return {'valid': True}  # No files to validate
        
        for field_name, uploaded_file in request.FILES.items():
            # Check file size
            if uploaded_file.size > self.max_file_size:
                return {
                    'valid': False,
                    'message': f'File size exceeds limit of {self.max_file_size // (1024*1024)}MB',
                    'details': {'file_size': uploaded_file.size, 'max_size': self.max_file_size}
                }
            
            # Check file extension
            file_extension = self._get_file_extension(uploaded_file.name)
            if file_extension not in self.allowed_extensions:
                return {
                    'valid': False,
                    'message': f'File type not allowed. Allowed types: {", ".join(self.allowed_extensions)}',
                    'details': {'file_extension': file_extension}
                }
            
            # Check MIME type
            if uploaded_file.content_type not in self.allowed_mime_types:
                return {
                    'valid': False,
                    'message': 'Invalid file type detected',
                    'details': {'mime_type': uploaded_file.content_type}
                }
            
            # Check filename for malicious patterns
            if self._contains_malicious_patterns(uploaded_file.name):
                return {
                    'valid': False,
                    'message': 'Filename contains invalid characters',
                    'details': {'filename': uploaded_file.name}
                }
            
            # Validate file content (basic checks)
            content_validation = self._validate_file_content(uploaded_file, file_extension)
            if not content_validation['valid']:
                return content_validation
        
        return {'valid': True}
    
    def _get_file_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        return filename.lower().split('.')[-1] if '.' in filename else ''
    
    def _contains_malicious_patterns(self, filename: str) -> bool:
        """Check filename for malicious patterns."""
        filename_lower = filename.lower()
        return any(pattern in filename_lower for pattern in self.dangerous_patterns)
    
    def _validate_file_content(self, uploaded_file, extension: str) -> Dict[str, Any]:
        """Basic file content validation."""
        try:
            if extension == '.csv':
                # Read first few lines to validate CSV structure
                uploaded_file.seek(0)
                first_line = uploaded_file.readline(1024).decode('utf-8', errors='ignore')
                uploaded_file.seek(0)  # Reset for actual processing
                
                # Basic CSV validation
                if not first_line or ',' not in first_line:
                    return {
                        'valid': False,
                        'message': 'Invalid CSV format - no comma separators found',
                        'details': {'first_line': first_line[:100]}
                    }
            
            elif extension == '.pdf':
                # Basic PDF validation (check PDF magic number)
                uploaded_file.seek(0)
                first_bytes = uploaded_file.read(4)
                uploaded_file.seek(0)
                
                if first_bytes != b'%PDF':
                    return {
                        'valid': False,
                        'message': 'Invalid PDF file format',
                        'details': {'file_header': first_bytes.hex()}
                    }
            
            return {'valid': True}
            
        except Exception as e:
            logger.error(f"File content validation error: {str(e)}")
            return {
                'valid': False,
                'message': 'File content validation failed',
                'details': {'error': str(e)}
            }


class SecurityAuditMiddleware:
    """
    Security audit middleware for logging and monitoring suspicious activities.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Suspicious patterns to monitor
        self.suspicious_patterns = [
            'SELECT * FROM',
            'UNION SELECT', 
            '<script>',
            'javascript:',
            '../',
            'cmd.exe',
            '/etc/passwd',
        ]
    
    def __call__(self, request):
        # Log suspicious requests
        if self._is_suspicious_request(request):
            self._log_suspicious_activity(request)
        
        response = self.get_response(request)
        
        # Log failed authentication attempts
        if hasattr(response, 'status_code') and response.status_code == 401:
            self._log_failed_auth(request)
        
        return response
    
    def _is_suspicious_request(self, request) -> bool:
        """Check if request contains suspicious patterns."""
        # Check query parameters
        for key, value in request.GET.items():
            if any(pattern.lower() in value.lower() for pattern in self.suspicious_patterns):
                return True
        
        # Check POST data
        if request.method == 'POST':
            try:
                body = request.body.decode('utf-8', errors='ignore')
                if any(pattern.lower() in body.lower() for pattern in self.suspicious_patterns):
                    return True
            except:
                pass
        
        return False
    
    def _log_suspicious_activity(self, request):
        """Log suspicious request activity."""
        user_info = f"User: {request.user.id if request.user.is_authenticated else 'Anonymous'}"
        ip_info = f"IP: {self._get_client_ip(request)}"
        path_info = f"Path: {request.path}"
        
        logger.warning(
            f"Suspicious request detected - {user_info}, {ip_info}, {path_info}",
            extra={
                'user_id': request.user.id if request.user.is_authenticated else None,
                'ip_address': self._get_client_ip(request),
                'path': request.path,
                'method': request.method,
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown')
            }
        )
    
    def _log_failed_auth(self, request):
        """Log failed authentication attempts."""
        logger.warning(
            f"Failed authentication attempt from {self._get_client_ip(request)}",
            extra={
                'ip_address': self._get_client_ip(request),
                'path': request.path,
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown')
            }
        )
    
    def _get_client_ip(self, request) -> str:
        """Get real client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        return ip