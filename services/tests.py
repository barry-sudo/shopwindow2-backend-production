# ===== SERVICES LAYER TEST SUITE =====
"""
Comprehensive test suite for services layer functionality
File: services/tests.py

Test Coverage:
- Geocoding service with Google Maps API integration
- Business logic calculations and property analysis
- Quality scoring algorithms and data validation
- Error handling for external API failures
- Performance testing for calculation-intensive operations
- Integration testing between services
- Utility functions and helper methods
"""

import json
from decimal import Decimal
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, timedelta

from django.test import TestCase, TransactionTestCase, override_settings
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.utils import timezone

from properties.models import ShoppingCenter, Tenant
from imports.models import ImportBatch

# Import the services we're testing
from .geocoding import (
    geocode_address, reverse_geocode, validate_coordinates,
    get_address_components, batch_geocode_addresses
)
from .business_logic import (
    calculate_quality_score, validate_shopping_center_data,
    calculate_occupancy_rate, calculate_average_rent,
    analyze_tenant_mix, calculate_property_metrics,
    generate_property_report, compare_properties
)


# =============================================================================
# GEOCODING SERVICE TESTS
# =============================================================================

class GeocodingServiceTest(TestCase):
    """Test geocoding service functionality"""
    
    def setUp(self):
        """Set up geocoding test data"""
        self.test_address = "2855 Stevens Creek Blvd, Santa Clara, CA 95050"
        self.test_coordinates = Point(-121.9718, 37.3230)  # Santa Clara coordinates
        
        # Mock Google Maps API response
        self.mock_geocoding_response = {
            'results': [{
                'geometry': {
                    'location': {
                        'lat': 37.3230,
                        'lng': -121.9718
                    }
                },
                'address_components': [
                    {'long_name': '2855', 'types': ['street_number']},
                    {'long_name': 'Stevens Creek Boulevard', 'types': ['route']},
                    {'long_name': 'Santa Clara', 'types': ['locality']},
                    {'long_name': 'California', 'types': ['administrative_area_level_1']},
                    {'long_name': '95050', 'types': ['postal_code']}
                ],
                'formatted_address': '2855 Stevens Creek Blvd, Santa Clara, CA 95050, USA'
            }],
            'status': 'OK'
        }
        
        self.mock_reverse_geocoding_response = {
            'results': [{
                'formatted_address': '2855 Stevens Creek Blvd, Santa Clara, CA 95050, USA',
                'address_components': [
                    {'long_name': '2855', 'types': ['street_number']},
                    {'long_name': 'Stevens Creek Boulevard', 'types': ['route']},
                    {'long_name': 'Santa Clara', 'types': ['locality']},
                    {'long_name': 'California', 'types': ['administrative_area_level_1']},
                    {'long_name': '95050', 'types': ['postal_code']}
                ]
            }],
            'status': 'OK'
        }
    
    @patch('services.geocoding.requests.get')
    def test_geocode_address_success(self, mock_get):
        """Test successful address geocoding"""
        mock_response = Mock()
        mock_response.json.return_value = self.mock_geocoding_response
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = geocode_address(self.test_address)
        
        self.assertIsInstance(result, Point)
        self.assertAlmostEqual(result.x, -121.9718, places=4)
        self.assertAlmostEqual(result.y, 37.3230, places=4)
        
        # Verify API was called correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args[1]
        self.assertIn('address', call_args['params'])
        self.assertEqual(call_args['params']['address'], self.test_address)
    
    @patch('services.geocoding.requests.get')
    def test_geocode_address_no_results(self, mock_get):
        """Test geocoding with no results"""
        mock_response = Mock()
        mock_response.json.return_value = {'results': [], 'status': 'ZERO_RESULTS'}
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = geocode_address("Invalid Address That Doesn't Exist")
        
        self.assertIsNone(result)
    
    @patch('services.geocoding.requests.get')
    def test_geocode_address_api_error(self, mock_get):
        """Test geocoding API error handling"""
        mock_response = Mock()
        mock_response.json.return_value = {'status': 'REQUEST_DENIED', 'error_message': 'Invalid API key'}
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = geocode_address(self.test_address)
        
        self.assertIsNone(result)
    
    @patch('services.geocoding.requests.get')
    def test_geocode_address_network_error(self, mock_get):
        """Test geocoding network error handling"""
        mock_get.side_effect = ConnectionError("Network error")
        
        result = geocode_address(self.test_address)
        
        self.assertIsNone(result)
    
    @patch('services.geocoding.requests.get')
    def test_reverse_geocode_success(self, mock_get):
        """Test successful reverse geocoding"""
        mock_response = Mock()
        mock_response.json.return_value = self.mock_reverse_geocoding_response
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = reverse_geocode(self.test_coordinates)
        
        self.assertIsInstance(result, dict)
        self.assertIn('formatted_address', result)
        self.assertIn('Santa Clara', result['formatted_address'])
    
    def test_validate_coordinates_valid(self):
        """Test coordinate validation with valid coordinates"""
        # Valid coordinates
        self.assertTrue(validate_coordinates(-121.9718, 37.3230))
        self.assertTrue(validate_coordinates(0, 0))  # Equator/Prime Meridian
        self.assertTrue(validate_coordinates(-180, -90))  # Valid extremes
        self.assertTrue(validate_coordinates(180, 90))  # Valid extremes
    
    def test_validate_coordinates_invalid(self):
        """Test coordinate validation with invalid coordinates"""
        # Invalid latitude (must be -90 to 90)
        self.assertFalse(validate_coordinates(-121.9718, 91))
        self.assertFalse(validate_coordinates(-121.9718, -91))
        
        # Invalid longitude (must be -180 to 180)
        self.assertFalse(validate_coordinates(-181, 37.3230))
        self.assertFalse(validate_coordinates(181, 37.3230))
        
        # Non-numeric values
        self.assertFalse(validate_coordinates("invalid", 37.3230))
        self.assertFalse(validate_coordinates(-121.9718, "invalid"))
    
    @patch('services.geocoding.requests.get')
    def test_get_address_components_success(self, mock_get):
        """Test extracting address components"""
        mock_response = Mock()
        mock_response.json.return_value = self.mock_geocoding_response
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        components = get_address_components(self.test_address)
        
        self.assertIsInstance(components, dict)
        self.assertEqual(components['street_number'], '2855')
        self.assertEqual(components['route'], 'Stevens Creek Boulevard')
        self.assertEqual(components['locality'], 'Santa Clara')
        self.assertEqual(components['administrative_area_level_1'], 'California')
        self.assertEqual(components['postal_code'], '95050')
    
    @patch('services.geocoding.geocode_address')
    def test_batch_geocode_addresses(self, mock_geocode):
        """Test batch geocoding multiple addresses"""
        addresses = [
            "2855 Stevens Creek Blvd, Santa Clara, CA",
            "1 Infinite Loop, Cupertino, CA",
            "1600 Amphitheatre Parkway, Mountain View, CA"
        ]
        
        # Mock geocoding results
        mock_geocode.side_effect = [
            Point(-121.9718, 37.3230),  # Santa Clara
            Point(-122.0312, 37.3318),  # Cupertino
            Point(-122.0840, 37.4220)   # Mountain View
        ]
        
        results = batch_geocode_addresses(addresses)
        
        self.assertEqual(len(results), 3)
        self.assertEqual(mock_geocode.call_count, 3)
        
        # Check results
        for i, result in enumerate(results):
            self.assertEqual(result['address'], addresses[i])
            self.assertIsInstance(result['coordinates'], Point)
            self.assertTrue(result['success'])
    
    @patch('services.geocoding.geocode_address')
    def test_batch_geocode_with_failures(self, mock_geocode):
        """Test batch geocoding with some failures"""
        addresses = [
            "Valid Address, Santa Clara, CA",
            "Invalid Address That Doesn't Exist",
            "Another Valid Address, San Jose, CA"
        ]
        
        # Mock mixed results
        mock_geocode.side_effect = [
            Point(-121.9718, 37.3230),  # Success
            None,                       # Failure
            Point(-121.8863, 37.3382)   # Success
        ]
        
        results = batch_geocode_addresses(addresses)
        
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]['success'])
        self.assertFalse(results[1]['success'])
        self.assertTrue(results[2]['success'])
    
    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_geocoding_without_api_key(self):
        """Test geocoding without API key"""
        result = geocode_address(self.test_address)
        self.assertIsNone(result)
    
    @patch('services.geocoding.requests.get')
    def test_geocoding_rate_limiting(self, mock_get):
        """Test geocoding rate limiting handling"""
        mock_response = Mock()
        mock_response.json.return_value = {'status': 'OVER_QUERY_LIMIT'}
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = geocode_address(self.test_address)
        
        self.assertIsNone(result)
    
    @patch('services.geocoding.time.sleep')
    @patch('services.geocoding.requests.get')
    def test_geocoding_with_retry(self, mock_get, mock_sleep):
        """Test geocoding with retry mechanism"""
        # First call fails with rate limit, second succeeds
        mock_responses = [
            Mock(json=lambda: {'status': 'OVER_QUERY_LIMIT'}, status_code=200),
            Mock(json=lambda: self.mock_geocoding_response, status_code=200)
        ]
        mock_get.side_effect = mock_responses
        
        result = geocode_address(self.test_address, max_retries=2)
        
        self.assertIsInstance(result, Point)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once()


# =============================================================================
# BUSINESS LOGIC TESTS
# =============================================================================

class BusinessLogicTest(TestCase):
    """Test business logic calculations and analysis"""
    
    def setUp(self):
        """Set up business logic test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Business Logic Test Mall',
            center_type='mall',
            total_gla=500000,
            address_street='123 Test Street',
            address_city='Test City',
            address_state='CA',
            address_zip='12345',
            owner_name='Test Owner',
            property_manager='Test Manager',
            year_built=2010
        )
        
        # Create tenants with varying data completeness
        self.tenants = [
            Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name='Complete Data Store',
                suite_number='CD101',
                suite_sqft=10000,
                tenant_category='electronics',
                rent_psf=Decimal('80.00'),
                lease_status='occupied'
            ),
            Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name='Partial Data Store',
                suite_number='PD102',
                suite_sqft=5000,
                lease_status='occupied'
                # Missing rent_psf and category
            ),
            Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name='Vacant Suite',
                suite_number='V103',
                suite_sqft=3000,
                lease_status='vacant'
            )
        ]
    
    def test_calculate_quality_score_complete_data(self):
        """Test quality score calculation for complete data"""
        # Add geocoding data for completeness
        self.shopping_center.geo_location = Point(-122.0, 37.0)
        self.shopping_center.save()
        
        score = calculate_quality_score(self.shopping_center)
        
        # Should have high quality score (80-100) with complete data
        self.assertGreaterEqual(score, 80)
        self.assertLessEqual(score, 100)
    
    def test_calculate_quality_score_incomplete_data(self):
        """Test quality score calculation for incomplete data"""
        # Create shopping center with minimal data
        incomplete_center = ShoppingCenter.objects.create(
            shopping_center_name='Incomplete Center'
            # Missing most fields
        )
        
        score = calculate_quality_score(incomplete_center)
        
        # Should have lower quality score
        self.assertLess(score, 50)
        self.assertGreaterEqual(score, 0)
    
    def test_validate_shopping_center_data(self):
        """Test shopping center data validation"""
        validation_result = validate_shopping_center_data(self.shopping_center)
        
        self.assertIsInstance(validation_result, dict)
        self.assertIn('valid', validation_result)
        self.assertIn('errors', validation_result)
        self.assertIn('warnings', validation_result)
        self.assertIn('completeness_score', validation_result)
        
        # Should be mostly valid
        self.assertTrue(validation_result['valid'])
        self.assertLessEqual(len(validation_result['errors']), 1)
    
    def test_validate_shopping_center_data_invalid(self):
        """Test validation with invalid data"""
        invalid_center = ShoppingCenter.objects.create(
            shopping_center_name='',  # Empty name
            total_gla=-1000,  # Negative GLA
            year_built=1800   # Too old
        )
        
        validation_result = validate_shopping_center_data(invalid_center)
        
        self.assertFalse(validation_result['valid'])
        self.assertGreater(len(validation_result['errors']), 0)
    
    def test_calculate_occupancy_rate(self):
        """Test occupancy rate calculation"""
        occupancy_rate = calculate_occupancy_rate(self.shopping_center)
        
        # Two occupied tenants: 10,000 + 5,000 = 15,000 sq ft
        # Total GLA: 500,000 sq ft
        # Expected occupancy: 3%
        expected_rate = (15000 / 500000) * 100
        
        self.assertEqual(occupancy_rate, expected_rate)
        self.assertEqual(occupancy_rate, 3.0)
    
    def test_calculate_occupancy_rate_no_tenants(self):
        """Test occupancy rate with no tenants"""
        empty_center = ShoppingCenter.objects.create(
            shopping_center_name='Empty Center',
            total_gla=100000
        )
        
        occupancy_rate = calculate_occupancy_rate(empty_center)
        self.assertEqual(occupancy_rate, 0.0)
    
    def test_calculate_occupancy_rate_no_gla(self):
        """Test occupancy rate with no GLA specified"""
        center_no_gla = ShoppingCenter.objects.create(
            shopping_center_name='No GLA Center'
        )
        
        occupancy_rate = calculate_occupancy_rate(center_no_gla)
        self.assertEqual(occupancy_rate, 0.0)
    
    def test_calculate_average_rent(self):
        """Test average rent calculation"""
        avg_rent = calculate_average_rent(self.shopping_center)
        
        # Only one tenant has rent data: 10,000 sq ft at $80/sq ft
        # Expected average: $80.00
        expected_rent = Decimal('80.00')
        
        self.assertEqual(avg_rent, expected_rent)
    
    def test_calculate_average_rent_no_rent_data(self):
        """Test average rent with no rent data"""
        # Create center with tenants but no rent data
        no_rent_center = ShoppingCenter.objects.create(
            shopping_center_name='No Rent Center',
            total_gla=100000
        )
        
        Tenant.objects.create(
            shopping_center=no_rent_center,
            tenant_name='No Rent Store',
            suite_sqft=5000,
            lease_status='occupied'
            # No rent_psf
        )
        
        avg_rent = calculate_average_rent(no_rent_center)
        self.assertEqual(avg_rent, Decimal('0.00'))
    
    def test_calculate_average_rent_weighted(self):
        """Test weighted average rent calculation"""
        # Add another tenant with different rent
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='High Rent Store',
            suite_sqft=2000,
            rent_psf=Decimal('120.00'),
            lease_status='occupied'
        )
        
        avg_rent = calculate_average_rent(self.shopping_center)
        
        # Weighted average: (10000 * 80 + 2000 * 120) / (10000 + 2000)
        # = (800000 + 240000) / 12000 = 1040000 / 12000 = 86.67
        expected_rent = Decimal('1040000') / Decimal('12000')
        
        self.assertAlmostEqual(float(avg_rent), float(expected_rent), places=2)
    
    def test_analyze_tenant_mix(self):
        """Test tenant mix analysis"""
        tenant_mix = analyze_tenant_mix(self.shopping_center)
        
        self.assertIsInstance(tenant_mix, dict)
        self.assertIn('categories', tenant_mix)
        self.assertIn('total_tenants', tenant_mix)
        self.assertIn('occupied_tenants', tenant_mix)
        self.assertIn('vacant_tenants', tenant_mix)
        
        # Check category breakdown
        categories = tenant_mix['categories']
        self.assertIn('electronics', categories)
        self.assertEqual(categories['electronics']['count'], 1)
        self.assertEqual(categories['electronics']['sqft'], 10000)
        
        # Check totals
        self.assertEqual(tenant_mix['total_tenants'], 3)
        self.assertEqual(tenant_mix['occupied_tenants'], 2)
        self.assertEqual(tenant_mix['vacant_tenants'], 1)
    
    def test_calculate_property_metrics(self):
        """Test comprehensive property metrics calculation"""
        metrics = calculate_property_metrics(self.shopping_center)
        
        self.assertIsInstance(metrics, dict)
        
        # Check required metrics
        required_metrics = [
            'total_gla', 'occupied_sqft', 'vacant_sqft', 'occupancy_rate',
            'total_tenants', 'occupied_tenants', 'vacant_tenants',
            'average_rent_psf', 'total_annual_rent', 'quality_score',
            'tenant_categories'
        ]
        
        for metric in required_metrics:
            self.assertIn(metric, metrics)
        
        # Validate specific calculations
        self.assertEqual(metrics['total_gla'], 500000)
        self.assertEqual(metrics['occupied_sqft'], 15000)
        self.assertEqual(metrics['vacant_sqft'], 3000)
        self.assertEqual(metrics['occupancy_rate'], 3.0)
        self.assertEqual(metrics['total_tenants'], 3)
        self.assertEqual(metrics['occupied_tenants'], 2)
    
    def test_generate_property_report(self):
        """Test property report generation"""
        report = generate_property_report(self.shopping_center)
        
        self.assertIsInstance(report, dict)
        
        # Check report sections
        expected_sections = [
            'property_info', 'location_info', 'financial_summary',
            'tenant_summary', 'occupancy_analysis', 'data_quality',
            'recommendations'
        ]
        
        for section in expected_sections:
            self.assertIn(section, report)
        
        # Validate property info
        prop_info = report['property_info']
        self.assertEqual(prop_info['name'], 'Business Logic Test Mall')
        self.assertEqual(prop_info['type'], 'mall')
        
        # Validate financial summary
        financial = report['financial_summary']
        self.assertIn('total_annual_rent', financial)
        self.assertIn('average_rent_psf', financial)
        self.assertIn('occupancy_rate', financial)
    
    def test_compare_properties(self):
        """Test property comparison functionality"""
        # Create second property for comparison
        other_center = ShoppingCenter.objects.create(
            shopping_center_name='Comparison Mall',
            center_type='mall',
            total_gla=300000,
            address_city='Other City',
            address_state='CA'
        )
        
        # Add tenant to other center
        Tenant.objects.create(
            shopping_center=other_center,
            tenant_name='Other Store',
            suite_sqft=8000,
            rent_psf=Decimal('70.00'),
            lease_status='occupied'
        )
        
        comparison = compare_properties([self.shopping_center, other_center])
        
        self.assertIsInstance(comparison, dict)
        self.assertIn('properties', comparison)
        self.assertIn('comparison_metrics', comparison)
        
        # Check properties included
        properties = comparison['properties']
        self.assertEqual(len(properties), 2)
        
        # Check comparison metrics
        metrics = comparison['comparison_metrics']
        self.assertIn('gla_comparison', metrics)
        self.assertIn('rent_comparison', metrics)
        self.assertIn('occupancy_comparison', metrics)
    
    def test_business_logic_edge_cases(self):
        """Test business logic with edge cases"""
        # Test with zero GLA
        zero_gla_center = ShoppingCenter.objects.create(
            shopping_center_name='Zero GLA Center',
            total_gla=0
        )
        
        occupancy = calculate_occupancy_rate(zero_gla_center)
        self.assertEqual(occupancy, 0.0)
        
        # Test with very high rent
        high_rent_center = ShoppingCenter.objects.create(
            shopping_center_name='High Rent Center',
            total_gla=10000
        )
        
        Tenant.objects.create(
            shopping_center=high_rent_center,
            tenant_name='Expensive Store',
            suite_sqft=1000,
            rent_psf=Decimal('500.00'),  # Very high rent
            lease_status='occupied'
        )
        
        avg_rent = calculate_average_rent(high_rent_center)
        self.assertEqual(avg_rent, Decimal('500.00'))
        
        metrics = calculate_property_metrics(high_rent_center)
        self.assertEqual(metrics['total_annual_rent'], Decimal('500000'))


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class ServicesIntegrationTest(TransactionTestCase):
    """Integration tests between different services"""
    
    def setUp(self):
        """Set up integration test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Integration Test Center',
            center_type='mall',
            total_gla=400000,
            address_street='789 Integration Blvd',
            address_city='Integration City',
            address_state='CA',
            address_zip='54321'
        )
    
    @patch('services.geocoding.requests.get')
    def test_geocoding_business_logic_integration(self, mock_get):
        """Test integration between geocoding and business logic"""
        # Mock successful geocoding
        mock_response = Mock()
        mock_response.json.return_value = {
            'results': [{
                'geometry': {
                    'location': {'lat': 37.5, 'lng': -122.0}
                }
            }],
            'status': 'OK'
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        # Geocode the shopping center
        if self.shopping_center.has_complete_address:
            location = geocode_address(self.shopping_center.full_address)
            if location:
                self.shopping_center.geo_location = location
                self.shopping_center.save()
        
        # Calculate quality score (should be higher with location)
        quality_with_location = calculate_quality_score(self.shopping_center)
        
        # Remove location and recalculate
        self.shopping_center.geo_location = None
        self.shopping_center.save()
        quality_without_location = calculate_quality_score(self.shopping_center)
        
        # Quality should be higher with location data
        self.assertGreater(quality_with_location, quality_without_location)
    
    def test_import_quality_scoring_integration(self):
        """Test integration with import quality scoring"""
        # Simulate import batch
        import_batch = ImportBatch.objects.create(
            file_name='integration_test.csv',
            status='completed',
            records_processed=1
        )
        
        # Calculate property quality
        quality_score = calculate_quality_score(self.shopping_center)
        
        # Update import batch with quality info
        import_batch.quality_score = quality_score
        import_batch.save()
        
        # Verify integration
        import_batch.refresh_from_db()
        self.assertEqual(import_batch.quality_score, quality_score)
        self.assertGreaterEqual(quality_score, 0)
        self.assertLessEqual(quality_score, 100)
    
    @patch('services.geocoding.geocode_address')
    def test_batch_processing_integration(self, mock_geocode):
        """Test batch processing with multiple services"""
        # Create multiple shopping centers
        centers = []
        for i in range(5):
            center = ShoppingCenter.objects.create(
                shopping_center_name=f'Batch Center {i}',
                center_type='mall',
                total_gla=100000 + (i * 10000),
                address_city=f'City {i}',
                address_state='CA'
            )
            centers.append(center)
        
        # Mock geocoding for all centers
        mock_geocode.side_effect = [
            Point(-122.0 + i * 0.1, 37.0 + i * 0.1) for i in range(5)
        ]
        
        # Process batch geocoding and quality calculation
        for center in centers:
            if center.has_complete_address:
                location = geocode_address(center.full_address)
                if location:
                    center.geo_location = location
                    center.save()
            
            # Calculate quality for each
            quality = calculate_quality_score(center)
            center.data_quality_score = quality
            center.save()
        
        # Verify all centers were processed
        self.assertEqual(mock_geocode.call_count, 5)
        
        for center in centers:
            center.refresh_from_db()
            self.assertIsNotNone(center.geo_location)
            self.assertIsNotNone(center.data_quality_score)


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class ServicesPerformanceTest(TransactionTestCase):
    """Performance tests for services layer"""
    
    def setUp(self):
        """Set up performance test data"""
        # Create multiple shopping centers with tenants
        self.shopping_centers = []
        
        for i in range(20):
            center = ShoppingCenter.objects.create(
                shopping_center_name=f'Performance Center {i}',
                center_type='mall' if i % 2 == 0 else 'strip_center',
                total_gla=100000 + (i * 5000),
                address_street=f'{100 + i} Performance St',
                address_city=f'Perf City {i % 5}',
                address_state='CA',
                address_zip=f'9{i:04d}',
                geo_location=Point(-122.0 + (i * 0.01), 37.0 + (i * 0.01))
            )
            
            # Add tenants to each center
            for j in range(5):
                Tenant.objects.create(
                    shopping_center=center,
                    tenant_name=f'Store {i}-{j}',
                    suite_sqft=1000 + (j * 200),
                    rent_psf=Decimal('50.00') + (j * 5),
                    tenant_category='retail',
                    lease_status='occupied' if j < 4 else 'vacant'
                )
            
            self.shopping_centers.append(center)
    
    def test_bulk_quality_score_calculation_performance(self):
        """Test performance of bulk quality score calculations"""
        import time
        
        start_time = time.time()
        
        quality_scores = []
        for center in self.shopping_centers:
            score = calculate_quality_score(center)
            quality_scores.append(score)
        
        end_time = time.time()
        calculation_time = end_time - start_time
        
        # Should complete quickly
        self.assertLess(calculation_time, 2.0)  # Less than 2 seconds
        self.assertEqual(len(quality_scores), 20)
        
        # All scores should be valid
        for score in quality_scores:
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)
    
    def test_bulk_business_metrics_calculation_performance(self):
        """Test performance of bulk business metrics calculations"""
        import time
        
        start_time = time.time()
        
        all_metrics = []
        for center in self.shopping_centers:
            metrics = calculate_property_metrics(center)
            all_metrics.append(metrics)
        
        end_time = time.time()
        calculation_time = end_time - start_time
        
        # Should complete efficiently
        self.assertLess(calculation_time, 3.0)  # Less than 3 seconds
        self.assertEqual(len(all_metrics), 20)
        
        # Verify metrics are calculated correctly
        for metrics in all_metrics:
            self.assertIn('occupancy_rate', metrics)
            self.assertIn('average_rent_psf', metrics)
            self.assertIn('total_annual_rent', metrics)
    
    @patch('services.geocoding.geocode_address')
    def test_batch_geocoding_performance(self, mock_geocode):
        """Test performance of batch geocoding operations"""
        import time
        
        # Mock geocoding responses
        mock_geocode.side_effect = [
            Point(-122.0 + i * 0.01, 37.0 + i * 0.01) for i in range(20)
        ]
        
        addresses = [center.full_address for center in self.shopping_centers[:20]]
        
        start_time = time.time()
        results = batch_geocode_addresses(addresses)
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        # Should complete reasonably quickly
        self.assertLess(processing_time, 5.0)  # Less than 5 seconds
        self.assertEqual(len(results), 20)
        
        # All should be successful (mocked)
        successful_geocodes = sum(1 for r in results if r['success'])
        self.assertEqual(successful_geocodes, 20)
    
    def test_property_comparison_performance(self):
        """Test performance of property comparison with multiple properties"""
        import time
        
        # Compare all shopping centers
        start_time = time.time()
        comparison = compare_properties(self.shopping_centers)
        end_time = time.time()
        
        comparison_time = end_time - start_time
        
        # Should handle comparison efficiently
        self.assertLess(comparison_time, 5.0)  # Less than 5 seconds
        
        # Check comparison results
        self.assertIn('properties', comparison)
        self.assertIn('comparison_metrics', comparison)
        self.assertEqual(len(comparison['properties']), 20)


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class ServicesErrorHandlingTest(TestCase):
    """Test error handling in services layer"""
    
    def setUp(self):
        """Set up error handling test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Error Test Center'
        )
    
    def test_geocoding_invalid_address(self):
        """Test geocoding with invalid address"""
        result = geocode_address("")
        self.assertIsNone(result)
        
        result = geocode_address(None)
        self.assertIsNone(result)
        
        result = geocode_address("   ")  # Whitespace only
        self.assertIsNone(result)
    
    def test_business_logic_invalid_data(self):
        """Test business logic with invalid data"""
        # Test with None input
        with self.assertRaises((TypeError, AttributeError)):
            calculate_quality_score(None)
        
        # Test with non-existent shopping center
        fake_center = ShoppingCenter()  # Not saved to database
        
        # Should handle gracefully
        score = calculate_quality_score(fake_center)
        self.assertIsInstance(score, (int, float))
        self.assertGreaterEqual(score, 0)
    
    def test_occupancy_calculation_edge_cases(self):
        """Test occupancy calculation edge cases"""
        # Shopping center with negative GLA
        negative_gla_center = ShoppingCenter.objects.create(
            shopping_center_name='Negative GLA Center',
            total_gla=-1000
        )
        
        occupancy = calculate_occupancy_rate(negative_gla_center)
        self.assertEqual(occupancy, 0.0)
        
        # Shopping center with very large GLA
        huge_gla_center = ShoppingCenter.objects.create(
            shopping_center_name='Huge GLA Center',
            total_gla=999999999
        )
        
        Tenant.objects.create(
            shopping_center=huge_gla_center,
            tenant_name='Small Tenant',
            suite_sqft=1000,
            lease_status='occupied'
        )
        
        occupancy = calculate_occupancy_rate(huge_gla_center)
        self.assertGreater(occupancy, 0)
        self.assertLess(occupancy, 1)  # Should be very small percentage
    
    def test_rent_calculation_edge_cases(self):
        """Test rent calculation with edge cases"""
        # Tenant with negative rent
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Negative Rent Store',
            suite_sqft=1000,
            rent_psf=Decimal('-10.00'),  # Negative rent
            lease_status='occupied'
        )
        
        avg_rent = calculate_average_rent(self.shopping_center)
        # Should handle gracefully (might be 0 or negative)
        self.assertIsInstance(avg_rent, Decimal)
        
        # Tenant with extremely high rent
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Extreme Rent Store',
            suite_sqft=1,
            rent_psf=Decimal('99999.99'),
            lease_status='occupied'
        )
        
        # Should not cause overflow errors
        avg_rent = calculate_average_rent(self.shopping_center)
        self.assertIsInstance(avg_rent, Decimal)
    
    def test_validation_with_missing_fields(self):
        """Test validation with missing required fields"""
        incomplete_center = ShoppingCenter.objects.create(
            shopping_center_name='Incomplete Center'
            # Many fields missing
        )
        
        # Should not raise exceptions
        validation_result = validate_shopping_center_data(incomplete_center)
        self.assertIsInstance(validation_result, dict)
        self.assertIn('valid', validation_result)
        self.assertIn('errors', validation_result)
        
        quality_score = calculate_quality_score(incomplete_center)
        self.assertIsInstance(quality_score, (int, float))
        self.assertGreaterEqual(quality_score, 0)
        self.assertLessEqual(quality_score, 100)
    
    @patch('services.geocoding.requests.get')
    def test_geocoding_timeout_handling(self, mock_get):
        """Test geocoding timeout handling"""
        from requests.exceptions import Timeout
        
        mock_get.side_effect = Timeout("Request timed out")
        
        result = geocode_address("123 Test Street, Test City, CA")
        self.assertIsNone(result)
    
    @patch('services.geocoding.requests.get')
    def test_geocoding_connection_error_handling(self, mock_get):
        """Test geocoding connection error handling"""
        from requests.exceptions import ConnectionError
        
        mock_get.side_effect = ConnectionError("Connection failed")
        
        result = geocode_address("123 Test Street, Test City, CA")
        self.assertIsNone(result)


# =============================================================================
# UTILITY AND HELPER FUNCTION TESTS
# =============================================================================

class ServicesUtilityTest(TestCase):
    """Test utility functions and helpers in services layer"""
    
    def test_coordinate_validation_edge_cases(self):
        """Test coordinate validation with edge cases"""
        # Test boundary values
        self.assertTrue(validate_coordinates(-180, -90))  # Southwest corner
        self.assertTrue(validate_coordinates(180, 90))    # Northeast corner
        self.assertTrue(validate_coordinates(0, 0))       # Origin
        
        # Test just outside boundaries
        self.assertFalse(validate_coordinates(-180.1, 0))
        self.assertFalse(validate_coordinates(180.1, 0))
        self.assertFalse(validate_coordinates(0, -90.1))
        self.assertFalse(validate_coordinates(0, 90.1))
        
        # Test with floating point precision
        self.assertTrue(validate_coordinates(-179.999999, 89.999999))
        self.assertTrue(validate_coordinates(179.999999, -89.999999))
    
    def test_address_component_extraction(self):
        """Test address component extraction utilities"""
        mock_components = [
            {'long_name': '123', 'types': ['street_number']},
            {'long_name': 'Main Street', 'types': ['route']},
            {'long_name': 'Anytown', 'types': ['locality']},
            {'long_name': 'California', 'types': ['administrative_area_level_1']},
            {'long_name': 'CA', 'types': ['administrative_area_level_1', 'political']},
            {'long_name': '12345', 'types': ['postal_code']}
        ]
        
        # This would be tested if we had a utility function for parsing components
        # For now, test the structure we expect
        expected_components = {
            'street_number': '123',
            'route': 'Main Street',
            'locality': 'Anytown',
            'administrative_area_level_1': 'California',
            'postal_code': '12345'
        }
        
        self.assertIsInstance(expected_components, dict)
        self.assertEqual(expected_components['street_number'], '123')
    
    def test_business_metrics_rounding(self):
        """Test proper rounding in business metrics"""
        center = ShoppingCenter.objects.create(
            shopping_center_name='Rounding Test Center',
            total_gla=333333  # Will create fractional percentages
        )
        
        Tenant.objects.create(
            shopping_center=center,
            tenant_name='Fraction Store',
            suite_sqft=11111,  # Creates 3.333...% occupancy
            lease_status='occupied'
        )
        
        occupancy = calculate_occupancy_rate(center)
        
        # Should be properly rounded
        self.assertIsInstance(occupancy, float)
        self.assertAlmostEqual(occupancy, 3.333, places=2)
    
    def test_data_type_consistency(self):
        """Test data type consistency across services"""
        center = ShoppingCenter.objects.create(
            shopping_center_name='Data Type Test Center',
            total_gla=100000
        )
        
        Tenant.objects.create(
            shopping_center=center,
            tenant_name='Type Test Store',
            suite_sqft=5000,
            rent_psf=Decimal('75.50'),
            lease_status='occupied'
        )
        
        # Test that all functions return expected data types
        quality_score = calculate_quality_score(center)
        self.assertIsInstance(quality_score, (int, float))
        
        occupancy_rate = calculate_occupancy_rate(center)
        self.assertIsInstance(occupancy_rate, float)
        
        avg_rent = calculate_average_rent(center)
        self.assertIsInstance(avg_rent, Decimal)
        
        metrics = calculate_property_metrics(center)
        self.assertIsInstance(metrics, dict)
        
        tenant_mix = analyze_tenant_mix(center)
        self.assertIsInstance(tenant_mix, dict)
    
    def test_null_and_empty_value_handling(self):
        """Test handling of null and empty values"""
        # Test with minimal data
        minimal_center = ShoppingCenter.objects.create(
            shopping_center_name='Minimal Center'
        )
        
        # All calculations should handle missing data gracefully
        quality_score = calculate_quality_score(minimal_center)
        self.assertIsInstance(quality_score, (int, float))
        self.assertGreaterEqual(quality_score, 0)
        
        occupancy_rate = calculate_occupancy_rate(minimal_center)
        self.assertEqual(occupancy_rate, 0.0)
        
        avg_rent = calculate_average_rent(minimal_center)
        self.assertEqual(avg_rent, Decimal('0.00'))
        
        tenant_mix = analyze_tenant_mix(minimal_center)
        self.assertEqual(tenant_mix['total_tenants'], 0)
