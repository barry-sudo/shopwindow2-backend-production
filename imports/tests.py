# ===== IMPORTS APP TEST SUITE =====
"""
Comprehensive test suite for imports app functionality
File: imports/tests.py

Test Coverage:
- ImportBatch model operations and business logic
- CSV processing services and data transformation
- API endpoints for upload, validation, and management
- Integration with properties models
- Error handling and edge cases
- Quality scoring and validation workflows
- Admin interface functionality
"""

import json
import io
import tempfile
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, Mock

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from .models import ImportBatch
from .services import CSVImportService, validate_csv_structure, create_sample_csv
from properties.models import ShoppingCenter, Tenant

User = get_user_model()


# =============================================================================
# MODEL TESTS
# =============================================================================

class ImportBatchModelTest(TestCase):
    """Test ImportBatch model functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_import_batch(self):
        """Test creating an import batch"""
        batch = ImportBatch.objects.create(
            file_name='test.csv',
            import_type='csv',
            status='pending',
            notes='Test import batch'
        )
        
        self.assertEqual(batch.file_name, 'test.csv')
        self.assertEqual(batch.import_type, 'csv')
        self.assertEqual(batch.status, 'pending')
        self.assertFalse(batch.has_errors)
        self.assertIsNotNone(batch.batch_id)
        self.assertIsNotNone(batch.created_at)
    
    def test_batch_id_uniqueness(self):
        """Test that batch IDs are unique"""
        batch1 = ImportBatch.objects.create(file_name='test1.csv')
        batch2 = ImportBatch.objects.create(file_name='test2.csv')
        
        self.assertNotEqual(batch1.batch_id, batch2.batch_id)
    
    def test_batch_status_choices(self):
        """Test valid status choices"""
        valid_statuses = ['pending', 'processing', 'completed', 'failed', 'cancelled']
        
        for status in valid_statuses:
            batch = ImportBatch.objects.create(
                file_name=f'test_{status}.csv',
                status=status
            )
            self.assertEqual(batch.status, status)
    
    def test_quality_score_validation(self):
        """Test quality score validation"""
        # Valid quality scores
        for score in [0, 50, 100]:
            batch = ImportBatch.objects.create(
                file_name=f'test_{score}.csv',
                quality_score=score
            )
            self.assertEqual(batch.quality_score, score)
    
    def test_batch_string_representation(self):
        """Test string representation of import batch"""
        batch = ImportBatch.objects.create(
            file_name='test.csv',
            status='completed'
        )
        
        expected = f'Import Batch {batch.batch_id} - test.csv (completed)'
        self.assertEqual(str(batch), expected)


# =============================================================================
# CSV PROCESSING SERVICE TESTS
# =============================================================================

class CSVImportServiceTest(TransactionTestCase):
    """Test CSV import service functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.import_batch = ImportBatch.objects.create(
            file_name='test.csv',
            import_type='csv',
            status='pending'
        )
        self.service = CSVImportService(self.import_batch)
        
        # Sample CSV content
        self.valid_csv_content = """shopping_center_name,center_type,total_gla,address_city,address_state,tenant_name,suite_sqft
Westfield Valley Fair,mall,2100000,Santa Clara,CA,Apple Store,8500
Downtown Plaza,strip_center,45000,Sacramento,CA,Starbucks Coffee,1200"""
    
    def test_parse_csv_content(self):
        """Test CSV content parsing"""
        csv_data = self.service._parse_csv_content(self.valid_csv_content)
        
        self.assertEqual(len(csv_data), 2)
        self.assertEqual(csv_data[0]['shopping_center_name'], 'Westfield Valley Fair')
        self.assertEqual(csv_data[1]['shopping_center_name'], 'Downtown Plaza')
    
    def test_header_mapping(self):
        """Test CSV header mapping to model fields"""
        csv_headers = ['property_name', 'type', 'gla', 'city', 'state']
        mapping = self.service._create_headers_mapping(csv_headers)
        
        expected_mapping = {
            'property_name': 'shopping_center_name',
            'type': 'center_type',
            'gla': 'total_gla',
            'city': 'address_city',
            'state': 'address_state'
        }
        
        for csv_header, model_field in expected_mapping.items():
            self.assertEqual(mapping.get(csv_header), model_field)
    
    def test_extract_shopping_center_data(self):
        """Test extracting shopping center data from CSV row"""
        row_data = {
            'shopping_center_name': 'Test Mall',
            'center_type': 'mall',
            'total_gla': '150,000',
            'address_city': 'San Jose',
            'address_state': 'CA',
            'year_built': '2020'
        }
        
        extracted_data = self.service._extract_shopping_center_data(row_data)
        
        self.assertEqual(extracted_data['shopping_center_name'], 'Test Mall')
        self.assertEqual(extracted_data['center_type'], 'mall')
        self.assertEqual(extracted_data['total_gla'], 150000)
        self.assertEqual(extracted_data['year_built'], 2020)
    
    def test_extract_tenant_data(self):
        """Test extracting tenant data from CSV row"""
        row_data = {
            'tenant_name': 'Apple Store',
            'suite_number': 'A101',
            'suite_sqft': '8,500',
            'rent_psf': '85.50',
            'tenant_category': 'electronics'
        }
        
        extracted_data = self.service._extract_tenant_data(row_data)
        
        self.assertEqual(extracted_data['tenant_name'], 'Apple Store')
        self.assertEqual(extracted_data['suite_sqft'], 8500)
        self.assertEqual(extracted_data['rent_psf'], Decimal('85.50'))
    
    @patch('imports.services.geocode_address')
    def test_process_csv_file_success(self, mock_geocode):
        """Test successful CSV file processing"""
        mock_geocode.return_value = None  # Skip geocoding for test
        
        result = self.service.process_csv_file(self.valid_csv_content)
        
        # Check import batch was updated
        self.import_batch.refresh_from_db()
        self.assertEqual(self.import_batch.status, 'completed')
        self.assertEqual(self.import_batch.records_total, 2)
        self.assertEqual(self.import_batch.records_processed, 2)
        
        # Check shopping centers were created
        self.assertEqual(ShoppingCenter.objects.count(), 2)
        
        # Check processing results
        self.assertEqual(result['records_processed'], 2)
        self.assertEqual(result['records_created'], 2)
        self.assertGreater(result['quality_score'], 0)
    
    def test_process_invalid_csv(self):
        """Test processing invalid CSV content"""
        invalid_csv = "invalid,csv,content\nwithout,proper,headers"
        
        with self.assertRaises(ValueError):
            self.service.process_csv_file(invalid_csv)
    
    def test_duplicate_shopping_center_update(self):
        """Test updating existing shopping center with new data"""
        # Create existing shopping center
        existing_center = ShoppingCenter.objects.create(
            shopping_center_name='Test Mall',
            center_type='mall'
        )
        
        # CSV with additional data for same shopping center
        csv_content = """shopping_center_name,address_city,address_state,total_gla
Test Mall,San Jose,CA,150000"""
        
        self.service.process_csv_file(csv_content)
        
        # Check that existing center was updated, not duplicated
        self.assertEqual(ShoppingCenter.objects.count(), 1)
        
        existing_center.refresh_from_db()
        self.assertEqual(existing_center.address_city, 'San Jose')
        self.assertEqual(existing_center.total_gla, 150000)
    
    def test_quality_score_calculation(self):
        """Test quality score calculation"""
        # Add some errors and warnings to test quality calculation
        self.service.errors = ['Error 1', 'Error 2']
        self.service.warnings = ['Warning 1']
        self.service.processed_count = 10
        
        quality_score = self.service._calculate_import_quality()
        
        # Quality should be reduced due to errors and warnings
        self.assertLess(quality_score, 100)
        self.assertGreaterEqual(quality_score, 0)


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class ImportUtilityTest(TestCase):
    """Test utility functions for CSV processing"""
    
    def test_validate_csv_structure_valid(self):
        """Test validating valid CSV structure"""
        valid_csv = """shopping_center_name,center_type,address_city
Test Mall,mall,San Jose
Plaza Center,strip_center,Sacramento"""
        
        result = validate_csv_structure(valid_csv)
        
        self.assertTrue(result['valid'])
        self.assertEqual(result['row_count'], 2)
        self.assertIn('shopping_center_name', result['headers'])
    
    def test_validate_csv_structure_invalid(self):
        """Test validating invalid CSV structure"""
        invalid_csv = """invalid,headers,only
data,without,required,fields"""
        
        result = validate_csv_structure(invalid_csv)
        
        self.assertFalse(result['valid'])
        self.assertIn('missing_required', result)
    
    def test_create_sample_csv(self):
        """Test sample CSV generation"""
        sample_csv = create_sample_csv()
        
        self.assertIsInstance(sample_csv, str)
        self.assertIn('shopping_center_name', sample_csv)
        self.assertIn('Westfield Valley Fair', sample_csv)
        
        # Validate that sample CSV is valid
        validation_result = validate_csv_structure(sample_csv)
        self.assertTrue(validation_result['valid'])


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================

class ImportAPITestCase(APITestCase):
    """Base test case for import API endpoints"""
    
    def setUp(self):
        """Set up test data and authentication"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create test import batch
        self.import_batch = ImportBatch.objects.create(
            file_name='test.csv',
            import_type='csv',
            status='completed',
            records_processed=10,
            quality_score=85
        )


class ImportBatchViewSetTest(ImportAPITestCase):
    """Test ImportBatchViewSet API endpoints"""
    
    def test_list_import_batches(self):
        """Test listing import batches"""
        url = reverse('importbatch-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['file_name'], 'test.csv')
    
    def test_retrieve_import_batch(self):
        """Test retrieving specific import batch"""
        url = reverse('importbatch-detail', kwargs={'pk': self.import_batch.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['file_name'], 'test.csv')
        self.assertEqual(response.data['status'], 'completed')
    
    def test_filter_by_status(self):
        """Test filtering import batches by status"""
        # Create additional batch with different status
        ImportBatch.objects.create(
            file_name='pending.csv',
            status='pending'
        )
        
        url = reverse('importbatch-list')
        response = self.client.get(url, {'status': 'completed'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['status'], 'completed')
    
    def test_import_batch_status_action(self):
        """Test import batch status custom action"""
        url = reverse('importbatch-status', kwargs={'pk': self.import_batch.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['batch_id'], self.import_batch.batch_id)
        self.assertEqual(response.data['status'], 'completed')
        self.assertEqual(response.data['records_processed'], 10)
    
    def test_import_batch_quality_action(self):
        """Test import batch quality report action"""
        url = reverse('importbatch-quality', kwargs={'pk': self.import_batch.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['quality_score'], 85)
    
    def test_retry_failed_import(self):
        """Test retrying failed import batch"""
        # Create failed import batch
        failed_batch = ImportBatch.objects.create(
            file_name='failed.csv',
            status='failed',
            error_message='Test error'
        )
        
        url = reverse('importbatch-retry', kwargs={'pk': failed_batch.pk})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        failed_batch.refresh_from_db()
        self.assertEqual(failed_batch.status, 'pending')
        self.assertEqual(failed_batch.error_message, '')
    
    def test_retry_non_failed_import_error(self):
        """Test trying to retry non-failed import returns error"""
        url = reverse('importbatch-retry', kwargs={'pk': self.import_batch.pk})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


class CSVUploadViewTest(ImportAPITestCase):
    """Test CSV upload API endpoint"""
    
    def test_csv_upload_success(self):
        """Test successful CSV file upload"""
        csv_content = b"""shopping_center_name,center_type,address_city,address_state
Test Mall,mall,San Jose,CA
Plaza Center,strip_center,Sacramento,CA"""
        
        csv_file = SimpleUploadedFile(
            "test.csv",
            csv_content,
            content_type="text/csv"
        )
        
        url = reverse('csv-upload')
        response = self.client.post(url, {
            'file': csv_file,
            'import_type': 'csv',
            'notes': 'Test upload'
        }, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('import_batch_id', response.data)
        self.assertIn('processing_result', response.data)
        
        # Check that import batch was created
        batch_id = response.data['import_batch_id']
        batch = ImportBatch.objects.get(batch_id=batch_id)
        self.assertEqual(batch.file_name, 'test.csv')
        self.assertEqual(batch.notes, 'Test upload')
    
    def test_csv_upload_no_file(self):
        """Test CSV upload without file returns error"""
        url = reverse('csv-upload')
        response = self.client.post(url, {
            'import_type': 'csv'
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_csv_upload_invalid_file_type(self):
        """Test uploading non-CSV file returns error"""
        txt_file = SimpleUploadedFile(
            "test.txt",
            b"This is not a CSV file",
            content_type="text/plain"
        )
        
        url = reverse('csv-upload')
        response = self.client.post(url, {
            'file': txt_file
        }, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only CSV files are allowed', response.data['error'])
    
    @patch('imports.views.settings.IMPORT_MAX_FILE_SIZE', 1024)  # 1KB limit
    def test_csv_upload_file_too_large(self):
        """Test uploading file that exceeds size limit"""
        large_content = b"a" * 2048  # 2KB content
        large_file = SimpleUploadedFile(
            "large.csv",
            large_content,
            content_type="text/csv"
        )
        
        url = reverse('csv-upload')
        response = self.client.post(url, {
            'file': large_file
        }, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('File too large', response.data['error'])


class CSVValidationViewTest(ImportAPITestCase):
    """Test CSV validation API endpoint"""
    
    def test_csv_validation_success(self):
        """Test successful CSV validation"""
        csv_content = b"""shopping_center_name,center_type,address_city
Test Mall,mall,San Jose
Plaza Center,strip_center,Sacramento"""
        
        csv_file = SimpleUploadedFile(
            "test.csv",
            csv_content,
            content_type="text/csv"
        )
        
        url = reverse('csv-validate')
        response = self.client.post(url, {
            'file': csv_file
        }, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['file_name'], 'test.csv')
        self.assertTrue(response.data['validation_result']['valid'])
        self.assertEqual(response.data['validation_result']['row_count'], 2)
    
    def test_csv_validation_invalid_structure(self):
        """Test validation of invalid CSV structure"""
        csv_content = b"""invalid,headers
data,values"""
        
        csv_file = SimpleUploadedFile(
            "invalid.csv",
            csv_content,
            content_type="text/csv"
        )
        
        url = reverse('csv-validate')
        response = self.client.post(url, {
            'file': csv_file
        }, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['validation_result']['valid'])


class CSVTemplateViewTest(ImportAPITestCase):
    """Test CSV template download endpoint"""
    
    def test_csv_template_download(self):
        """Test downloading CSV template"""
        url = reverse('csv-template')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('shop_window_import_template.csv', response['Content-Disposition'])
        
        # Check that content is valid CSV
        content = response.content.decode('utf-8')
        self.assertIn('shopping_center_name', content)
        self.assertIn('Westfield Valley Fair', content)


class ImportStatsViewTest(ImportAPITestCase):
    """Test import statistics API endpoint"""
    
    def setUp(self):
        super().setUp()
        
        # Create additional test data for statistics
        ImportBatch.objects.create(
            file_name='batch2.csv',
            status='failed',
            records_processed=0,
            created_at=timezone.now() - timedelta(days=5)
        )
        
        ImportBatch.objects.create(
            file_name='batch3.csv',
            status='processing',
            records_processed=5,
            records_total=10,
            created_at=timezone.now() - timedelta(days=2)
        )
    
    def test_import_stats_default_range(self):
        """Test import statistics with default date range"""
        url = reverse('import-stats')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check summary data
        summary = response.data['summary']
        self.assertEqual(summary['total_imports'], 3)
        self.assertEqual(summary['completed_imports'], 1)
        self.assertEqual(summary['failed_imports'], 1)
        self.assertEqual(summary['processing_imports'], 1)
        self.assertGreater(summary['success_rate'], 0)
        
        # Check status distribution
        status_dist = response.data['status_distribution']
        self.assertEqual(status_dist['completed'], 1)
        self.assertEqual(status_dist['failed'], 1)
        self.assertEqual(status_dist['processing'], 1)
        
        # Check recent activity
        self.assertIn('recent_activity', response.data)
        self.assertIsInstance(response.data['recent_activity'], list)
    
    def test_import_stats_custom_date_range(self):
        """Test import statistics with custom date range"""
        start_date = (timezone.now() - timedelta(days=3)).isoformat()
        end_date = timezone.now().isoformat()
        
        url = reverse('import-stats')
        response = self.client.get(url, {
            'date_from': start_date,
            'date_to': end_date
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only include batches within date range
        summary = response.data['summary']
        self.assertLessEqual(summary['total_imports'], 3)


class AdminViewsTest(ImportAPITestCase):
    """Test admin-only API endpoints"""
    
    def setUp(self):
        super().setUp()
        # Switch to admin client
        self.client.force_authenticate(user=self.admin_user)
    
    def test_load_sample_data_success(self):
        """Test loading sample data (admin only)"""
        url = reverse('load-sample-data')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('import_batch_id', response.data)
        self.assertIn('processing_result', response.data)
        
        # Check that sample data was processed
        batch_id = response.data['import_batch_id']
        batch = ImportBatch.objects.get(batch_id=batch_id)
        self.assertEqual(batch.import_type, 'sample')
    
    def test_load_sample_data_requires_admin(self):
        """Test that loading sample data requires admin permissions"""
        # Switch back to regular user
        self.client.force_authenticate(user=self.user)
        
        url = reverse('load-sample-data')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_clear_imports_success(self):
        """Test clearing old imports (admin only)"""
        # Create old import batch
        old_batch = ImportBatch.objects.create(
            file_name='old.csv',
            status='completed',
            created_at=timezone.now() - timedelta(days=35)
        )
        
        url = reverse('clear-imports')
        response = self.client.delete(url, {'days_old': 30})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 1)
        
        # Check that old batch was deleted
        self.assertFalse(ImportBatch.objects.filter(pk=old_batch.pk).exists())
    
    def test_clear_imports_with_status_filter(self):
        """Test clearing imports with status filter"""
        # Create old batches with different statuses
        ImportBatch.objects.create(
            file_name='old_completed.csv',
            status='completed',
            created_at=timezone.now() - timedelta(days=35)
        )
        
        ImportBatch.objects.create(
            file_name='old_failed.csv',
            status='failed',
            created_at=timezone.now() - timedelta(days=35)
        )
        
        url = reverse('clear-imports')
        response = self.client.delete(url, {
            'days_old': 30,
            'status': 'failed'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 1)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class ImportIntegrationTest(TransactionTestCase):
    """Integration tests for complete import workflows"""
    
    def setUp(self):
        """Set up integration test data"""
        self.user = User.objects.create_user(
            username='integrationtest',
            email='integration@test.com',
            password='testpass123'
        )
    
    @patch('imports.services.geocode_address')
    def test_complete_csv_import_workflow(self, mock_geocode):
        """Test complete CSV import workflow from upload to completion"""
        mock_geocode.return_value = None  # Skip geocoding
        
        # Step 1: Create import batch
        batch = ImportBatch.objects.create(
            file_name='integration_test.csv',
            import_type='csv',
            status='pending'
        )
        
        # Step 2: Process CSV data
        csv_content = """shopping_center_name,center_type,total_gla,address_city,address_state,tenant_name,suite_sqft,rent_psf
Westfield Valley Fair,mall,2100000,Santa Clara,CA,Apple Store,8500,85.00
Westfield Valley Fair,mall,2100000,Santa Clara,CA,Microsoft Store,7500,80.00
Downtown Plaza,strip_center,45000,Sacramento,CA,Starbucks Coffee,1200,35.00"""
        
        service = CSVImportService(batch)
        result = service.process_csv_file(csv_content)
        
        # Step 3: Verify results
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'completed')
        self.assertEqual(batch.records_processed, 3)
        
        # Check shopping centers were created
        self.assertEqual(ShoppingCenter.objects.count(), 2)
        
        valley_fair = ShoppingCenter.objects.get(shopping_center_name='Westfield Valley Fair')
        self.assertEqual(valley_fair.total_gla, 2100000)
        self.assertEqual(valley_fair.address_city, 'Santa Clara')
        
        downtown_plaza = ShoppingCenter.objects.get(shopping_center_name='Downtown Plaza')
        self.assertEqual(downtown_plaza.total_gla, 45000)
        
        # Check tenants were created and associated correctly
        self.assertEqual(Tenant.objects.count(), 3)
        
        valley_fair_tenants = Tenant.objects.filter(shopping_center=valley_fair)
        self.assertEqual(valley_fair_tenants.count(), 2)
        
        apple_store = valley_fair_tenants.get(tenant_name='Apple Store')
        self.assertEqual(apple_store.suite_sqft, 8500)
        self.assertEqual(apple_store.rent_psf, Decimal('85.00'))
        
        # Check processing results
        self.assertGreater(result['quality_score'], 0)
        self.assertEqual(result['records_created'], 3)  # 2 properties + 3 tenants created
    
    def test_error_handling_in_integration(self):
        """Test error handling in complete workflow"""
        batch = ImportBatch.objects.create(
            file_name='error_test.csv',
            status='pending'
        )
        
        # CSV with some invalid data
        csv_content = """shopping_center_name,total_gla,address_city
Valid Center,150000,San Jose
,50000,Sacramento
Another Valid,invalid_gla,Oakland"""
        
        service = CSVImportService(batch)
        result = service.process_csv_file(csv_content)
        
        # Should complete but with errors/warnings
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'completed_with_errors')
        self.assertTrue(batch.has_errors)
        
        # Should have created valid records
        self.assertGreater(ShoppingCenter.objects.count(), 0)
        
        # Should have error information
        self.assertGreater(len(result['errors']), 0)


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class ImportPerformanceTest(TransactionTestCase):
    """Performance tests for import functionality"""
    
    @patch('imports.services.geocode_address')
    def test_large_csv_processing_performance(self, mock_geocode):
        """Test processing large CSV files"""
        mock_geocode.return_value = None  # Skip geocoding
        
        # Generate large CSV content (100 records)
        csv_lines = ['shopping_center_name,center_type,address_city,address_state']
        for i in range(100):
            csv_lines.append(f'Center_{i},mall,City_{i%10},CA')
        
        large_csv_content = '\n'.join(csv_lines)
        
        # Create import batch and process
        batch = ImportBatch.objects.create(
            file_name='large_test.csv',
            status='pending'
        )
        
        service = CSVImportService(batch)
        
        start_time = timezone.now()
        result = service.process_csv_file(large_csv_content)
        end_time = timezone.now()
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Performance assertions
        self.assertLess(processing_time, 30)  # Should complete within 30 seconds
        self.assertEqual(result['records_processed'], 100)
        self.assertEqual(ShoppingCenter.objects.count(), 100)
        
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'completed')
    
    def test_concurrent_imports_handling(self):
        """Test handling multiple concurrent imports"""
        # Create multiple import batches
        batches = []
        for i in range(5):
            batch = ImportBatch.objects.create(
                file_name=f'concurrent_test_{i}.csv',
                status='pending'
            )
            batches.append(batch)
        
        # Simulate concurrent processing
        csv_content = """shopping_center_name,address_city,address_state
Test Center,San Jose,CA"""
        
        for batch in batches:
            service = CSVImportService(batch)
            service.process_csv_file(csv_content)
        
        # Verify all batches completed successfully
        for batch in batches:
            batch.refresh_from_db()
            self.assertEqual(batch.status, 'completed')
        
        # Should have created shopping centers (may be deduplicated by name)
        self.assertGreaterEqual(ShoppingCenter.objects.count(), 1)


# =============================================================================
# AUTHENTICATION AND PERMISSION TESTS
# =============================================================================

class ImportAuthenticationTest(APITestCase):
    """Test authentication and permissions for import endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )
    
    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated users cannot access endpoints"""
        urls_to_test = [
            reverse('importbatch-list'),
            reverse('csv-upload'),
            reverse('csv-validate'),
            reverse('csv-template'),
            reverse('import-stats'),
        ]
        
        for url in urls_to_test:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_regular_user_access_allowed(self):
        """Test that regular authenticated users can access most endpoints"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get(reverse('importbatch-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response = self.client.get(reverse('csv-template'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_admin_only_endpoints_require_admin(self):
        """Test that admin endpoints require admin permissions"""
        # Test with regular user
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post(reverse('load-sample-data'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        response = self.client.delete(reverse('clear-imports'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Test with admin user
        self.client.force_authenticate(user=self.admin_user)
        
        response = self.client.post(reverse('load-sample-data'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
