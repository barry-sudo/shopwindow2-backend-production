#!/usr/bin/env bash
# Shop Window Backend - Render Build Script
# This script runs during deployment on Render
# Updated for shopwindow.cloud production deployment

set -o errexit  # Exit on error

echo "🔧 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🗄️  Running database migrations..."
python manage.py migrate --noinput

echo "📦 Collecting static files..."
python manage.py collectstatic --noinput

echo "✅ Build complete! Backend ready for deployment."
