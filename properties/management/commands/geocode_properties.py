# properties/management/commands/geocode_properties.py
"""
Django management command to geocode all shopping centers.

Usage:
    python manage.py geocode_properties
    python manage.py geocode_properties --force  # Re-geocode all properties
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from properties.models import ShoppingCenter
from services.geocoding import geocoding_service


class Command(BaseCommand):
    help = 'Geocode shopping center addresses and populate latitude/longitude fields'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-geocode all properties, even if they already have coordinates',
        )
        
        parser.add_argument(
            '--id',
            type=int,
            help='Geocode a specific property by ID',
        )
        
        parser.add_argument(
            '--delay',
            type=float,
            default=0.2,
            help='Delay between geocoding requests in seconds (default: 0.2)',
        )

    def handle(self, *args, **options):
        force = options['force']
        property_id = options['id']
        delay = options['delay']
        
        # Build queryset
        if property_id:
            # Geocode specific property
            queryset = ShoppingCenter.objects.filter(id=property_id)
            if not queryset.exists():
                self.stdout.write(self.style.ERROR(f'Property with ID {property_id} not found'))
                return
        elif force:
            # Re-geocode all properties
            queryset = ShoppingCenter.objects.all()
            self.stdout.write(self.style.WARNING('Force mode: Re-geocoding ALL properties'))
        else:
            # Geocode only properties without coordinates
            queryset = ShoppingCenter.objects.filter(
                Q(latitude__isnull=True) | Q(longitude__isnull=True)
            )
        
        total = queryset.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('✓ All properties already have coordinates'))
            return
        
        self.stdout.write(f'Found {total} properties to geocode')
        self.stdout.write(f'Using delay of {delay} seconds between requests')
        self.stdout.write('Starting geocoding...\n')
        
        # Batch geocode
        results = geocoding_service.batch_geocode_shopping_centers(queryset, delay=delay)
        
        # Display results
        self.stdout.write('\n' + '='*60)
        self.stdout.write('GEOCODING COMPLETE')
        self.stdout.write('='*60)
        self.stdout.write(f'Total properties:     {results["total"]}')
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully geocoded: {results["success"]}'))
        self.stdout.write(self.style.WARNING(f'⊘ Already had coords:   {results["skipped"]}'))
        
        if results['failed'] > 0:
            self.stdout.write(self.style.ERROR(f'✗ Failed:              {results["failed"]}'))
            if results['failed_ids']:
                self.stdout.write(f'\nFailed property IDs: {", ".join(map(str, results["failed_ids"]))}')
        
        self.stdout.write('='*60 + '\n')
        
        # Calculate success rate
        if results['success'] + results['failed'] > 0:
            success_rate = (results['success'] / (results['success'] + results['failed'])) * 100
            self.stdout.write(f'Success rate: {success_rate:.1f}%')
