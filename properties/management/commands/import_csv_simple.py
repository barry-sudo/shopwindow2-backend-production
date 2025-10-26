"""
Simple CSV import - Stocking Shelves philosophy.
CSV headers must match model fields EXACTLY. No mapping, no variations, no magic.

Usage:
    # As management command:
    python manage.py import_csv_simple masterdatabase.csv
    python manage.py import_csv_simple masterdatabase.csv --clear
    
    # As callable function (for web endpoints):
    from properties.management.commands.import_csv_simple import run_import
    stats = run_import('path/to/file.csv', clear_data=False)
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from properties.models import ShoppingCenter, Tenant
from services.geocoding import geocoding_service
import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime
import os


def run_import(csv_path: str, clear_data: bool = False) -> dict:
    """
    Core CSV import logic - callable from management command or web endpoint.
    
    Args:
        csv_path: Path to CSV file to import
        clear_data: If True, clear all existing data before import
    
    Returns:
        dict with import statistics:
        {
            'success': bool,
            'centers_created': int,
            'centers_updated': int,
            'geocoding_success': int,
            'geocoding_failed': int,
            'tenants_created': int,
            'tenants_updated': int,
            'rows_processed': int,
            'errors': list[str],
            'error_message': str (only if success=False)
        }
    
    Raises:
        ValueError: If Google Maps API key not found
        FileNotFoundError: If CSV file doesn't exist
    """
    
    # CRITICAL: Check for Google Maps API key before starting import
    if not os.environ.get('GOOGLE_MAPS_API_KEY'):
        raise ValueError(
            "GOOGLE_MAPS_API_KEY not found in environment. "
            "Geocoding is required for this map-centric application. "
            "Please set GOOGLE_MAPS_API_KEY in your .env file before importing."
        )
    
    # Check file exists
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    # Initialize stats
    stats = {
        'success': False,
        'centers_created': 0,
        'centers_updated': 0,
        'geocoding_success': 0,
        'geocoding_failed': 0,
        'tenants_created': 0,
        'tenants_updated': 0,
        'errors': [],
        'rows_processed': 0,
    }
    
    try:
        # Clear existing data if requested
        if clear_data:
            tenant_count = Tenant.objects.count()
            center_count = ShoppingCenter.objects.count()
            ShoppingCenter.objects.all().delete()
            print(f"Cleared {tenant_count} tenants and {center_count} shopping centers")
        
        # Read and process CSV
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            # Process each row
            with transaction.atomic():
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    try:
                        _process_row(row, stats)
                        stats['rows_processed'] += 1
                        
                        # Progress indicator
                        if stats['rows_processed'] % 100 == 0:
                            print(f"Processed {stats['rows_processed']} rows...")
                    
                    except Exception as e:
                        error_msg = f"Row {row_num}: {str(e)}"
                        stats['errors'].append(error_msg)
                        if len(stats['errors']) <= 5:  # Only log first 5
                            print(f"Warning: {error_msg}")
        
        # Mark as successful
        stats['success'] = True
        
    except Exception as e:
        stats['success'] = False
        stats['error_message'] = str(e)
        print(f"Import failed: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return stats


def _process_row(row: dict, stats: dict):
    """
    Process a single CSV row.
    
    Philosophy: CSV columns map DIRECTLY to model fields.
    No transformations, no magic, no variations.
    """
    
    # Get or create shopping center (by name)
    shopping_center_name = row.get('shopping_center_name', '').strip()
    
    if not shopping_center_name:
        raise ValueError("shopping_center_name is required")
    
    # Extract shopping center fields (direct mapping)
    center_data = {
        'shopping_center_name': shopping_center_name,
        'center_type': row.get('center_type', '').strip() or None,
        'address_street': row.get('address_street', '').strip() or None,
        'address_city': row.get('address_city', '').strip() or None,
        'address_state': row.get('address_state', '').strip() or None,
        'address_zip': row.get('address_zip', '').strip() or None,
        'county': row.get('county', '').strip() or None,
        'municipality': row.get('municipality', '').strip() or None,
        'owner': row.get('owner', '').strip() or None,
        'property_manager': row.get('property_manager', '').strip() or None,
    }
    
    # Handle numeric fields
    if row.get('total_gla'):
        try:
            center_data['total_gla'] = int(float(str(row['total_gla']).replace(',', '')))
        except (ValueError, TypeError):
            pass
    
    if row.get('year_built'):
        try:
            year = int(float(str(row['year_built'])))
            if 1800 <= year <= datetime.now().year + 5:
                center_data['year_built'] = year
        except (ValueError, TypeError):
            pass
    
    # Get or create shopping center
    shopping_center, created = ShoppingCenter.objects.get_or_create(
        shopping_center_name=shopping_center_name,
        defaults=center_data
    )
    
    if created:
        # NEW SHOPPING CENTER - Must geocode immediately
        geocoding_success = geocoding_service.geocode_shopping_center(shopping_center)
        
        if not geocoding_success:
            # GEOCODING FAILED - Delete the shopping center and raise error
            shopping_center.delete()
            stats['geocoding_failed'] += 1
            raise ValueError(f"Failed to geocode {shopping_center_name}")
        
        # Geocoding succeeded
        stats['centers_created'] += 1
        stats['geocoding_success'] += 1
    else:
        # EXISTING CENTER - Skip geocoding (one and done)
        # Update empty fields only (rolling CSV approach)
        updated = False
        for field, value in center_data.items():
            if field != 'shopping_center_name' and value:
                current = getattr(shopping_center, field)
                if not current:
                    setattr(shopping_center, field, value)
                    updated = True
        
        if updated:
            shopping_center.save()
            stats['centers_updated'] += 1
    
    # Process tenant if present
    tenant_name = row.get('tenant_name', '').strip()
    
    if tenant_name:
        _process_tenant(shopping_center, row, stats)


def _process_tenant(shopping_center, row: dict, stats: dict):
    """
    Process tenant data.
    Direct 1:1 mapping from CSV to Tenant model.
    
    Uses get_or_create with unique constraint on:
    shopping_center + tenant_name + tenant_suite_number
    
    This allows multiple vacant units per shopping center (different suites)
    while preventing duplicates on reimport.
    """
    
    tenant_name = row.get('tenant_name', '').strip()
    tenant_suite_number = row.get('tenant_suite_number', '').strip() or None
    
    # Tenant data (direct mapping)
    tenant_data = {
        'retail_category': row.get('retail_category', '').strip() or None,
        # major_group auto-populated by model's save() method
    }
    
    # Handle numeric fields
    if row.get('square_footage'):
        try:
            tenant_data['square_footage'] = int(float(str(row['square_footage']).replace(',', '')))
        except (ValueError, TypeError):
            pass
    
    if row.get('base_rent'):
        try:
            tenant_data['base_rent'] = Decimal(str(row['base_rent']).replace(',', '').replace('$', ''))
        except (ValueError, TypeError, InvalidOperation):
            pass
    
    if row.get('lease_term'):
        try:
            tenant_data['lease_term'] = int(float(str(row['lease_term'])))
        except (ValueError, TypeError):
            pass
    
    # Handle date fields - LEASE COMMENCE
    if row.get('lease_commence'):
        try:
            date_str = str(row['lease_commence']).strip()
            if date_str:
                # Try parsing multiple date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']:
                    try:
                        tenant_data['lease_commence'] = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
        except Exception:
            pass
    
    # Handle date fields - LEASE EXPIRATION
    if row.get('lease_expiration'):
        try:
            date_str = str(row['lease_expiration']).strip()
            if date_str:
                # Try parsing multiple date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']:
                    try:
                        tenant_data['lease_expiration'] = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
        except Exception:
            pass
    
    # Get or create tenant - uniform logic for all tenants (including Vacant)
    # Unique constraint: shopping_center + tenant_name + tenant_suite_number
    tenant, created = Tenant.objects.get_or_create(
        shopping_center=shopping_center,
        tenant_name=tenant_name,
        tenant_suite_number=tenant_suite_number,
        defaults=tenant_data
    )
    
    if created:
        stats['tenants_created'] += 1
    else:
        # Update empty fields only (progressive enrichment)
        updated = False
        for field, value in tenant_data.items():
            if value:
                current = getattr(tenant, field)
                if not current:
                    setattr(tenant, field, value)
                    updated = True
        
        if updated:
            tenant.save()
            stats['tenants_updated'] += 1


class Command(BaseCommand):
    """Django management command wrapper for run_import()"""
    
    help = 'Import CSV with direct 1:1 field mapping (Stocking Shelves)'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing data before import',
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        clear_data = options['clear']
        
        self.stdout.write(f"\nReading CSV: {csv_file}")
        
        try:
            # Call the extracted function
            stats = run_import(csv_file, clear_data)
            
            # Print summary
            self._print_summary(stats)
            
        except ValueError as e:
            # API key or validation errors
            self.stdout.write(
                self.style.ERROR(f"\n❌ CRITICAL ERROR: {str(e)}\n")
            )
        except FileNotFoundError as e:
            self.stdout.write(
                self.style.ERROR(f"\n❌ FILE ERROR: {str(e)}\n")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Import failed: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
    
    def _print_summary(self, stats):
        """Print import summary."""
        self.stdout.write("\n" + "="*70)
        
        if stats['success']:
            self.stdout.write(self.style.SUCCESS("✅ IMPORT COMPLETE"))
        else:
            self.stdout.write(self.style.ERROR("❌ IMPORT FAILED"))
            if 'error_message' in stats:
                self.stdout.write(self.style.ERROR(f"Error: {stats['error_message']}"))
        
        self.stdout.write("="*70)
        self.stdout.write(f"Rows Processed: {stats['rows_processed']}")
        self.stdout.write(f"Shopping Centers Created: {stats['centers_created']}")
        self.stdout.write(f"Shopping Centers Updated: {stats['centers_updated']}")
        
        # Geocoding results
        if stats['geocoding_success'] > 0 or stats['geocoding_failed'] > 0:
            self.stdout.write(f"\nGeocoding Results:")
            self.stdout.write(self.style.SUCCESS(f"  ✓ Successfully geocoded: {stats['geocoding_success']}"))
            if stats['geocoding_failed'] > 0:
                self.stdout.write(self.style.ERROR(f"  ✗ Failed geocoding: {stats['geocoding_failed']}"))
        
        self.stdout.write(f"\nTenants Created: {stats['tenants_created']}")
        self.stdout.write(f"Tenants Updated: {stats['tenants_updated']}")
        
        if stats['errors']:
            self.stdout.write(f"\n⚠️  Errors: {len(stats['errors'])}")
            for error in stats['errors'][:5]:
                self.stdout.write(f"  - {error}")
            if len(stats['errors']) > 5:
                self.stdout.write(f"  ... and {len(stats['errors']) - 5} more")
        
        # Verify major_group population
        self.stdout.write("\n" + "="*70)
        self.stdout.write("Verifying major_group population...")
        
        from django.db.models import Count
        from properties.models import Tenant
        
        total_tenants = Tenant.objects.count()
        with_major_group = Tenant.objects.exclude(major_group__isnull=True).count()
        
        self.stdout.write(f"Total tenants: {total_tenants}")
        self.stdout.write(f"Tenants with major_group: {with_major_group}")
        
        if total_tenants > 0:
            percentage = (with_major_group / total_tenants) * 100
            self.stdout.write(f"Success rate: {percentage:.1f}%")
            
            if percentage == 100:
                self.stdout.write(self.style.SUCCESS("✅ All tenants have major_group!"))
            else:
                self.stdout.write(self.style.WARNING(f"⚠️  {total_tenants - with_major_group} tenants missing major_group"))
        
        # Show breakdown
        breakdown = Tenant.objects.values('major_group').annotate(count=Count('id')).order_by('-count')
        if breakdown:
            self.stdout.write("\nTenant Mix Breakdown:")
            for group in breakdown:
                if group['major_group']:
                    self.stdout.write(f"  {group['major_group']}: {group['count']} tenants")
                else:
                    self.stdout.write(f"  (no major_group): {group['count']} tenants")
        
        self.stdout.write("="*70)
