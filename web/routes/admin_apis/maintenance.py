"""
Updated admin maintenance routes for Travian Whispers web application.
This version properly implements maintenance mode toggling.
"""
import logging
from datetime import datetime, timedelta
from flask import (
    render_template, request, redirect, 
    url_for, flash, session, current_app, jsonify
)

from web.utils.decorators import admin_required
from database.models.user import User
from web.maintenance import enable_maintenance_mode, disable_maintenance_mode, get_maintenance_status
from database.models.system_log import SystemLog

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(admin_bp):
    """Register maintenance routes with the admin blueprint."""
    # Attach routes to the blueprint
    admin_bp.route('/maintenance')(admin_required(maintenance))
    admin_bp.route('/update-maintenance', methods=['POST'])(admin_required(update_maintenance))
    admin_bp.route('/generate-report', methods=['POST'])(admin_required(generate_report))

def maintenance():
    """System maintenance page."""
    # Get current user for the template
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Get maintenance status
    maintenance_status = get_maintenance_status(current_app)
    
    # Mock system stats with actual maintenance mode status
    system_stats = {
        'uptime': '24d 12h 36m',
        'memory_usage': 62,
        'cpu_usage': 35,
        'disk_usage': 48,
        'active_connections': 18,
        'maintenance_mode': maintenance_status['enabled'],
        'maintenance_message': maintenance_status['message'],
        'maintenance_until': maintenance_status['until'].strftime('%Y-%m-%d %H:%M') if maintenance_status['until'] else None,
        'status': 'Maintenance' if maintenance_status['enabled'] else 'Healthy'
    }
    
    # Database stats
    db_stats = {
        'total_collections': 7,
        'total_documents': 15425,
        'total_size': '48.6 MB',
        'avg_document_size': '3.25 KB',
        'indexes': 18,
        'indexes_size': '12.8 MB'
    }
    
    # Get system logs related to maintenance
    system_log = SystemLog()
    maintenance_logs = system_log.get_logs_by_category('Maintenance', limit=10)
    
    # Format logs if needed
    formatted_logs = []
    for log in maintenance_logs:
        formatted_logs.append({
            'timestamp': log.get('timestamp', datetime.now()),
            'level': log.get('level', 'INFO').upper(),
            'action': 'Maintenance',
            'details': log.get('message', 'Maintenance action performed')
        })
    
    # Render maintenance template
    return render_template(
        'admin/maintenance.html', 
        system_stats=system_stats,
        db_stats=db_stats,
        maintenance_logs=formatted_logs,
        current_user=current_user,
        title='System Maintenance'
    )

def update_maintenance():
    """
    Update maintenance mode settings.
    Handles both form submissions and API requests.
    """
    # Get current user for the template
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Get request data (supporting both JSON and form data)
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    
    # Log incoming data for debugging
    logger.info(f"Maintenance mode update request received: {data}")
    
    try:
        enabled = data.get('enabled', False)
        
        # Debug the enabled value
        logger.info(f"Raw enabled value: {enabled}, type: {type(enabled)}")
        
        # Convert string to boolean if it's a string
        if isinstance(enabled, str):
            enabled = enabled.lower() == 'true' or enabled == 'on'
        # Handle None or missing value
        elif enabled is None:
            enabled = False
            
        logger.info(f"Processed enabled value: {enabled}")
        
        message = data.get('message', '')
        duration = data.get('duration', 'indefinite')
        
        logger.info(f"Processing maintenance mode update: enabled={enabled}, duration={duration}")
        
        # Set actual maintenance mode
        if enabled:
            # Convert duration to hours
            duration_hours = None
            if duration == '30min':
                duration_hours = 0.5
            elif duration == '1hour':
                duration_hours = 1
            elif duration == '2hours':
                duration_hours = 2
            elif duration == '4hours':
                duration_hours = 4
            
            # Enable maintenance mode
            logger.info(f"Attempting to enable maintenance mode with message: '{message}' and duration: {duration_hours} hours")
            success = enable_maintenance_mode(current_app, message, duration_hours)
            
            if success:
                # Log the action
                try:
                    system_log = SystemLog()
                    system_log.add_log(
                        level='info',
                        message=f'Maintenance mode enabled by {current_user["username"]}',
                        category='Maintenance',
                        user=current_user['username'],
                        details=f'Duration: {duration}, Message: {message}'
                    )
                except Exception as e:
                    logger.error(f"Error logging maintenance action: {e}")
                
                action_message = 'Maintenance mode enabled successfully'
                logger.info(action_message)
            else:
                action_message = 'Failed to enable maintenance mode'
                logger.error(action_message)
        else:
            # Disable maintenance mode
            logger.info("Attempting to disable maintenance mode")
            success = disable_maintenance_mode(current_app)
            
            if success:
                # Log the action
                try:
                    system_log = SystemLog()
                    system_log.add_log(
                        level='info',
                        message=f'Maintenance mode disabled by {current_user["username"]}',
                        category='Maintenance',
                        user=current_user['username']
                    )
                except Exception as e:
                    logger.error(f"Error logging maintenance action: {e}")
                
                action_message = 'Maintenance mode disabled successfully'
                logger.info(action_message)
            else:
                action_message = 'Failed to disable maintenance mode'
                logger.error(action_message)
        
        # Check the current maintenance mode state
        logger.info(f"Current maintenance mode state after update: {current_app.config.get('MAINTENANCE_MODE', False)}")
        
        # Return based on request type
        if request.is_json:
            return jsonify({
                'success': success,
                'message': action_message
            })
        else:
            if success:
                flash(action_message, 'success')
            else:
                flash(action_message, 'danger')
            return redirect(url_for('admin.maintenance'))
            
    except Exception as e:
        logger.exception(f"Error updating maintenance mode: {e}")
        if request.is_json:
            return jsonify({
                'success': False,
                'message': f"Error updating maintenance mode: {str(e)}"
            }), 500
        else:
            flash(f"Error updating maintenance mode: {str(e)}", 'danger')
            return redirect(url_for('admin.maintenance'))

def generate_report():
    """Generate various reports."""
    # Get current user for the template
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Get form data
    report_type = request.form.get('report_type')
    date_range = request.form.get('date_range')
    report_format = request.form.get('report_format')
    
    # Generate report (mock implementation)
    logger.info(f"Admin '{current_user['username']}' generated {report_type} report in {report_format} format")
    
    # Log the action
    system_log = SystemLog()
    system_log.add_log(
        level='info',
        message=f'Report generated by {current_user["username"]}',
        category='Reports',
        user=current_user['username'],
        details=f'Type: {report_type}, Range: {date_range}, Format: {report_format}'
    )
    
    # Flash success message and redirect
    flash(f'{report_type.capitalize()} report generated successfully in {report_format.upper()} format', 'success')
    return redirect(url_for('admin.dashboard'))
