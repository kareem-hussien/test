"""
Context processors for Travian Whispers web application.
This module provides template context processors for the Flask application.
"""
import logging
from datetime import datetime, date
from flask import current_app, g

# Initialize logger
logger = logging.getLogger(__name__)

def register_context_processors(app):
    """
    Register template context processors with the application.
    
    Args:
        app: Flask application instance
    """
    # Current year processor for copyright notices
    @app.context_processor
    def inject_current_year():
        return {'current_year': date.today().year}
    
    # Application version processor
    @app.context_processor
    def inject_app_version():
        version = current_app.config.get('APP_VERSION', '1.0.0')
        return {'app_version': version}
    
    # Maintenance mode status processor
    @app.context_processor
    def inject_maintenance_mode():
        return {
            'maintenance_mode': getattr(g, 'maintenance_mode', False),
            'maintenance_message': current_app.config.get('MAINTENANCE_MESSAGE', ''),
            'maintenance_until': current_app.config.get('MAINTENANCE_UNTIL')
        }
    
    logger.info("Context processors registered")
