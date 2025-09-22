#!/usr/bin/env python
"""
Django's command-line utility for administrative tasks.

Shop Window Backend Management Script
=====================================

This script is the entry point for all Django administrative tasks including:
- Running the development server
- Database migrations
- Creating superusers
- Loading sample data
- Running tests
- Collecting static files
- Custom management commands

Usage Examples:
===============

Development:
  python manage.py runserver                    # Start development server
  python manage.py runserver 0.0.0.0:8000     # Start server on all interfaces

Database Operations:
  python manage.py makemigrations              # Create new migrations
  python manage.py migrate                     # Apply migrations
  python manage.py showmigrations              # Show migration status
  python manage.py sqlmigrate properties 0001 # Show SQL for migration

User Management:
  python manage.py createsuperuser            # Create admin user
  python manage.py changepassword username    # Change user password

Data Management:
  python manage.py load_sample_data sample_data.xlsx  # Load sample property data
  python manage.py loaddata fixture.json      # Load fixture data
  python manage.py dumpdata > backup.json     # Export data

Development Tools:
  python manage.py shell                       # Interactive Python shell
  python manage.py dbshell                    # Database shell
  python manage.py check                      # System check
  python manage.py test                       # Run tests

Production:
  python manage.py collectstatic --noinput    # Collect static files
  python manage.py compress                   # Compress static files

Shop Window Specific Commands:
  python manage.py load_sample_data <file>    # Load shopping center data
  python manage.py geocode_centers            # Geocode missing coordinates
  python manage.py import_csv <file>          # Import CSV property data
  python manage.py quality_report             # Generate data quality report
"""

import os
import sys


def main():
    """Run administrative tasks."""
    
    # Set the default Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shopwindow.settings')
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Enhanced error message with troubleshooting steps
        error_msg = (
            "Couldn't import Django. This usually means:\n"
            "  1. Django is not installed - run: pip install django\n"
            "  2. Virtual environment is not activated\n"
            "  3. PYTHONPATH is not set correctly\n"
            "  4. You're in the wrong directory\n\n"
            f"Current Python path: {sys.executable}\n"
            f"Current working directory: {os.getcwd()}\n"
            f"DJANGO_SETTINGS_MODULE: {os.environ.get('DJANGO_SETTINGS_MODULE', 'Not set')}\n\n"
            "Try:\n"
            "  - Activating your virtual environment\n"
            "  - Running: pip install -r requirements.txt\n"
            "  - Verifying you're in the project root directory\n"
        )
        raise ImportError(error_msg) from exc
    
    try:
        # Execute the command line arguments
        execute_from_command_line(sys.argv)
    except Exception as exc:
        # Catch any other runtime errors and provide helpful context
        print(f"\nError executing Django command: {exc}", file=sys.stderr)
        print(f"Command attempted: {' '.join(sys.argv)}", file=sys.stderr)
        print(f"Python version: {sys.version}", file=sys.stderr)
        print(f"Working directory: {os.getcwd()}", file=sys.stderr)
        raise


if __name__ == '__main__':
    main()