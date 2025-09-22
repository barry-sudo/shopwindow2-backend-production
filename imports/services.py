# ===== IMPORTS SERVICES - CSV PROCESSING BUSINESS LOGIC =====
"""
CSV Processing Services for Shop Window Import System
File: imports/services.py

This module implements the core business logic for processing CSV files
containing shopping center and tenant data, following the "stocking shelves"
philosophy: import first, validate incrementally.

Key Services:
- CSV file processing and validation
- Data extraction and transformation
- Shopping center and tenant record creation
- Quality scoring and data completeness tracking
- Import batch management and error handling
"""

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple, Any
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone

# Import models
from .models import ImportBatch
from properties.models import ShoppingCenter, Tenant

# Import services
from services.geocoding import geocode_address
from services.business_logic import calculate_quality_score, validate_shopping_center_data

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CSV PROCESSING SERVICE
# =============================================================================

class CSVImportService:
    """
    Primary service class for processing CSV imports
    Handles the complete workflow from file upload to record creation
    """
    
    # Expected CSV headers for shopping centers
    SHOPPING_CENTER_HEADERS = {
        'shopping_center_name': ['shopping_center_name', 'property_name', 'center_name'],
        'center_type': ['center_type', 'property_type', 'type'],
        'total_gla': ['total_gla', 'gla', 'gross_leasable_area', 'total_sqft'],
        'address_street': ['address_street', 'street_address', 'address'],
        'address_city': ['address_city', 'city'],
        'address_state': ['address_state', 'state'],
        'address_zip': ['address_zip', 'zip', 'zipcode', 'zip_code'],
        'owner_name': ['owner_name', 'owner', 'property_owner'],
        'property_manager': ['property_manager', 'manager', 'pm'],
        'year_built': ['year_built', 'built_year', 'construction_year']
    }
    
    # Expected CSV headers for tenants
    TENANT_HEADERS = {
        'tenant_name': ['tenant_name', 'business_name', 'store_name'],
        'suite_number': ['suite_number', 'suite', 'unit', 'space'],
        'suite_sqft': ['suite_sqft', 'square_feet', 'sqft', 'size'],
        'tenant_category': ['tenant_category', 'category', 'business_type'],
        'rent_psf': ['rent_psf', 'rent_per_sqft', 'psf_rent'],
        'lease_status': ['lease_status', 'status', 'occupancy_status']
    }
    
    def __init__(self, import_batch: ImportBatch):
        """
        Initialize CSV import service with import batch
        
        Args:
            import_batch: ImportBatch instance to track processing
        """
        self.import_batch = import_batch
        self.errors = []
        self.warnings = []
        self.processed_count = 0
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0
    
    def process_csv_file(self, file_content: str) -> Dict[str, Any]:
        """
        Process CSV file content and create/update records
        
        Args:
            file_content: String content of CSV file
            
        Returns:
            Dict containing processing results and statistics
        """
        logger.info(f"Starting CSV processing for batch {self.import_batch.batch_id}")
        
        try:
            # Update batch status
            self.import_batch.status = 'processing'
            self.import_batch.save()
            
            # Parse CSV content
            csv_data = self._parse_csv_content(file_content)
            
            if not csv_data:
                raise ValueError("No valid data found in CSV file")
            
            # Process records in transaction for data integrity
            with transaction.atomic():
                self._process_csv_records(csv_data)
            
            # Calculate quality score
            quality_score = self._calculate_import_quality()
            
            # Update batch with results
            self._finalize_import_batch(quality_score)
            
            return self._generate_processing_results()
            
        except Exception as e:
            logger.error(f"CSV processing failed for batch {self.import_batch.batch_id}: {str(e)}")
            self._handle_processing_error(str(e))
            raise
    
    def _parse_csv_content(self, content: str) -> List[Dict[str, str]]:
        """
        Parse CSV content and return list of dictionaries
        
        Args:
            content: Raw CSV content as string
            
        Returns:
            List of dictionaries with normalized headers
        """
        try:
            # Use StringIO to treat string as file-like object
            csv_file = io.StringIO(content)
            
            # Detect CSV dialect
            sample = content[:1024]
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            # Read CSV with detected delimiter
            csv_file.seek(0)  # Reset to beginning
            reader = csv.DictReader(csv_file, delimiter=delimiter)
            
            # Normalize headers and collect data
            normalized_data = []
            headers_mapping = self._create_headers_mapping(reader.fieldnames)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 for header row
                try:
                    normalized_row = self._normalize_row_data(row, headers_mapping)
                    normalized_row['_row_number'] = row_num
                    normalized_data.append(normalized_row)
                    
                except Exception as e:
                    self.errors.append(f"Row {row_num}: {str(e)}")
                    continue
            
            logger.info(f"Parsed {len(normalized_data)} rows from CSV")
            return normalized_data
            
        except Exception as e:
            error_msg = f"Failed to parse CSV content: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _create_headers_mapping(self, csv_headers: List[str]) -> Dict[str, str]:
        """
        Create mapping between CSV headers and model fields
        
        Args:
            csv_headers: List of headers from CSV file
            
        Returns:
            Dictionary mapping CSV headers to model field names
        """
        mapping = {}
        csv_headers_lower = [h.lower().strip().replace(' ', '_') for h in csv_headers if h]
        
        # Map shopping center headers
        for field, possible_headers in self.SHOPPING_CENTER_HEADERS.items():
            for csv_header in csv_headers_lower:
                if csv_header in possible_headers:
                    mapping[csv_header] = field
                    break
        
        # Map tenant headers
        for field, possible_headers in self.TENANT_HEADERS.items():
            for csv_header in csv_headers_lower:
                if csv_header in possible_headers:
                    mapping[csv_header] = field
                    break
        
        logger.info(f"Created header mapping: {mapping}")
        return mapping
    
    def _normalize_row_data(self, row: Dict[str, str], headers_mapping: Dict[str, str]) -> Dict[str, str]:
        """
        Normalize row data using headers mapping
        
        Args:
            row: Raw CSV row data
            headers_mapping: Mapping of CSV headers to model fields
            
        Returns:
            Normalized row data
        """
        normalized = {}
        
        for csv_key, csv_value in row.items():
            if csv_key and csv_value:
                # Clean the key and value
                clean_key = csv_key.lower().strip().replace(' ', '_')
                clean_value = str(csv_value).strip()
                
                # Map to model field if available
                model_field = headers_mapping.get(clean_key, clean_key)
                normalized[model_field] = clean_value
        
        return normalized
    
    def _process_csv_records(self, csv_data: List[Dict[str, str]]) -> None:
        """
        Process CSV records and create/update database records
        
        Args:
            csv_data: List of normalized CSV row data
        """
        self.import_batch.records_total = len(csv_data)
        self.import_batch.save()
        
        for row_data in csv_data:
            try:
                self._process_single_record(row_data)
                self.processed_count += 1
                
                # Update progress every 10 records
                if self.processed_count % 10 == 0:
                    self.import_batch.records_processed = self.processed_count
                    self.import_batch.save()
                    
            except Exception as e:
                row_num = row_data.get('_row_number', 'unknown')
                error_msg = f"Row {row_num}: {str(e)}"
                self.errors.append(error_msg)
                logger.warning(error_msg)
                continue
    
    def _process_single_record(self, row_data: Dict[str, str]) -> None:
        """
        Process a single CSV record - create or update shopping center and tenant
        
        Args:
            row_data: Normalized row data from CSV
        """
        # Extract shopping center data
        shopping_center_data = self._extract_shopping_center_data(row_data)
        
        if not shopping_center_data.get('shopping_center_name'):
            raise ValueError("Shopping center name is required")
        
        # Create or update shopping center using "stocking shelves" approach
        shopping_center, created = self._get_or_create_shopping_center(shopping_center_data)
        
        if created:
            self.created_count += 1
            logger.info(f"Created shopping center: {shopping_center.shopping_center_name}")
        else:
            # Update existing record with new data
            updated = self._update_shopping_center(shopping_center, shopping_center_data)
            if updated:
                self.updated_count += 1
                logger.info(f"Updated shopping center: {shopping_center.shopping_center_name}")
        
        # Process tenant data if available
        tenant_data = self._extract_tenant_data(row_data)
        if tenant_data.get('tenant_name'):
            self._process_tenant_record(shopping_center, tenant_data)
    
    def _extract_shopping_center_data(self, row_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract shopping center data from row
        
        Args:
            row_data: Normalized row data
            
        Returns:
            Dictionary of shopping center field data
        """
        shopping_center_data = {}
        
        # Extract and clean basic fields
        for field in ['shopping_center_name', 'center_type', 'address_street', 
                     'address_city', 'address_state', 'address_zip', 
                     'owner_name', 'property_manager']:
            value = row_data.get(field)
            if value:
                shopping_center_data[field] = value
        
        # Handle numeric fields
        if row_data.get('total_gla'):
            try:
                gla_value = str(row_data['total_gla']).replace(',', '').replace('$', '')
                shopping_center_data['total_gla'] = int(float(gla_value))
            except (ValueError, TypeError):
                self.warnings.append(f"Invalid GLA value: {row_data.get('total_gla')}")
        
        if row_data.get('year_built'):
            try:
                year_value = int(float(str(row_data['year_built'])))
                if 1800 <= year_value <= datetime.now().year + 5:
                    shopping_center_data['year_built'] = year_value
                else:
                    self.warnings.append(f"Invalid year built: {year_value}")
            except (ValueError, TypeError):
                self.warnings.append(f"Invalid year built: {row_data.get('year_built')}")
        
        return shopping_center_data
    
    def _extract_tenant_data(self, row_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract tenant data from row
        
        Args:
            row_data: Normalized row data
            
        Returns:
            Dictionary of tenant field data
        """
        tenant_data = {}
        
        # Extract basic tenant fields
        for field in ['tenant_name', 'suite_number', 'tenant_category', 'lease_status']:
            value = row_data.get(field)
            if value:
                tenant_data[field] = value
        
        # Handle numeric fields
        if row_data.get('suite_sqft'):
            try:
                sqft_value = str(row_data['suite_sqft']).replace(',', '').replace('$', '')
                tenant_data['suite_sqft'] = int(float(sqft_value))
            except (ValueError, TypeError):
                self.warnings.append(f"Invalid suite sqft: {row_data.get('suite_sqft')}")
        
        if row_data.get('rent_psf'):
            try:
                rent_value = str(row_data['rent_psf']).replace(',', '').replace('$', '')
                tenant_data['rent_psf'] = Decimal(rent_value)
            except (ValueError, TypeError, InvalidOperation):
                self.warnings.append(f"Invalid rent PSF: {row_data.get('rent_psf')}")
        
        return tenant_data
    
    def _get_or_create_shopping_center(self, data: Dict[str, Any]) -> Tuple[ShoppingCenter, bool]:
        """
        Get existing shopping center or create new one
        
        Args:
            data: Shopping center data
            
        Returns:
            Tuple of (ShoppingCenter instance, created boolean)
        """
        shopping_center_name = data['shopping_center_name']
        
        try:
            # Try to get existing shopping center
            shopping_center = ShoppingCenter.objects.get(
                shopping_center_name=shopping_center_name
            )
            return shopping_center, False
            
        except ShoppingCenter.DoesNotExist:
            # Create new shopping center
            shopping_center = ShoppingCenter.objects.create(**data)
            
            # Try to geocode the address
            if shopping_center.has_complete_address:
                try:
                    location = geocode_address(shopping_center.full_address)
                    if location:
                        shopping_center.geo_location = location
                        shopping_center.save()
                except Exception as e:
                    logger.warning(f"Geocoding failed for {shopping_center_name}: {str(e)}")
            
            return shopping_center, True
    
    def _update_shopping_center(self, shopping_center: ShoppingCenter, 
                               new_data: Dict[str, Any]) -> bool:
        """
        Update existing shopping center with new data (rolling CSV approach)
        
        Args:
            shopping_center: Existing ShoppingCenter instance
            new_data: New data to merge
            
        Returns:
            Boolean indicating if any updates were made
        """
        updated = False
        
        for field, value in new_data.items():
            if field == 'shopping_center_name':
                continue  # Don't update the unique identifier
                
            current_value = getattr(shopping_center, field, None)
            
            # Update if current value is empty or None
            if not current_value and value:
                setattr(shopping_center, field, value)
                updated = True
        
        if updated:
            shopping_center.save()
            
            # Re-attempt geocoding if address was updated
            if shopping_center.has_complete_address and not shopping_center.geo_location:
                try:
                    location = geocode_address(shopping_center.full_address)
                    if location:
                        shopping_center.geo_location = location
                        shopping_center.save()
                except Exception as e:
                    logger.warning(f"Geocoding failed: {str(e)}")
        
        return updated
    
    def _process_tenant_record(self, shopping_center: ShoppingCenter, 
                              tenant_data: Dict[str, Any]) -> None:
        """
        Process tenant record for shopping center
        
        Args:
            shopping_center: Parent ShoppingCenter instance
            tenant_data: Tenant data to process
        """
        tenant_data['shopping_center'] = shopping_center
        tenant_name = tenant_data['tenant_name']
        suite_number = tenant_data.get('suite_number', '')
        
        try:
            # Try to find existing tenant
            tenant, created = Tenant.objects.get_or_create(
                shopping_center=shopping_center,
                tenant_name=tenant_name,
                suite_number=suite_number,
                defaults=tenant_data
            )
            
            if created:
                self.created_count += 1
                logger.info(f"Created tenant: {tenant_name} at {shopping_center.shopping_center_name}")
            else:
                # Update tenant with new data
                updated = False
                for field, value in tenant_data.items():
                    if field not in ['shopping_center', 'tenant_name', 'suite_number']:
                        current_value = getattr(tenant, field, None)
                        if not current_value and value:
                            setattr(tenant, field, value)
                            updated = True
                
                if updated:
                    tenant.save()
                    self.updated_count += 1
                    logger.info(f"Updated tenant: {tenant_name}")
                    
        except Exception as e:
            self.errors.append(f"Failed to process tenant {tenant_name}: {str(e)}")
    
    def _calculate_import_quality(self) -> int:
        """
        Calculate quality score for the import batch
        
        Returns:
            Quality score (0-100)
        """
        try:
            # Get all shopping centers created/updated in this batch
            total_score = 0
            center_count = 0
            
            # This is a simplified quality calculation
            # In production, you'd use services.business_logic.calculate_quality_score
            
            if self.processed_count > 0:
                error_rate = len(self.errors) / self.processed_count
                warning_rate = len(self.warnings) / self.processed_count
                
                # Base score
                quality_score = 100
                
                # Deduct for errors and warnings
                quality_score -= (error_rate * 50)  # Errors are more serious
                quality_score -= (warning_rate * 20)  # Warnings are less serious
                
                # Ensure score is between 0 and 100
                quality_score = max(0, min(100, int(quality_score)))
                
            else:
                quality_score = 0
            
            return quality_score
            
        except Exception as e:
            logger.error(f"Quality calculation failed: {str(e)}")
            return 50  # Default middle score
    
    def _finalize_import_batch(self, quality_score: int) -> None:
        """
        Finalize import batch with results
        
        Args:
            quality_score: Calculated quality score
        """
        self.import_batch.status = 'completed' if len(self.errors) == 0 else 'completed_with_errors'
        self.import_batch.records_processed = self.processed_count
        self.import_batch.quality_score = quality_score
        self.import_batch.has_errors = len(self.errors) > 0
        
        if self.errors:
            self.import_batch.error_message = f"{len(self.errors)} errors occurred during processing"
        
        if self.warnings:
            validation_results = {
                'warnings': self.warnings[:10],  # Store first 10 warnings
                'warning_count': len(self.warnings)
            }
            self.import_batch.validation_results = validation_results
        
        self.import_batch.save()
        
        logger.info(f"Import batch {self.import_batch.batch_id} completed: "
                   f"{self.processed_count} processed, {self.created_count} created, "
                   f"{self.updated_count} updated, {len(self.errors)} errors")
    
    def _handle_processing_error(self, error_message: str) -> None:
        """
        Handle fatal processing error
        
        Args:
            error_message: Error message to record
        """
        self.import_batch.status = 'failed'
        self.import_batch.error_message = error_message
        self.import_batch.has_errors = True
        self.import_batch.save()
    
    def _generate_processing_results(self) -> Dict[str, Any]:
        """
        Generate processing results summary
        
        Returns:
            Dictionary with processing statistics
        """
        return {
            'batch_id': self.import_batch.batch_id,
            'status': self.import_batch.status,
            'records_processed': self.processed_count,
            'records_created': self.created_count,
            'records_updated': self.updated_count,
            'records_skipped': self.skipped_count,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'quality_score': self.import_batch.quality_score,
            'errors': self.errors[:5],  # Return first 5 errors
            'warnings': self.warnings[:5]  # Return first 5 warnings
        }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def process_csv_import(import_batch: ImportBatch, file_content: str) -> Dict[str, Any]:
    """
    Convenience function to process CSV import
    
    Args:
        import_batch: ImportBatch instance
        file_content: CSV file content as string
        
    Returns:
        Processing results dictionary
    """
    service = CSVImportService(import_batch)
    return service.process_csv_file(file_content)


def validate_csv_structure(file_content: str) -> Dict[str, Any]:
    """
    Validate CSV structure without processing data
    
    Args:
        file_content: CSV file content as string
        
    Returns:
        Validation results dictionary
    """
    try:
        csv_file = io.StringIO(file_content)
        reader = csv.DictReader(csv_file)
        
        headers = reader.fieldnames or []
        row_count = sum(1 for _ in reader)
        
        # Check for required headers
        required_headers = ['shopping_center_name']  # Minimum requirement
        found_headers = [h.lower().replace(' ', '_') for h in headers]
        
        missing_required = []
        for req_header in required_headers:
            if not any(req_header in possible for possible in 
                      CSVImportService.SHOPPING_CENTER_HEADERS.get(req_header, [])):
                missing_required.append(req_header)
        
        return {
            'valid': len(missing_required) == 0,
            'headers': headers,
            'row_count': row_count,
            'missing_required': missing_required,
            'message': 'CSV structure is valid' if len(missing_required) == 0 
                      else f'Missing required headers: {missing_required}'
        }
        
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'message': 'Failed to parse CSV structure'
        }


def create_sample_csv() -> str:
    """
    Create sample CSV content for testing and templates
    
    Returns:
        Sample CSV content as string
    """
    sample_data = [
        {
            'shopping_center_name': 'Westfield Valley Fair',
            'center_type': 'mall',
            'total_gla': '2100000',
            'address_street': '2855 Stevens Creek Blvd',
            'address_city': 'Santa Clara',
            'address_state': 'CA',
            'address_zip': '95050',
            'owner_name': 'Westfield Corporation',
            'property_manager': 'Westfield Management',
            'tenant_name': 'Apple Store',
            'suite_number': 'A101',
            'suite_sqft': '8500',
            'tenant_category': 'electronics',
            'rent_psf': '85.00',
            'lease_status': 'occupied'
        },
        {
            'shopping_center_name': 'Downtown Plaza',
            'center_type': 'strip_center',
            'total_gla': '45000',
            'address_street': '123 Main Street',
            'address_city': 'Sacramento',
            'address_state': 'CA',
            'address_zip': '95814',
            'owner_name': 'Local Development LLC',
            'property_manager': 'PMG Properties',
            'tenant_name': 'Starbucks Coffee',
            'suite_number': '105',
            'suite_sqft': '1200',
            'tenant_category': 'food_beverage',
            'rent_psf': '35.00',
            'lease_status': 'occupied'
        }
    ]
    
    # Create CSV string
    output = io.StringIO()
    if sample_data:
        writer = csv.DictWriter(output, fieldnames=sample_data[0].keys())
        writer.writeheader()
        writer.writerows(sample_data)
    
    return output.getvalue()
