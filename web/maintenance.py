"""
Maintenance mode middleware for Travian Whispers web application.
This module provides middleware to show a maintenance page when maintenance mode is enabled.
"""
import logging
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, request, current_app

# Initialize logger
logger = logging.getLogger(__name__)

def register_maintenance_middleware(app):
    """
    Register maintenance middleware with the Flask application.
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def maintenance_mode_middleware():
        """Check if maintenance mode is enabled and show maintenance page if it is."""
        # Skip middleware for static files
        if request.path.startswith('/static'):
            return None
            
        # Get maintenance status
        enabled = current_app.config.get('MAINTENANCE_MODE', False)
        
        # Check if maintenance period has expired
        if enabled:
            until = current_app.config.get('MAINTENANCE_UNTIL')
            
            # Auto-disable if maintenance period has ended
            if until and datetime.utcnow() > until:
                logger.info("Maintenance mode auto-disabled because scheduled end time has passed")
                current_app.config['MAINTENANCE_MODE'] = False
                enabled = False
                
        if enabled:
            # Get maintenance message
            message = current_app.config.get('MAINTENANCE_MESSAGE', 
                'We are currently performing scheduled maintenance. Please check back later.')
            
            # Get maintenance end time
            until = current_app.config.get('MAINTENANCE_UNTIL', None)
            
            # Format until time for display if it exists
            until_display = until.strftime('%Y-%m-%d %H:%M:%S UTC') if until else None
            
            # Calculate remaining time if until exists
            remaining = None
            if until:
                time_diff = until - datetime.utcnow()
                # Only calculate if still in the future
                if time_diff.total_seconds() > 0:
                    hours, remainder = divmod(time_diff.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    remaining = {
                        'hours': int(hours),
                        'minutes': int(minutes),
                        'seconds': int(seconds),
                        'total_seconds': int(time_diff.total_seconds())
                    }
            
            # Skip for admin users
            if is_admin_user():
                return None
                
            # Allow logout functionality to work even in maintenance mode
            if request.path == url_for('auth.logout'):
                return None
                
            # Show maintenance page
            return render_template('errors/maintenance.html', 
                                  message=message,
                                  until=until_display,
                                  remaining=remaining), 503
        
        return None

def enable_maintenance_mode(app, message=None, duration_hours=None):
    """
    Enable maintenance mode.
    
    Args:
        app: Flask application instance
        message (str, optional): Maintenance message
        duration_hours (float, optional): Maintenance duration in hours
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Set maintenance mode
        app.config['MAINTENANCE_MODE'] = True
        
        # Set maintenance message if provided
        if message:
            app.config['MAINTENANCE_MESSAGE'] = message
        
        # Set end time if duration provided
        if duration_hours:
            end_time = datetime.utcnow() + timedelta(hours=duration_hours)
            app.config['MAINTENANCE_UNTIL'] = end_time
        else:
            app.config['MAINTENANCE_UNTIL'] = None
        
        logger.info(f"Maintenance mode enabled. Duration: {duration_hours} hours" if duration_hours else "Maintenance mode enabled indefinitely")
        return True
    except Exception as e:
        logger.error(f"Failed to enable maintenance mode: {e}")
        return False

def disable_maintenance_mode(app):
    """
    Disable maintenance mode.
    
    Args:
        app: Flask application instance
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Disable maintenance mode
        app.config['MAINTENANCE_MODE'] = False
        app.config['MAINTENANCE_UNTIL'] = None
        
        logger.info("Maintenance mode disabled manually")
        return True
    except Exception as e:
        logger.error(f"Failed to disable maintenance mode: {e}")
        return False

def get_maintenance_status(app):
    """
    Get maintenance mode status.
    
    Args:
        app: Flask application instance
        
    Returns:
        dict: Maintenance status
    """
    enabled = app.config.get('MAINTENANCE_MODE', False)
    until = app.config.get('MAINTENANCE_UNTIL', None)
    
    # Auto-disable if maintenance period has ended
    if enabled and until and datetime.utcnow() > until:
        app.config['MAINTENANCE_MODE'] = False
        enabled = False
    
    return {
        'enabled': enabled,
        'message': app.config.get('MAINTENANCE_MESSAGE', ''),
        'until': until
    }

def is_admin_user():
    """
    Check if the current user is an admin.
    
    Returns:
        bool: True if user is admin, False otherwise
    """
    from flask import session
    
    # Check if user is logged in and has admin role
    if 'user_id' in session and 'role' in session:
        role = session.get('role')
        return role == 'admin'
    
    return False
