"""
Diagnostic CSV import with detailed logging.

Usage:
    python manage.py import_csv_verbose masterdatabase.csv
"""

from django.core.management.base import BaseCommand
from imports.models import ImportBatch
from imports.services import CSVImportService
import csv
import io


class Command(BaseCommand):
    help = 'Import CSV with detailed diagnostic logging'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        self.stdout.write(self.style.SUCCESS("="*70))
        self.stdout.write(self.style.SUCCESS("DIAGNOSTIC CSV IMPORT"))
        self.stdout.write(self.style.SUCCESS("="*70))
        
        # Read CSV file
        self.stdout.write(f"\n1️⃣  Reading CSV file: {csv_file}")
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                file_content = f.read()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to read file: {str(e)}"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"✅ Read {len(file_content)} bytes"))
        
        # Detect delimiter
        self.stdout.write(f"\n2️⃣  Detecting CSV delimiter...")
        csv_file_io = io.StringIO(file_content)
        sample = file_content[:1024]
        sniffer = csv.Sniffer()
        detected_delimiter = sniffer.sniff(sample).delimiter
        self.stdout.write(self.style.SUCCESS(f"✅ Detected delimiter: '{detected_delimiter}' (ASCII {ord(detected_delimiter)})"))
        
        # Read headers
        self.stdout.write(f"\n3️⃣  Reading CSV headers...")
        csv_file_io.seek(0)
        reader = csv.DictReader(csv_file_io, delimiter=detected_delimiter)
        headers = reader.fieldnames
        
        self.stdout.write(self.style.SUCCESS(f"✅ Found {len(headers)} headers:"))
        for i, header in enumerate(headers, 1):
            cleaned = header.lower().strip().replace(' ', '_')
            self.stdout.write(f"   {i:2}. '{header}' → normalized: '{cleaned}'")
        
        # Create headers mapping (copy logic from CSVImportService)
        self.stdout.write(f"\n4️⃣  Creating headers mapping...")
        
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
        
        mapping = {}
        csv_headers_lower = [h.lower().strip().replace(' ', '_') for h in headers if h]
        
        for field, possible_headers in SHOPPING_CENTER_HEADERS.items():
            for csv_header in csv_headers_lower:
                if csv_header in possible_headers:
                    mapping[csv_header] = field
                    self.stdout.write(self.style.SUCCESS(f"   ✅ '{csv_header}' → '{field}'"))
                    break
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️  No match found for field '{field}'"))
        
        # Read first data row
        self.stdout.write(f"\n5️⃣  Reading first data row...")
        csv_file_io.seek(0)
        reader = csv.DictReader(csv_file_io, delimiter=detected_delimiter)
        first_row = next(reader)
        
        self.stdout.write(self.style.SUCCESS("✅ Raw first row (first 5 fields):"))
        for i, (key, value) in enumerate(list(first_row.items())[:5]):
            self.stdout.write(f"   '{key}': '{value}'")
        
        # Normalize first row
        self.stdout.write(f"\n6️⃣  Normalizing first row...")
        normalized = {}
        for csv_key, csv_value in first_row.items():
            if csv_key and csv_value:
                clean_key = csv_key.lower().strip().replace(' ', '_')
                clean_value = str(csv_value).strip()
                model_field = mapping.get(clean_key, clean_key)
                normalized[model_field] = clean_value
        
        self.stdout.write(self.style.SUCCESS("✅ Normalized first row (first 5 fields):"))
        for i, (key, value) in enumerate(list(normalized.items())[:5]):
            self.stdout.write(f"   '{key}': '{value}'")
        
        # Extract shopping center data
        self.stdout.write(f"\n7️⃣  Extracting shopping_center_name...")
        shopping_center_name = normalized.get('shopping_center_name')
        
        if shopping_center_name:
            self.stdout.write(self.style.SUCCESS(f"✅ Found: '{shopping_center_name}'"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ NOT FOUND!"))
            self.stdout.write(self.style.ERROR(f"   Normalized dict keys: {list(normalized.keys())[:10]}"))
            
            # Check if it's under a different key
            for key, value in normalized.items():
                if 'shopping' in key.lower() or 'center' in key.lower() or 'property' in key.lower():
                    self.stdout.write(self.style.WARNING(f"   Found similar key: '{key}' = '{value}'"))
        
        # Summary
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(self.style.SUCCESS("DIAGNOSTIC COMPLETE"))
        self.stdout.write(f"{'='*70}")
        
        if shopping_center_name:
            self.stdout.write(self.style.SUCCESS(f"\n✅ CSV appears valid - shopping_center_name found"))
            self.stdout.write(f"\nThe import SHOULD work. Issue is likely in CSVImportService logic.")
            self.stdout.write(f"Check imports/services.py _normalize_row_data() method.")
        else:
            self.stdout.write(self.style.ERROR(f"\n❌ shopping_center_name NOT found in normalized data"))
            self.stdout.write(f"\nThis explains why import is failing.")
            self.stdout.write(f"Issue is in header mapping or normalization logic.")