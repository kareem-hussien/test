"""
Maintenance mode middleware for Travian Whispers web application.
This middleware checks if the site is in maintenance mode and redirects
non-admin users to a maintenance page.
"""
import logging
from functools import wraps
from flask import redirect, request, flash, url_for, session, current_app, render_template

# Initialize logger
logger = logging.getLogger(__name__)

def maintenance_middleware():
    """
    Middleware function to check if the application is in maintenance mode.
    If it is, and the current user is not an admin, redirect to the maintenance page.
    
    Returns:
        function: The middleware function
    """
    def middleware(view_func):
        @wraps(view_func)
        def decorated_function(*args, **kwargs):
            # Skip maintenance check for admin routes and login route
            if request.path.startswith('/admin') or request.path == '/auth/login':
                return view_func(*args, **kwargs)
            
            # Skip maintenance check for static files
            if request.path.startswith('/static'):
                return view_func(*args, **kwargs)
            
            # Check if maintenance mode is enabled
            maintenance_mode = current_app.config.get('MAINTENANCE_MODE', False)
            
            if maintenance_mode:
                # Check if user is admin
                user_id = session.get('user_id')
                user_role = session.get('role')
                
                # Allow admins to bypass maintenance mode
                if user_id and user_role == 'admin':
                    # Add a flash message for admins viewing the site in maintenance mode
                    flash('The site is currently in maintenance mode. Only administrators can access it.', 'warning')
                    return view_func(*args, **kwargs)
                
                # Get maintenance message
                maintenance_message = current_app.config.get(
                    'MAINTENANCE_MESSAGE', 
                    'We are currently performing scheduled maintenance. Please check back later.'
                )
                
                # Render maintenance page
                return render_template('maintenance.html', message=maintenance_message)
            
            return view_func(*args, **kwargs)
        return decorated_function
    return middleware


def register_maintenance_middleware(app):
    """
    Register the maintenance middleware with the Flask application.
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def check_maintenance():
        # Skip maintenance check for admin routes and login route
        if request.path.startswith('/admin') or request.path == '/auth/login':
            return None
        
        # Skip maintenance check for static files
        if request.path.startswith('/static'):
            return None
        
        # Check if maintenance mode is enabled
        maintenance_mode = app.config.get('MAINTENANCE_MODE', False)
        
        if maintenance_mode:
            # Check if user is admin
            user_id = session.get('user_id')
            user_role = session.get('role')
            
            # Allow admins to bypass maintenance mode
            if user_id and user_role == 'admin':
                # Add a flash message for admins viewing the site in maintenance mode
                flash('The site is currently in maintenance mode. Only administrators can access it.', 'warning')
                return None
            
            # Get maintenance message
            maintenance_message = app.config.get(
                'MAINTENANCE_MESSAGE', 
                'We are currently performing scheduled maintenance. Please check back later.'
            )
            
            # Render maintenance page
            return render_template('maintenance.html', message=maintenance_message)
        
        return None
