#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shopwindow.settings')
django.setup()

from services.csv_import import CSVImportService

# Test with your CSV file
csv_path = 'masterdatabase.csv'

print("Starting CSV import test...")
print(f"CSV file: {csv_path}")
print("-" * 60)

importer = CSVImportService()
results = importer.import_csv(csv_path)

print("\n" + "=" * 60)
print("IMPORT RESULTS")
print("=" * 60)
print(f"Shopping Centers Created: {results['shopping_centers_created']}")
print(f"Shopping Centers Updated: {results['shopping_centers_updated']}")
print(f"Tenants Created: {results['tenants_created']}")
print(f"Tenants Updated: {results['tenants_updated']}")
print(f"Rows Processed: {results['rows_processed']}")
print(f"Rows Failed: {results['rows_failed']}")

if results['errors']:
    print(f"\nErrors ({len(results['errors'])}):")
    for error in results['errors'][:10]:  # Show first 10 errors
        print(f"  Row {error['row']}: {error['error']}")

if results['quality_flags']:
    print(f"\nQuality Flags ({len(results['quality_flags'])}):")
    for flag in results['quality_flags'][:10]:  # Show first 10 flags
        print(f"  Row {flag['row']}: {flag['flag']}")