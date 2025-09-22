"""
ASGI config for shopwindow project.

This module contains the ASGI application used by Django's development server
and any production ASGI deployments. It exposes a module-level variable
named ``application``.

ASGI (Asynchronous Server Gateway Interface) is the successor to WSGI and
provides support for both synchronous and asynchronous applications.

For Shop Window, ASGI enables:
- WebSocket support for real-time data updates
- Async view support for improved performance
- Future real-time features like live import progress
- Concurrent request handling

For production deployment, this can be used with:
- Daphne (Django Channels)
- Uvicorn
- Hypercorn
- Other ASGI servers
"""

import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Add the project directory to Python path
sys.path.append(str(BASE_DIR))

# Set the default settings module for the 'shopwindow' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shopwindow.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()


# =============================================================================
# ASGI APPLICATION CONFIGURATION
# =============================================================================

# For Sprint 1, we use standard Django ASGI without WebSockets
# Future sprints can extend this for real-time features
application = django_asgi_app


# =============================================================================
# FUTURE REAL-TIME FEATURES (Sprint 2+)
# =============================================================================

"""
Future ASGI Configuration for Real-Time Features:

When we implement real-time features in later sprints, this file can be
extended to support WebSockets and async capabilities:

```python
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

# Import WebSocket routing when implemented
# from shopwindow.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": get_asgi_application(),
    
    # WebSocket chat handler (future implementation)
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter([
                # WebSocket URL patterns will go here
                # path("ws/import-progress/", ImportProgressConsumer.as_asgi()),
                # path("ws/data-updates/", DataUpdateConsumer.as_asgi()),
            ])
        )
    ),
})
```

Potential Real-Time Features for Future Sprints:
================================================

1. **Import Progress Tracking (Sprint 2)**
   - Real-time CSV import progress updates
   - Live error reporting during data processing
   - WebSocket endpoint: ws/import-progress/{batch_id}/

2. **Data Quality Notifications (Sprint 3)**
   - Live notifications for data quality issues
   - Real-time validation feedback during manual entry
   - WebSocket endpoint: ws/quality-updates/

3. **Collaborative Editing (Sprint 4+)**
   - Multiple users editing property data simultaneously  
   - Real-time conflict resolution and merge notifications
   - WebSocket endpoint: ws/property-edit/{property_id}/

4. **Map Data Streaming (Sprint 3+)**
   - Real-time property updates on map interface
   - Live marker updates as data changes
   - WebSocket endpoint: ws/map-updates/

5. **Admin Dashboard Updates (Sprint 4+)**
   - Live statistics updates in admin interface
   - Real-time system health monitoring
   - WebSocket endpoint: ws/admin-updates/

Required Dependencies for Real-Time Features:
============================================

Add to requirements.txt when implementing:
- channels>=4.0.0
- channels-redis>=4.1.0  # For production WebSocket scaling
- daphne>=4.0.0  # ASGI server for WebSockets

Environment Configuration:
=========================

For real-time features, add to environment variables:
- REDIS_URL: For WebSocket scaling across multiple servers
- WEBSOCKET_ALLOWED_ORIGINS: Comma-separated list of allowed origins

Production Deployment with WebSockets:
=====================================

For Render deployment with WebSocket support:
1. Use Daphne instead of Gunicorn for ASGI serving
2. Configure Redis for channel layers
3. Update start command to: daphne shopwindow.asgi:application

Example render.yaml modification:
```yaml
services:
  - type: web
    name: shopwindow-backend
    env: python
    buildCommand: pip install -r requirements.txt && python manage.py migrate
    startCommand: daphne -b 0.0.0.0 -p $PORT shopwindow.asgi:application
    envVars:
      - key: REDIS_URL
        fromService:
          name: shopwindow-redis
          type: redis
          property: connectionString
```

Performance Considerations:
==========================

ASGI applications can handle both sync and async requests, but:
- Database queries are still synchronous (unless using async ORM)
- File uploads remain synchronous
- Heavy computations should use async task queues (Celery)
- WebSocket connections consume memory - monitor connection limits

Testing Real-Time Features:
===========================

When implementing WebSocket features:
- Use Django Channels testing utilities
- Test WebSocket connections and message handling
- Verify authentication and authorization for WebSocket consumers
- Load test WebSocket connections for scalability

Security Considerations:
=======================

For WebSocket implementations:
- Validate WebSocket origins (AllowedHostsOriginValidator)
- Implement proper authentication for WebSocket consumers
- Rate limit WebSocket messages to prevent abuse
- Sanitize all data sent through WebSocket channels
"""


# =============================================================================
# ASGI MIDDLEWARE AND UTILITIES
# =============================================================================

def get_asgi_application_with_monitoring():
    """
    ASGI application wrapper with monitoring and logging.
    
    Useful for production deployments where we need:
    - Request/response logging
    - Performance monitoring  
    - Error tracking
    - Health check endpoints
    """
    
    async def asgi_application_with_logging(scope, receive, send):
        """
        ASGI middleware for request logging and monitoring.
        
        This can be expanded for production monitoring needs.
        """
        
        # Log WebSocket connections when implemented
        if scope['type'] == 'websocket':
            print(f"WebSocket connection: {scope['path']}")
        
        # Call the Django ASGI application
        return await django_asgi_app(scope, receive, send)
    
    return asgi_application_with_logging


# =============================================================================
# DEVELOPMENT AND TESTING UTILITIES
# =============================================================================

def get_test_asgi_application():
    """
    ASGI application configured for testing.
    
    Returns a clean ASGI application for unit tests and integration tests.
    Useful for testing WebSocket functionality when implemented.
    """
    return django_asgi_app


# =============================================================================
# PRODUCTION CONFIGURATION NOTES
# =============================================================================

"""
Production ASGI Deployment Notes:
=================================

1. **Standard HTTP (Current Sprint 1)**
   - Use Gunicorn with WSGI (shopwindow.wsgi:application)
   - ASGI not required for basic REST API functionality
   - Keep this file for future WebSocket features

2. **ASGI Server Options (Future)**
   - Daphne: Django Channels official server
   - Uvicorn: Fast ASGI server (good for pure async Django)
   - Hypercorn: HTTP/2 and WebSocket support
   - Gunicorn with uvicorn workers: Hybrid approach

3. **Scaling WebSocket Connections**
   - Use Redis for channel layers in production
   - Configure connection limits and timeouts
   - Monitor memory usage for WebSocket connections
   - Consider connection pooling for high traffic

4. **Load Balancing with WebSockets**
   - Sticky sessions required for WebSocket connections
   - Use Redis channel layers for multi-server deployments
   - Configure load balancer for WebSocket upgrade headers

5. **Monitoring ASGI Applications**
   - Track WebSocket connection counts
   - Monitor channel layer performance (Redis)
   - Log WebSocket connection/disconnection events
   - Alert on WebSocket connection limits

Example Production Commands:
===========================

Development (HTTP only):
python manage.py runserver

Production WSGI (Current):
gunicorn shopwindow.wsgi:application

Production ASGI (Future):
daphne shopwindow.asgi:application

Production ASGI with workers (Future):
daphne -b 0.0.0.0 -p 8000 --workers 4 shopwindow.asgi:application

Health Checks for ASGI:
=======================

ASGI applications can include health checks at the ASGI level:
- HTTP health checks: /health/ endpoint (already implemented)
- WebSocket health checks: Test connection and immediate close
- Channel layer health checks: Test Redis connectivity

The current implementation focuses on HTTP functionality for Sprint 1,
with this file serving as the foundation for future real-time features.
"""
