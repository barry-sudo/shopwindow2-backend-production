from django.core.management.base import BaseCommand
import csv

class Command(BaseCommand):
    help = 'Debug CSV file headers'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        self.stdout.write(f"Reading CSV file: {csv_file}\n")
        
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                headers = next(reader)
                
                self.stdout.write(self.style.SUCCESS(f"Found {len(headers)} columns:\n"))
                
                for i, header in enumerate(headers, 1):
                    self.stdout.write(f"{i:3}. '{header}' (length: {len(header)}, bytes: {len(header.encode())})")
                    
                    if header != header.strip():
                        self.stdout.write(self.style.WARNING(f"     ⚠️  Has whitespace"))
                    if 'shopping' in header.lower():
                        self.stdout.write(self.style.SUCCESS(f"     ✅ Contains 'shopping'"))
                
                self.stdout.write(f"\n{self.style.SUCCESS('First data row:')}")
                first_row = next(reader)
                for header, value in zip(headers, first_row[:5]):
                    self.stdout.write(f"  {header}: {value}")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))