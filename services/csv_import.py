import csv
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
from datetime import datetime
from django.db import transaction
from properties.models import ShoppingCenter, Tenant


class CSVImportService:
    """
    Two-pass CSV import service for shopping centers and tenants.
    
    Pass 1: Import all shopping centers
    Pass 2: Import all tenants (with valid FK references)
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def import_csv(self, csv_file_path: str) -> Dict:
        """
        Main import method using two-pass approach.
        
        Args:
            csv_file_path: Path to CSV file
            
        Returns:
            Dictionary with import statistics
        """
        print(f"Starting CSV import from: {csv_file_path}")
        
        # Pass 1: Import shopping centers
        print("\n=== Pass 1: Importing Shopping Centers ===")
        shopping_centers = self._import_shopping_centers(csv_file_path)
        
        # Pass 2: Import tenants
        print("\n=== Pass 2: Importing Tenants ===")
        tenants_created = self._import_tenants(csv_file_path, shopping_centers)
        
        # Summary
        result = {
            'shopping_centers_created': len(shopping_centers),
            'tenants_created': tenants_created,
            'errors': self.errors,
            'warnings': self.warnings
        }
        
        print(f"\n=== Import Complete ===")
        print(f"Shopping Centers: {result['shopping_centers_created']}")
        print(f"Tenants Created: {result['tenants_created']}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        
        return result
    
    def _import_shopping_centers(self, csv_file_path: str) -> Dict[str, ShoppingCenter]:
        """
        Pass 1: Create all shopping centers and return a mapping.
        
        Returns:
            Dictionary mapping shopping_center_name -> ShoppingCenter instance
        """
        shopping_centers = {}
        row_num = 0
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    row_num += 1
                    
                    sc_name = row.get('shopping_center_name', '').strip()
                    if not sc_name:
                        continue
                    
                    # Skip if already processed
                    if sc_name in shopping_centers:
                        continue
                    
                    try:
                        # Create or retrieve shopping center
                        sc, created = ShoppingCenter.objects.get_or_create(
                            shopping_center_name=sc_name,
                            defaults=self._build_shopping_center_defaults(row)
                        )
                        
                        shopping_centers[sc_name] = sc
                        
                        if created:
                            print(f"  Created: {sc_name}")
                        else:
                            print(f"  Existing: {sc_name}")
                            
                    except Exception as e:
                        error_msg = f"Row {row_num}: Failed to create shopping center '{sc_name}': {str(e)}"
                        self.errors.append(error_msg)
                        print(f"  Error: {error_msg}")
        
        except FileNotFoundError:
            error_msg = f"CSV file not found: {csv_file_path}"
            self.errors.append(error_msg)
            print(f"Error: {error_msg}")
        except Exception as e:
            error_msg = f"Unexpected error reading CSV: {str(e)}"
            self.errors.append(error_msg)
            print(f"Error: {error_msg}")
        
        return shopping_centers
    
    def _import_tenants(self, csv_file_path: str, shopping_centers: Dict[str, ShoppingCenter]) -> int:
        """
        Pass 2: Create all tenants linked to shopping centers.
        
        Uses get_or_create with unique constraint on:
        shopping_center + tenant_name + tenant_suite_number
        
        This allows multiple vacant units per shopping center (different suites)
        while preventing duplicates on reimport.
        
        Args:
            csv_file_path: Path to CSV file
            shopping_centers: Dictionary of shopping center name -> instance
            
        Returns:
            Number of tenants created
        """
        tenants_created = 0
        row_num = 0
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    row_num += 1
                    
                    sc_name = row.get('shopping_center_name', '').strip()
                    tenant_name = row.get('tenant_name', '').strip()
                    
                    # Validation
                    if not sc_name or not tenant_name:
                        continue
                    
                    # Get shopping center from pass 1
                    shopping_center = shopping_centers.get(sc_name)
                    if not shopping_center:
                        warning_msg = f"Row {row_num}: Shopping center '{sc_name}' not found"
                        self.warnings.append(warning_msg)
                        continue
                    
                    try:
                        # Get suite number
                        tenant_suite_number = row.get('tenant_suite_number', '').strip() or None
                        
                        # Get or create tenant - uniform logic for all tenants (including Vacant)
                        # Unique constraint: shopping_center + tenant_name + tenant_suite_number
                        tenant, created = Tenant.objects.get_or_create(
                            shopping_center=shopping_center,
                            tenant_name=tenant_name,
                            tenant_suite_number=tenant_suite_number,
                            defaults=self._build_tenant_defaults(row)
                        )
                        
                        if created:
                            tenants_created += 1
                            if tenants_created <= 20 or tenants_created % 50 == 0:
                                print(f"  Created tenant: {tenant_name} at {sc_name}")
                        else:
                            if tenants_created <= 10:
                                print(f"  Existing tenant: {tenant_name} at {sc_name}")
                            
                    except Exception as e:
                        error_msg = f"Row {row_num}: Failed to create tenant '{tenant_name}': {str(e)}"
                        self.errors.append(error_msg)
                        print(f"  Error: {error_msg}")
        
        except FileNotFoundError:
            error_msg = f"CSV file not found: {csv_file_path}"
            self.errors.append(error_msg)
            print(f"Error: {error_msg}")
        except Exception as e:
            error_msg = f"Unexpected error reading CSV: {str(e)}"
            self.errors.append(error_msg)
            print(f"Error: {error_msg}")
        
        return tenants_created
    
    def _build_shopping_center_defaults(self, row: Dict) -> Dict:
        """
        Build defaults dictionary for ShoppingCenter creation.
        Maps CSV columns to Django model fields.
        """
        return {
            'address_street': row.get('address_street', '').strip() or None,
            'address_city': row.get('address_city', '').strip() or None,
            'address_state': row.get('address_state', '').strip() or None,
            'address_zip': self._clean_zip(row.get('address_zip')),
            'center_type': row.get('center_type', '').strip() or None,
            'county': row.get('county', '').strip() or None,
            'municipality': row.get('municipality', '').strip() or None,
            'zoning_authority': row.get('zoning_authority', '').strip() or None,
            'year_built': self._parse_year(row.get('year_built')),
            'owner': row.get('owner', '').strip() or None,
            'property_manager': row.get('property_manager', '').strip() or None,
            'leasing_agent': row.get('leasing_agent', '').strip() or None,
            'leasing_brokerage': row.get('leasing_brokerage', '').strip() or None,
            'total_gla': self._parse_int(row.get('total_gla')),
        }
    
    def _build_tenant_defaults(self, row: Dict) -> Dict:
        """
        Build defaults dictionary for Tenant creation.
        Maps CSV columns to Django model fields.
        """
        return {
            'square_footage': self._parse_int(row.get('square_footage')),
            'retail_category': row.get('retail_category', '').strip() or None,
            'ownership_type': row.get('ownership_type', '').strip() or None,
            'base_rent': self._parse_decimal(row.get('base_rent')),
            'lease_term': self._parse_int(row.get('lease_term')),
            'lease_commence': self._parse_date(row.get('lease_commence')),
            'lease_expiration': self._parse_date(row.get('lease_expiration')),
            'credit_category': row.get('credit_category', '').strip() or None,
        }
    
    # Parsing utility methods
    
    def _clean_zip(self, value: Optional[str]) -> Optional[str]:
        """Clean and format ZIP code."""
        if not value:
            return None
        try:
            # Handle float ZIP codes from CSV
            zip_str = str(value).strip().replace('.0', '')
            # Take first 5 digits if longer
            return zip_str[:5] if zip_str.isdigit() else None
        except:
            return None
    
    def _parse_number(self, value: Optional[str]) -> Optional[float]:
        """Parse string to float, handling empty values."""
        if not value or not str(value).strip():
            return None
        try:
            clean_value = str(value).strip().replace(',', '')
            # Skip if it's just a period or dash
            if clean_value in ('.', '-', ''):
                return None
            return float(clean_value)
        except (ValueError, AttributeError):
            return None
    
    def _parse_int(self, value: Optional[str]) -> Optional[int]:
        """Parse string to integer."""
        if not value or not str(value).strip():
            return None
        try:
            num = float(str(value).strip().replace(',', ''))
            return int(num)
        except (ValueError, AttributeError):
            return None
    
    def _parse_decimal(self, value: Optional[str]) -> Optional[Decimal]:
        """Parse string to Decimal for currency fields."""
        if not value or not str(value).strip():
            return None
        try:
            clean_value = str(value).strip().replace(',', '').replace('$', '')
            if clean_value in ('.', '-', ''):
                return None
            return Decimal(clean_value)
        except (InvalidOperation, ValueError, AttributeError):
            return None
    
    def _parse_year(self, value: Optional[str]) -> Optional[int]:
        """Parse year value."""
        year = self._parse_int(value)
        if year and 1800 <= year <= 2100:
            return year
        return None
    
    def _parse_date(self, value: Optional[str]) -> Optional[str]:
        """
        Parse date string for Django DateField.
        Returns ISO format string (YYYY-MM-DD) or None.
        """
        if not value or not str(value).strip():
            return None
        
        date_str = str(value).strip()
        
        # Skip obviously invalid dates
        if date_str in ('.', '-', '', 'nan', 'NaN'):
            return None
        
        # Try common date formats
        formats = [
            '%Y-%m-%d',  # ISO format
            '%m/%d/%Y',  # US format
            '%m/%d/%y',  # US format short year
            '%d/%m/%Y',  # European format
            '%Y%m%d',    # Compact format
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        # If all parsing fails, return None
        return None
    
    def _parse_boolean(self, value: Optional[str]) -> bool:
        """Parse boolean values."""
        if not value:
            return False
        value_lower = str(value).lower().strip()
        return value_lower in ('true', 'yes', '1', 't', 'y')


# Usage example for Django management command
def run_import(csv_path: str):
    """
    Helper function to run import from management command.
    
    Usage:
        from services.csv_import import run_import
        run_import('/path/to/masterdatabase.csv')
    """
    service = CSVImportService()
    result = service.import_csv(csv_path)
    
    if result['errors']:
        print("\n=== ERRORS ===")
        for error in result['errors']:
            print(f"  • {error}")
    
    if result['warnings']:
        print("\n=== WARNINGS ===")
        for warning in result['warnings']:
            print(f"  • {warning}")
    
    return result
