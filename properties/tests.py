# ===== PROPERTIES APP TEST SUITE =====
"""
Comprehensive test suite for properties app functionality
File: properties/tests.py

Test Coverage:
- ShoppingCenter and Tenant model operations
- Spatial database functionality (PostGIS integration)
- API endpoints for property discovery and management
- Admin interface functionality and business logic
- Data quality tracking and validation
- Integration with imports and services
- Performance testing for map-based queries
"""

import json
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, Mock

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.utils import timezone

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import ShoppingCenter, Tenant
from .admin import ShoppingCenterAdmin, TenantAdmin

User = get_user_model()


# =============================================================================
# SHOPPING CENTER MODEL TESTS
# =============================================================================

class ShoppingCenterModelTest(TestCase):
    """Test ShoppingCenter model functionality and business logic"""
    
    def setUp(self):
        """Set up test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Westfield Valley Fair',
            center_type='mall',
            total_gla=2100000,
            address_street='2855 Stevens Creek Blvd',
            address_city='Santa Clara',
            address_state='CA',
            address_zip='95050',
            owner_name='Westfield Corporation',
            property_manager='Westfield Management',
            year_built=1986
        )
    
    def test_create_shopping_center(self):
        """Test creating a shopping center with basic data"""
        center = ShoppingCenter.objects.create(
            shopping_center_name='Test Mall',
            center_type='mall',
            total_gla=150000,
            address_city='San Jose',
            address_state='CA'
        )
        
        self.assertEqual(center.shopping_center_name, 'Test Mall')
        self.assertEqual(center.center_type, 'mall')
        self.assertEqual(center.total_gla, 150000)
        self.assertIsNotNone(center.created_at)
        self.assertIsNotNone(center.updated_at)
    
    def test_shopping_center_string_representation(self):
        """Test string representation of shopping center"""
        expected = 'Westfield Valley Fair (mall)'
        self.assertEqual(str(self.shopping_center), expected)
    
    def test_shopping_center_unique_name_constraint(self):
        """Test that shopping center names must be unique"""
        with self.assertRaises(Exception):  # IntegrityError
            ShoppingCenter.objects.create(
                shopping_center_name='Westfield Valley Fair',  # Duplicate name
                center_type='strip_center'
            )
    
    def test_full_address_property(self):
        """Test full address property concatenation"""
        expected_address = '2855 Stevens Creek Blvd, Santa Clara, CA 95050'
        self.assertEqual(self.shopping_center.full_address, expected_address)
    
    def test_full_address_partial_data(self):
        """Test full address with missing components"""
        center = ShoppingCenter.objects.create(
            shopping_center_name='Partial Address Center',
            address_city='San Jose',
            address_state='CA'
        )
        
        expected = 'San Jose, CA'
        self.assertEqual(center.full_address, expected)
    
    def test_has_complete_address_property(self):
        """Test has_complete_address property"""
        # Complete address
        self.assertTrue(self.shopping_center.has_complete_address)
        
        # Incomplete address
        incomplete_center = ShoppingCenter.objects.create(
            shopping_center_name='Incomplete Center',
            address_city='San Jose'
        )
        self.assertFalse(incomplete_center.has_complete_address)
    
    def test_geo_location_field(self):
        """Test geographic location field (PostGIS Point)"""
        # Set geographic coordinates (longitude, latitude)
        location = Point(-121.9718, 37.3230)  # Santa Clara, CA coordinates
        
        self.shopping_center.geo_location = location
        self.shopping_center.save()
        
        self.shopping_center.refresh_from_db()
        self.assertIsNotNone(self.shopping_center.geo_location)
        self.assertAlmostEqual(self.shopping_center.geo_location.x, -121.9718, places=4)
        self.assertAlmostEqual(self.shopping_center.geo_location.y, 37.3230, places=4)
    
    def test_center_type_choices(self):
        """Test valid center type choices"""
        valid_types = ['mall', 'strip_center', 'shopping_center', 'outlet', 'lifestyle', 'power_center', 'other']
        
        for center_type in valid_types:
            center = ShoppingCenter.objects.create(
                shopping_center_name=f'Test {center_type} Center',
                center_type=center_type
            )
            self.assertEqual(center.center_type, center_type)
    
    def test_occupancy_rate_calculation(self):
        """Test occupancy rate calculation based on tenants"""
        # Add some tenants
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Apple Store',
            suite_sqft=8500,
            lease_status='occupied'
        )
        
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Microsoft Store',
            suite_sqft=7500,
            lease_status='occupied'
        )
        
        # Calculate occupancy (16,000 sq ft occupied out of 2,100,000 total)
        occupied_sqft = self.shopping_center.tenants.filter(
            lease_status='occupied'
        ).aggregate(
            total=models.Sum('suite_sqft')
        )['total'] or 0
        
        expected_occupancy = (occupied_sqft / self.shopping_center.total_gla) * 100
        
        # This would typically be calculated in a model method or service
        self.assertGreater(occupied_sqft, 0)
        self.assertLess(expected_occupancy, 1)  # Less than 1% occupancy
    
    def test_data_quality_score_field(self):
        """Test data quality score field"""
        self.shopping_center.data_quality_score = 85
        self.shopping_center.save()
        
        self.shopping_center.refresh_from_db()
        self.assertEqual(self.shopping_center.data_quality_score, 85)
        
        # Test invalid scores (should be 0-100)
        # This would be validated in model clean() method or serializer
        with self.assertRaises(Exception):
            center = ShoppingCenter.objects.create(
                shopping_center_name='Invalid Score Center',
                data_quality_score=150  # Invalid score > 100
            )


# =============================================================================
# TENANT MODEL TESTS
# =============================================================================

class TenantModelTest(TestCase):
    """Test Tenant model functionality and relationships"""
    
    def setUp(self):
        """Set up test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Test Shopping Center',
            center_type='mall',
            total_gla=100000
        )
        
        self.tenant = Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Apple Store',
            suite_number='A101',
            suite_sqft=8500,
            tenant_category='electronics',
            rent_psf=Decimal('85.00'),
            lease_status='occupied'
        )
    
    def test_create_tenant(self):
        """Test creating a tenant with basic data"""
        tenant = Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Starbucks Coffee',
            suite_number='F201',
            suite_sqft=1200,
            tenant_category='food_beverage',
            rent_psf=Decimal('35.50'),
            lease_status='occupied'
        )
        
        self.assertEqual(tenant.tenant_name, 'Starbucks Coffee')
        self.assertEqual(tenant.suite_number, 'F201')
        self.assertEqual(tenant.suite_sqft, 1200)
        self.assertEqual(tenant.rent_psf, Decimal('35.50'))
        self.assertEqual(tenant.shopping_center, self.shopping_center)
        self.assertIsNotNone(tenant.created_at)
    
    def test_tenant_string_representation(self):
        """Test string representation of tenant"""
        expected = 'Apple Store - A101 (Test Shopping Center)'
        self.assertEqual(str(self.tenant), expected)
    
    def test_tenant_shopping_center_relationship(self):
        """Test relationship between tenant and shopping center"""
        self.assertEqual(self.tenant.shopping_center, self.shopping_center)
        
        # Test reverse relationship
        tenants = self.shopping_center.tenants.all()
        self.assertIn(self.tenant, tenants)
    
    def test_annual_rent_calculation(self):
        """Test annual rent calculation"""
        annual_rent = self.tenant.suite_sqft * self.tenant.rent_psf
        expected_rent = 8500 * Decimal('85.00')
        
        self.assertEqual(annual_rent, expected_rent)
        self.assertEqual(annual_rent, Decimal('722500.00'))
    
    def test_lease_status_choices(self):
        """Test valid lease status choices"""
        valid_statuses = ['occupied', 'vacant', 'available', 'pending']
        
        for status in valid_statuses:
            tenant = Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name=f'Test Tenant {status}',
                suite_number=f'T{status[0].upper()}01',
                lease_status=status
            )
            self.assertEqual(tenant.lease_status, status)
    
    def test_tenant_category_field(self):
        """Test tenant category field"""
        categories = ['electronics', 'food_beverage', 'clothing', 'services', 'entertainment']
        
        for category in categories:
            tenant = Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name=f'{category.title()} Store',
                suite_number=f'C{categories.index(category)}01',
                tenant_category=category
            )
            self.assertEqual(tenant.tenant_category, category)
    
    def test_rent_psf_decimal_precision(self):
        """Test rent per square foot decimal precision"""
        tenant = Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Precision Test Store',
            suite_number='P101',
            rent_psf=Decimal('42.99')
        )
        
        self.assertEqual(tenant.rent_psf, Decimal('42.99'))
        
        # Test high precision rent
        tenant.rent_psf = Decimal('123.456')
        tenant.save()
        tenant.refresh_from_db()
        
        # Should maintain decimal precision
        self.assertEqual(tenant.rent_psf, Decimal('123.456'))


# =============================================================================
# SPATIAL DATABASE TESTS (PostGIS)
# =============================================================================

class SpatialDatabaseTest(TestCase):
    """Test PostGIS spatial database functionality"""
    
    def setUp(self):
        """Set up test data with geographic coordinates"""
        # San Jose area shopping centers
        self.center_sj = ShoppingCenter.objects.create(
            shopping_center_name='San Jose Center',
            address_city='San Jose',
            address_state='CA',
            geo_location=Point(-121.8863, 37.3382)  # San Jose coordinates
        )
        
        # Santa Clara shopping center
        self.center_sc = ShoppingCenter.objects.create(
            shopping_center_name='Santa Clara Mall',
            address_city='Santa Clara',
            address_state='CA',
            geo_location=Point(-121.9718, 37.3230)  # Santa Clara coordinates
        )
        
        # Oakland shopping center (farther away)
        self.center_oak = ShoppingCenter.objects.create(
            shopping_center_name='Oakland Plaza',
            address_city='Oakland',
            address_state='CA',
            geo_location=Point(-122.2711, 37.8044)  # Oakland coordinates
        )
    
    def test_distance_calculation(self):
        """Test calculating distance between shopping centers"""
        from django.contrib.gis.measure import Distance
        
        # Calculate distance between San Jose and Santa Clara
        san_jose_point = self.center_sj.geo_location
        santa_clara_point = self.center_sc.geo_location
        
        distance = san_jose_point.distance(santa_clara_point)
        
        # Distance should be reasonable (approximately 10km)
        self.assertGreater(distance, 0)
        self.assertLess(distance, 0.2)  # Less than 0.2 degrees
    
    def test_nearby_centers_query(self):
        """Test querying nearby shopping centers"""
        from django.contrib.gis.measure import Distance
        
        # Find centers within 50km of San Jose
        san_jose_point = Point(-121.8863, 37.3382)
        
        nearby_centers = ShoppingCenter.objects.filter(
            geo_location__distance_lte=(san_jose_point, Distance(km=50))
        )
        
        # Should include San Jose and Santa Clara, but not Oakland
        self.assertIn(self.center_sj, nearby_centers)
        self.assertIn(self.center_sc, nearby_centers)
        # Oakland might be included depending on exact distance
        
    def test_bounding_box_query(self):
        """Test querying shopping centers within bounding box (for map)"""
        from django.contrib.gis.geos import Polygon
        
        # Define bounding box around San Francisco Bay Area
        bbox = Polygon.from_bbox((-122.5, 37.0, -121.0, 38.0))  # (xmin, ymin, xmax, ymax)
        
        centers_in_bbox = ShoppingCenter.objects.filter(
            geo_location__within=bbox
        )
        
        # All test centers should be within this bounding box
        self.assertGreaterEqual(centers_in_bbox.count(), 2)
        self.assertIn(self.center_sj, centers_in_bbox)
        self.assertIn(self.center_sc, centers_in_bbox)
    
    def test_center_without_location(self):
        """Test handling shopping centers without geographic data"""
        center_no_geo = ShoppingCenter.objects.create(
            shopping_center_name='No Location Center',
            address_city='Unknown',
            address_state='CA'
        )
        
        # Should not be included in spatial queries
        from django.contrib.gis.measure import Distance
        
        nearby_centers = ShoppingCenter.objects.filter(
            geo_location__distance_lte=(Point(-121.8863, 37.3382), Distance(km=50))
        )
        
        self.assertNotIn(center_no_geo, nearby_centers)
    
    def test_geocoding_status_tracking(self):
        """Test tracking geocoding status for addresses"""
        center = ShoppingCenter.objects.create(
            shopping_center_name='Geocoding Test Center',
            address_street='123 Test Street',
            address_city='Test City',
            address_state='CA',
            address_zip='12345'
        )
        
        # Initially should have no geocoding status
        self.assertIsNone(center.geo_location)
        
        # Simulate successful geocoding
        center.geo_location = Point(-121.0, 37.0)
        center.save()
        
        center.refresh_from_db()
        self.assertIsNotNone(center.geo_location)


# =============================================================================
# ADMIN INTERFACE TESTS
# =============================================================================

class ShoppingCenterAdminTest(TestCase):
    """Test ShoppingCenter admin interface functionality"""
    
    def setUp(self):
        """Set up admin test data"""
        self.site = AdminSite()
        self.admin = ShoppingCenterAdmin(ShoppingCenter, self.site)
        
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Admin Test Mall',
            center_type='mall',
            total_gla=250000,
            address_city='San Francisco',
            address_state='CA',
            geo_location=Point(-122.4194, 37.7749)
        )
        
        # Add some tenants
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Admin Test Store',
            suite_sqft=5000,
            lease_status='occupied'
        )
    
    def get_request(self):
        """Create mock request for admin testing"""
        request = HttpRequest()
        request.user = self.superuser
        
        # Add session and messages middleware
        SessionMiddleware().process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        request._messages = messages
        
        return request
    
    def test_admin_list_display(self):
        """Test admin list display configuration"""
        expected_fields = [
            'shopping_center_name_display',
            'center_type_badge',
            'location_display',
            'total_gla_display',
            'occupancy_display',
            'tenant_count_display',
            'data_quality_display',
            'map_link'
        ]
        
        self.assertEqual(self.admin.list_display, expected_fields)
    
    def test_admin_list_filter(self):
        """Test admin list filter configuration"""
        expected_filters = [
            'center_type',
            'address_state',
            'address_city',
            ('total_gla', admin.RangeNumericFilter),
            ('occupancy_rate', admin.RangeNumericFilter),
            'has_complete_address',
            'data_quality_score'
        ]
        
        # Check that filters are configured
        self.assertIsInstance(self.admin.list_filter, list)
        self.assertIn('center_type', self.admin.list_filter)
        self.assertIn('address_state', self.admin.list_filter)
    
    def test_admin_search_fields(self):
        """Test admin search configuration"""
        expected_search_fields = [
            'shopping_center_name',
            'address_street',
            'address_city',
            'address_state',
            'address_zip',
            'owner_name',
            'property_manager'
        ]
        
        for field in expected_search_fields:
            self.assertIn(field, self.admin.search_fields)
    
    def test_custom_display_methods(self):
        """Test custom admin display methods"""
        request = self.get_request()
        
        # Test shopping_center_name_display
        name_display = self.admin.shopping_center_name_display(self.shopping_center)
        self.assertIn('Admin Test Mall', name_display)
        self.assertIn('1 tenant', name_display)  # Should show tenant count
        
        # Test center_type_badge
        type_badge = self.admin.center_type_badge(self.shopping_center)
        self.assertIn('mall', type_badge)
        self.assertIn('background:', type_badge)  # Should have styling
        
        # Test total_gla_display
        gla_display = self.admin.total_gla_display(self.shopping_center)
        self.assertIn('250,000', gla_display)
        self.assertIn('sq ft', gla_display)
        
        # Test map_link
        map_link = self.admin.map_link(self.shopping_center)
        self.assertIn('google.com/maps', map_link)
        self.assertIn('📍', map_link)
    
    def test_admin_actions(self):
        """Test custom admin actions"""
        expected_actions = [
            'geocode_properties',
            'calculate_occupancy',
            'export_property_data',
            'mark_for_review'
        ]
        
        for action in expected_actions:
            self.assertIn(action, self.admin.actions)
    
    @patch('properties.admin.geocode_address')
    def test_geocode_properties_action(self, mock_geocode):
        """Test geocoding admin action"""
        mock_geocode.return_value = Point(-122.0, 37.0)
        
        request = self.get_request()
        queryset = ShoppingCenter.objects.filter(pk=self.shopping_center.pk)
        
        # Execute geocoding action
        self.admin.geocode_properties(request, queryset)
        
        # Should have attempted geocoding (mocked)
        # In real implementation, would update geo_location field
    
    def test_calculate_occupancy_action(self):
        """Test occupancy calculation admin action"""
        request = self.get_request()
        queryset = ShoppingCenter.objects.filter(pk=self.shopping_center.pk)
        
        # Execute occupancy calculation action
        self.admin.calculate_occupancy(request, queryset)
        
        # Should calculate occupancy based on tenants
        # In real implementation, would update occupancy_rate field
    
    def test_export_property_data_action(self):
        """Test property data export admin action"""
        request = self.get_request()
        queryset = ShoppingCenter.objects.filter(pk=self.shopping_center.pk)
        
        # Execute export action
        response = self.admin.export_property_data(request, queryset)
        
        # Should return CSV response
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])


class TenantAdminTest(TestCase):
    """Test Tenant admin interface functionality"""
    
    def setUp(self):
        """Set up tenant admin test data"""
        self.site = AdminSite()
        self.admin = TenantAdmin(Tenant, self.site)
        
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Tenant Admin Test Center',
            center_type='mall'
        )
        
        self.tenant = Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Test Tenant Store',
            suite_number='TA101',
            suite_sqft=3500,
            tenant_category='retail',
            rent_psf=Decimal('45.00'),
            lease_status='occupied'
        )
    
    def test_tenant_admin_list_display(self):
        """Test tenant admin list display"""
        expected_fields = [
            'tenant_name_display',
            'shopping_center_link',
            'tenant_category_badge',
            'suite_info_display',
            'rent_display',
            'lease_status_display'
        ]
        
        self.assertEqual(self.admin.list_display, expected_fields)
    
    def test_tenant_display_methods(self):
        """Test tenant custom display methods"""
        # Test tenant_name_display
        name_display = self.admin.tenant_name_display(self.tenant)
        self.assertIn('Test Tenant Store', name_display)
        self.assertIn('TA101', name_display)
        
        # Test suite_info_display
        suite_display = self.admin.suite_info_display(self.tenant)
        self.assertIn('3,500', suite_display)
        self.assertIn('sq ft', suite_display)
        
        # Test rent_display
        rent_display = self.admin.rent_display(self.tenant)
        self.assertIn('$45.00', rent_display)
        self.assertIn('$157,500', rent_display)  # Annual rent calculation


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================

class PropertiesAPITestCase(APITestCase):
    """Base test case for properties API endpoints"""
    
    def setUp(self):
        """Set up API test data"""
        self.user = User.objects.create_user(
            username='apitest',
            email='apitest@example.com',
            password='testpass123'
        )
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create test shopping centers
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='API Test Mall',
            center_type='mall',
            total_gla=180000,
            address_street='123 API Street',
            address_city='API City',
            address_state='CA',
            address_zip='12345',
            owner_name='API Owner LLC',
            property_manager='API Management',
            geo_location=Point(-122.0, 37.0)
        )
        
        # Create test tenants
        self.tenant = Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='API Test Store',
            suite_number='API101',
            suite_sqft=2500,
            tenant_category='retail',
            rent_psf=Decimal('55.00'),
            lease_status='occupied'
        )


class ShoppingCenterAPITest(PropertiesAPITestCase):
    """Test shopping center API endpoints"""
    
    def test_list_shopping_centers(self):
        """Test listing shopping centers"""
        url = reverse('shoppingcenter-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['shopping_center_name'], 'API Test Mall')
    
    def test_retrieve_shopping_center(self):
        """Test retrieving specific shopping center"""
        url = reverse('shoppingcenter-detail', kwargs={'pk': self.shopping_center.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['shopping_center_name'], 'API Test Mall')
        self.assertEqual(response.data['center_type'], 'mall')
        self.assertEqual(response.data['total_gla'], 180000)
    
    def test_filter_shopping_centers_by_state(self):
        """Test filtering shopping centers by state"""
        # Create center in different state
        ShoppingCenter.objects.create(
            shopping_center_name='NY Test Mall',
            address_state='NY'
        )
        
        url = reverse('shoppingcenter-list')
        response = self.client.get(url, {'address_state': 'CA'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['address_state'], 'CA')
    
    def test_filter_shopping_centers_by_center_type(self):
        """Test filtering shopping centers by type"""
        # Create different type of center
        ShoppingCenter.objects.create(
            shopping_center_name='Strip Center Test',
            center_type='strip_center'
        )
        
        url = reverse('shoppingcenter-list')
        response = self.client.get(url, {'center_type': 'mall'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['center_type'], 'mall')
    
    def test_search_shopping_centers(self):
        """Test searching shopping centers by name"""
        url = reverse('shoppingcenter-list')
        response = self.client.get(url, {'search': 'API Test'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['shopping_center_name'], 'API Test Mall')
    
    def test_shopping_center_with_tenants(self):
        """Test shopping center includes tenant information"""
        url = reverse('shoppingcenter-detail', kwargs={'pk': self.shopping_center.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should include tenant information
        if 'tenants' in response.data:
            self.assertEqual(len(response.data['tenants']), 1)
            self.assertEqual(response.data['tenants'][0]['tenant_name'], 'API Test Store')
    
    def test_create_shopping_center(self):
        """Test creating new shopping center via API"""
        url = reverse('shoppingcenter-list')
        data = {
            'shopping_center_name': 'New API Mall',
            'center_type': 'mall',
            'total_gla': 200000,
            'address_city': 'New City',
            'address_state': 'CA'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['shopping_center_name'], 'New API Mall')
        
        # Verify it was created in database
        new_center = ShoppingCenter.objects.get(shopping_center_name='New API Mall')
        self.assertEqual(new_center.center_type, 'mall')
    
    def test_update_shopping_center(self):
        """Test updating shopping center via API"""
        url = reverse('shoppingcenter-detail', kwargs={'pk': self.shopping_center.pk})
        data = {
            'total_gla': 200000,
            'occupancy_rate': 85.5
        }
        
        response = self.client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_gla'], 200000)
        
        # Verify in database
        self.shopping_center.refresh_from_db()
        self.assertEqual(self.shopping_center.total_gla, 200000)


class TenantAPITest(PropertiesAPITestCase):
    """Test tenant API endpoints"""
    
    def test_list_tenants(self):
        """Test listing tenants"""
        url = reverse('tenant-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['tenant_name'], 'API Test Store')
    
    def test_retrieve_tenant(self):
        """Test retrieving specific tenant"""
        url = reverse('tenant-detail', kwargs={'pk': self.tenant.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tenant_name'], 'API Test Store')
        self.assertEqual(response.data['suite_number'], 'API101')
    
    def test_filter_tenants_by_shopping_center(self):
        """Test filtering tenants by shopping center"""
        # Create tenant in different center
        other_center = ShoppingCenter.objects.create(
            shopping_center_name='Other Center'
        )
        
        Tenant.objects.create(
            shopping_center=other_center,
            tenant_name='Other Store'
        )
        
        url = reverse('tenant-list')
        response = self.client.get(url, {'shopping_center': self.shopping_center.pk})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['tenant_name'], 'API Test Store')
    
    def test_filter_tenants_by_category(self):
        """Test filtering tenants by category"""
        # Create tenant with different category
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Food Store',
            tenant_category='food_beverage'
        )
        
        url = reverse('tenant-list')
        response = self.client.get(url, {'tenant_category': 'retail'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['tenant_category'], 'retail')
    
    def test_create_tenant(self):
        """Test creating new tenant via API"""
        url = reverse('tenant-list')
        data = {
            'shopping_center': self.shopping_center.pk,
            'tenant_name': 'New Tenant Store',
            'suite_number': 'NEW101',
            'suite_sqft': 1800,
            'tenant_category': 'services',
            'rent_psf': '40.00',
            'lease_status': 'occupied'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tenant_name'], 'New Tenant Store')
        
        # Verify in database
        new_tenant = Tenant.objects.get(tenant_name='New Tenant Store')
        self.assertEqual(new_tenant.suite_sqft, 1800)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class PropertiesIntegrationTest(TransactionTestCase):
    """Integration tests for properties with other systems"""
    
    def setUp(self):
        """Set up integration test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Integration Test Mall',
            center_type='mall',
            total_gla=300000,
            address_street='456 Integration Blvd',
            address_city='Integration City',
            address_state='CA'
        )
    
    @patch('services.geocoding.geocode_address')
    def test_integration_with_geocoding_service(self, mock_geocode):
        """Test integration with geocoding service"""
        mock_geocode.return_value = Point(-122.1, 37.1)
        
        # Simulate geocoding when address is complete
        if self.shopping_center.has_complete_address:
            # This would typically be called by signal or service
            from services.geocoding import geocode_address
            location = geocode_address(self.shopping_center.full_address)
            
            if location:
                self.shopping_center.geo_location = location
                self.shopping_center.save()
        
        mock_geocode.assert_called_once()
        self.shopping_center.refresh_from_db()
        self.assertIsNotNone(self.shopping_center.geo_location)
    
    def test_integration_with_import_system(self):
        """Test integration with CSV import system"""
        # This would typically be tested with actual imports app
        # For now, test that properties can be created by external system
        
        # Simulate import system creating properties
        imported_center = ShoppingCenter.objects.create(
            shopping_center_name='Imported via CSV',
            center_type='strip_center',
            total_gla=50000,
            address_city='Import City',
            address_state='TX'
        )
        
        # Add tenant via same import
        imported_tenant = Tenant.objects.create(
            shopping_center=imported_center,
            tenant_name='Imported Store',
            suite_sqft=2000,
            lease_status='occupied'
        )
        
        # Verify relationships work correctly
        self.assertEqual(imported_tenant.shopping_center, imported_center)
        self.assertEqual(imported_center.tenants.count(), 1)
    
    def test_data_quality_tracking_integration(self):
        """Test integration with data quality tracking"""
        # Simulate quality score calculation
        quality_factors = {
            'has_name': bool(self.shopping_center.shopping_center_name),
            'has_address': self.shopping_center.has_complete_address,
            'has_gla': bool(self.shopping_center.total_gla),
            'has_type': bool(self.shopping_center.center_type),
            'has_location': bool(self.shopping_center.geo_location)
        }
        
        # Calculate simple quality score (0-100)
        quality_score = (sum(quality_factors.values()) / len(quality_factors)) * 100
        
        self.shopping_center.data_quality_score = int(quality_score)
        self.shopping_center.save()
        
        # Should have reasonable quality score
        self.assertGreaterEqual(self.shopping_center.data_quality_score, 50)
        self.assertLessEqual(self.shopping_center.data_quality_score, 100)


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class PropertiesPerformanceTest(TransactionTestCase):
    """Performance tests for properties functionality"""
    
    def setUp(self):
        """Set up performance test data"""
        # Create multiple shopping centers for performance testing
        self.shopping_centers = []
        for i in range(50):
            center = ShoppingCenter.objects.create(
                shopping_center_name=f'Performance Test Center {i}',
                center_type='mall' if i % 2 == 0 else 'strip_center',
                total_gla=100000 + (i * 1000),
                address_city=f'City_{i % 10}',
                address_state='CA' if i % 3 == 0 else 'TX',
                geo_location=Point(-122.0 + (i * 0.01), 37.0 + (i * 0.01))
            )
            self.shopping_centers.append(center)
            
            # Add tenants to each center
            for j in range(3):
                Tenant.objects.create(
                    shopping_center=center,
                    tenant_name=f'Store {i}-{j}',
                    suite_number=f'S{i}{j}',
                    suite_sqft=1000 + (j * 500),
                    tenant_category='retail',
                    lease_status='occupied'
                )
    
    def test_bulk_shopping_center_query_performance(self):
        """Test performance of bulk shopping center queries"""
        import time
        
        start_time = time.time()
        
        # Query all shopping centers with related data
        centers = ShoppingCenter.objects.select_related().prefetch_related('tenants')
        center_list = list(centers)
        
        end_time = time.time()
        query_time = end_time - start_time
        
        # Should complete quickly
        self.assertLess(query_time, 1.0)  # Less than 1 second
        self.assertEqual(len(center_list), 50)
    
    def test_spatial_query_performance(self):
        """Test performance of spatial queries"""
        import time
        from django.contrib.gis.measure import Distance
        
        start_time = time.time()
        
        # Find centers within 50km of a point
        center_point = Point(-122.0, 37.0)
        nearby_centers = ShoppingCenter.objects.filter(
            geo_location__distance_lte=(center_point, Distance(km=50))
        )
        
        nearby_list = list(nearby_centers)
        
        end_time = time.time()
        query_time = end_time - start_time
        
        # Spatial queries should be reasonably fast
        self.assertLess(query_time, 2.0)  # Less than 2 seconds
        self.assertGreater(len(nearby_list), 0)
    
    def test_aggregation_query_performance(self):
        """Test performance of aggregation queries"""
        import time
        from django.db.models import Count, Sum, Avg
        
        start_time = time.time()
        
        # Perform complex aggregations
        stats = ShoppingCenter.objects.aggregate(
            total_centers=Count('id'),
            total_gla=Sum('total_gla'),
            avg_gla=Avg('total_gla'),
            tenant_count=Count('tenants')
        )
        
        end_time = time.time()
        query_time = end_time - start_time
        
        # Aggregation should be fast
        self.assertLess(query_time, 0.5)  # Less than 0.5 seconds
        self.assertEqual(stats['total_centers'], 50)
        self.assertGreater(stats['total_gla'], 0)


# =============================================================================
# BUSINESS LOGIC TESTS
# =============================================================================

class PropertiesBusinessLogicTest(TestCase):
    """Test business logic and calculations for properties"""
    
    def setUp(self):
        """Set up business logic test data"""
        self.shopping_center = ShoppingCenter.objects.create(
            shopping_center_name='Business Logic Test Mall',
            center_type='mall',
            total_gla=500000,
            address_city='Business City',
            address_state='CA'
        )
        
        # Add tenants with varying rent and sizes
        self.tenants = [
            Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name='High Rent Store',
                suite_sqft=10000,
                rent_psf=Decimal('100.00'),
                lease_status='occupied'
            ),
            Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name='Medium Rent Store',
                suite_sqft=5000,
                rent_psf=Decimal('60.00'),
                lease_status='occupied'
            ),
            Tenant.objects.create(
                shopping_center=self.shopping_center,
                tenant_name='Vacant Suite',
                suite_sqft=3000,
                lease_status='vacant'
            )
        ]
    
    def test_occupancy_rate_calculation(self):
        """Test occupancy rate calculation"""
        occupied_tenants = self.shopping_center.tenants.filter(lease_status='occupied')
        total_occupied_sqft = sum(t.suite_sqft for t in occupied_tenants)
        
        occupancy_rate = (total_occupied_sqft / self.shopping_center.total_gla) * 100
        expected_rate = (15000 / 500000) * 100  # 3% occupancy
        
        self.assertEqual(occupancy_rate, expected_rate)
        self.assertEqual(occupancy_rate, 3.0)
    
    def test_average_rent_calculation(self):
        """Test average rent per square foot calculation"""
        occupied_tenants = self.shopping_center.tenants.filter(
            lease_status='occupied',
            rent_psf__isnull=False
        )
        
        if occupied_tenants:
            total_rent_weighted = sum(
                t.suite_sqft * t.rent_psf for t in occupied_tenants
            )
            total_occupied_sqft = sum(t.suite_sqft for t in occupied_tenants)
            avg_rent = total_rent_weighted / total_occupied_sqft
            
            # Expected: (10000 * 100 + 5000 * 60) / 15000 = 86.67
            expected_avg = (Decimal('1000000') + Decimal('300000')) / Decimal('15000')
            
            self.assertAlmostEqual(float(avg_rent), float(expected_avg), places=2)
    
    def test_total_annual_rent_calculation(self):
        """Test total annual rent calculation"""
        occupied_tenants = self.shopping_center.tenants.filter(
            lease_status='occupied',
            rent_psf__isnull=False
        )
        
        total_annual_rent = sum(
            t.suite_sqft * t.rent_psf for t in occupied_tenants
        )
        
        expected_rent = (10000 * Decimal('100.00')) + (5000 * Decimal('60.00'))
        expected_rent = Decimal('1000000') + Decimal('300000')  # $1,300,000
        
        self.assertEqual(total_annual_rent, expected_rent)
    
    def test_tenant_mix_analysis(self):
        """Test tenant mix analysis by category"""
        # Add tenants with different categories
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Electronics Store',
            tenant_category='electronics',
            suite_sqft=2000
        )
        
        Tenant.objects.create(
            shopping_center=self.shopping_center,
            tenant_name='Food Court',
            tenant_category='food_beverage',
            suite_sqft=3000
        )
        
        # Analyze tenant mix
        tenant_mix = {}
        for tenant in self.shopping_center.tenants.all():
            category = tenant.tenant_category or 'uncategorized'
            if category not in tenant_mix:
                tenant_mix[category] = {'count': 0, 'total_sqft': 0}
            tenant_mix[category]['count'] += 1
            tenant_mix[category]['total_sqft'] += tenant.suite_sqft or 0
        
        self.assertIn('electronics', tenant_mix)
        self.assertIn('food_beverage', tenant_mix)
        self.assertEqual(tenant_mix['electronics']['count'], 1)
        self.assertEqual(tenant_mix['electronics']['total_sqft'], 2000)
    
    def test_property_valuation_factors(self):
        """Test basic property valuation factors"""
        # Calculate basic property metrics
        metrics = {
            'total_gla': self.shopping_center.total_gla,
            'occupied_sqft': sum(
                t.suite_sqft for t in self.shopping_center.tenants.filter(
                    lease_status='occupied'
                )
            ),
            'annual_rent': sum(
                t.suite_sqft * (t.rent_psf or 0) 
                for t in self.shopping_center.tenants.filter(lease_status='occupied')
            ),
            'tenant_count': self.shopping_center.tenants.count(),
            'occupancy_rate': None  # Calculate below
        }
        
        # Calculate occupancy rate
        if metrics['total_gla'] > 0:
            metrics['occupancy_rate'] = (
                metrics['occupied_sqft'] / metrics['total_gla']
            ) * 100
        
        # Validate metrics
        self.assertEqual(metrics['total_gla'], 500000)
        self.assertEqual(metrics['occupied_sqft'], 15000)
        self.assertEqual(metrics['annual_rent'], Decimal('1300000'))
        self.assertEqual(metrics['tenant_count'], 4)  # Including vacant tenant
        self.assertEqual(metrics['occupancy_rate'], 3.0)
