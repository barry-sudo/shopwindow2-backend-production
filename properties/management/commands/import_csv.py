"""
Simple CSV import management command using existing import system.

Usage:
    python manage.py import_csv /path/to/file.csv
    python manage.py import_csv /path/to/file.csv --clear
"""

from django.core.management.base import BaseCommand
from imports.models import ImportBatch
from imports.services import process_csv_import
from properties.models import ShoppingCenter, Tenant


class Command(BaseCommand):
    help = 'Import shopping centers and tenants from CSV file'

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
        
        # Clear existing data if requested
        if clear_data:
            self.stdout.write(self.style.WARNING("Clearing existing data..."))
            tenant_count = Tenant.objects.count()
            center_count = ShoppingCenter.objects.count()
            ShoppingCenter.objects.all().delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Deleted {tenant_count} tenants and {center_count} shopping centers"
                )
            )
        
        # Read CSV file
        self.stdout.write(f"Reading CSV file: {csv_file}")
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                file_content = f.read()
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ File not found: {csv_file}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to read file: {str(e)}"))
            return
        
        # Create import batch
        import_batch = ImportBatch.objects.create(
            file_name=csv_file.split('/')[-1],
            import_type='csv',
            status='pending',
            notes='Manual import via management command'
        )
        
        self.stdout.write(f"Created import batch: {import_batch.batch_id}")
        
        # Process CSV using existing service
        try:
            self.stdout.write("Processing CSV...")
            result = process_csv_import(import_batch, file_content)
            
            # Display results
            self.stdout.write("\n" + "="*60)
            self.stdout.write(self.style.SUCCESS("✅ Import Complete!"))
            self.stdout.write("="*60)
            self.stdout.write(f"Batch ID: {result['batch_id']}")
            self.stdout.write(f"Status: {result['status']}")
            self.stdout.write(f"Records Processed: {result['records_processed']}")
            self.stdout.write(f"Records Created: {result['records_created']}")
            self.stdout.write(f"Records Updated: {result['records_updated']}")
            self.stdout.write(f"Quality Score: {result['quality_score']}")
            
            if result['error_count'] > 0:
                self.stdout.write(self.style.WARNING(f"\n⚠️  Errors: {result['error_count']}"))
                for error in result['errors']:
                    self.stdout.write(f"  - {error}")
            
            if result['warning_count'] > 0:
                self.stdout.write(self.style.WARNING(f"\n⚠️  Warnings: {result['warning_count']}"))
                for warning in result['warnings']:
                    self.stdout.write(f"  - {warning}")
            
            self.stdout.write("="*60)
            
            # Verify major_group population
            self.stdout.write("\nVerifying major_group population...")
            total_tenants = Tenant.objects.count()
            tenants_with_major_group = Tenant.objects.exclude(major_group__isnull=True).count()
            
            self.stdout.write(f"Total tenants: {total_tenants}")
            self.stdout.write(f"Tenants with major_group: {tenants_with_major_group}")
            
            if tenants_with_major_group == total_tenants:
                self.stdout.write(self.style.SUCCESS("✅ All tenants have major_group populated!"))
            elif tenants_with_major_group > 0:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  {total_tenants - tenants_with_major_group} tenants missing major_group"
                ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Import failed: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
