"""
Django management command to populate major_group for all existing tenants.

This is a one-time data migration to backfill major_group values for tenants
that were imported before the field was added.

Usage:
    python manage.py populate_major_groups
    python manage.py populate_major_groups --dry-run  # Preview without saving
"""

from django.core.management.base import BaseCommand
from properties.models import Tenant, RETAIL_CATEGORY_TO_MAJOR_GROUP
from django.db import transaction


class Command(BaseCommand):
    help = 'Populate major_group for all tenants with retail_category'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.WARNING(
            f"\n{'DRY RUN MODE - No changes will be saved' if dry_run else 'LIVE MODE - Changes will be saved'}\n"
        ))
        
        # Find tenants with retail_category but no major_group
        tenants_to_update = Tenant.objects.exclude(
            retail_category__isnull=True
        ).exclude(
            retail_category=[]
        ).filter(
            major_group__isnull=True
        )
        
        total_count = tenants_to_update.count()
        self.stdout.write(f"Found {total_count} tenants to update\n")
        
        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No tenants need updating!"))
            return
        
        # Statistics tracking
        stats = {
            'updated': 0,
            'unmapped': 0,
            'errors': 0,
            'unmapped_categories': set(),
        }
        
        # Process in batches for better performance
        batch_size = 100
        
        with transaction.atomic():
            for tenant in tenants_to_update.iterator(chunk_size=batch_size):
                try:
                    # Get the retail category (handle both string and list)
                    if isinstance(tenant.retail_category, list) and len(tenant.retail_category) > 0:
                        primary_category = tenant.retail_category[0]
                    elif isinstance(tenant.retail_category, str):
                        primary_category = tenant.retail_category
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ⚠️  {tenant.tenant_name}: Invalid retail_category format: {tenant.retail_category}"
                            )
                        )
                        stats['errors'] += 1
                        continue
                    
                    # Map to major_group
                    major_group = RETAIL_CATEGORY_TO_MAJOR_GROUP.get(
                        primary_category,
                        'other_nonretail'  # Default fallback
                    )
                    
                    # Track unmapped categories
                    if primary_category not in RETAIL_CATEGORY_TO_MAJOR_GROUP:
                        stats['unmapped'] += 1
                        stats['unmapped_categories'].add(primary_category)
                    
                    # Update the tenant
                    tenant.major_group = major_group
                    
                    if not dry_run:
                        tenant.save(update_fields=['major_group'])
                    
                    stats['updated'] += 1
                    
                    # Show progress every 50 tenants
                    if stats['updated'] % 50 == 0:
                        self.stdout.write(f"  Processed {stats['updated']} tenants...")
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ❌ Error processing {tenant.tenant_name}: {str(e)}"
                        )
                    )
                    stats['errors'] += 1
            
            # Rollback if dry run
            if dry_run:
                transaction.set_rollback(True)
        
        # Print summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(f"✅ Updated: {stats['updated']} tenants"))
        
        if stats['unmapped'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  Unmapped categories: {stats['unmapped']} tenants (defaulted to 'Other / Non-Retail')"
                )
            )
            self.stdout.write("\nUnmapped retail_category values:")
            for cat in sorted(stats['unmapped_categories']):
                self.stdout.write(f"  - {cat}")
        
        if stats['errors'] > 0:
            self.stdout.write(self.style.ERROR(f"❌ Errors: {stats['errors']} tenants"))
        
        self.stdout.write("="*60 + "\n")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN COMPLETE - No changes saved. Run without --dry-run to apply changes."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("BULK UPDATE COMPLETE!"))
            
            # Verify results
            remaining = Tenant.objects.exclude(
                retail_category__isnull=True
            ).exclude(
                retail_category=[]
            ).filter(
                major_group__isnull=True
            ).count()
            
            if remaining == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        "✅ All tenants with retail_category now have major_group!"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  {remaining} tenants still missing major_group (may need manual review)"
                    )
                )
