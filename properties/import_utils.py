"""
Reusable CSV import utilities for Shop Window.
Extracted from management command to support both CLI and web imports.

Philosophy: "Stocking Shelves" - Direct 1:1 field mapping, progressive enrichment.
"""

import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime
from io import StringIO
from django.db import transaction
from properties.models import ShoppingCenter, Tenant


def process_csv_import(csv_content, clear_existing=False):
    """
    Process CSV import from file content (string).
    
    Args:
        csv_content: String content of CSV file
        clear_existing: Boolean, whether to clear all data first
    
    Returns:
        Dictionary with import statistics:
        {
            'centers_created': int,
            'centers_updated': int,
            'tenants_created': int,
            'tenants_updated': int,
            'errors': list,
            'rows_processed': int
        }
    """
    stats = {
        'centers_created': 0,
        'centers_updated': 0,
        'tenants_created': 0,
        'tenants_updated': 0,
        'errors': [],
        'rows_processed': 0,
    }
    
    # Clear existing data if requested
    if clear_existing:
        tenant_count = Tenant.objects.count()
        center_count = ShoppingCenter.objects.count()
        ShoppingCenter.objects.all().delete()
        # Note: Tenants cascade delete automatically
    
    # Parse CSV
    csv_file = StringIO(csv_content)
    reader = csv.DictReader(csv_file)
    
    # Process each row in transaction
    with transaction.atomic():
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                _process_row(row, stats)
                stats['rows_processed'] += 1
            except Exception as e:
                error_msg = f"Row {row_num}: {str(e)}"
                stats['errors'].append(error_msg)
    
    return stats


def _process_row(row, stats):
    """
    Process a single CSV row - creates/updates shopping center and tenant.
    
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
        stats['centers_created'] += 1
    else:
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


def _process_tenant(shopping_center, row, stats):
    """
    Process tenant data - creates or updates tenant for shopping center.
    Direct 1:1 mapping from CSV to Tenant model.
    """
    
    tenant_name = row.get('tenant_name', '').strip()
    
    # Tenant data (direct mapping)
    tenant_data = {
        'shopping_center': shopping_center,
        'tenant_name': tenant_name,
        'tenant_suite_number': row.get('tenant_suite_number', '').strip() or None,
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
    
    # Handle date fields
    if row.get('lease_expiration'):
        try:
            # Try common date formats
            date_str = str(row['lease_expiration']).strip()
            if date_str:
                # Try parsing (add more formats as needed)
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']:
                    try:
                        tenant_data['lease_expiration'] = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
        except Exception:
            pass
    
    # Get or create tenant
    tenant, created = Tenant.objects.get_or_create(
        shopping_center=shopping_center,
        tenant_name=tenant_name,
        defaults=tenant_data
    )
    
    if created:
        stats['tenants_created'] += 1
    else:
        # Update empty fields only
        updated = False
        for field, value in tenant_data.items():
            if field not in ['shopping_center', 'tenant_name'] and value:
                current = getattr(tenant, field)
                if not current:
                    setattr(tenant, field, value)
                    updated = True
        
        if updated:
            tenant.save()
            stats['tenants_updated'] += 1


def calculate_fields_updated(stats):
    """
    Calculate total fields updated from stats.
    
    This is an approximation - estimates fields updated based on
    records created/updated.
    """
    # Rough estimate: 
    # - New center = ~10 fields
    # - Updated center = ~3 fields (average)
    # - New tenant = ~8 fields
    # - Updated tenant = ~2 fields (average)
    
    fields_updated = (
        (stats['centers_created'] * 10) +
        (stats['centers_updated'] * 3) +
        (stats['tenants_created'] * 8) +
        (stats['tenants_updated'] * 2)
    )
    
    return fields_updated
