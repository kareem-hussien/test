"""
Updated Travian settings module with automatic village extraction and simplified Gold Club verification.
"""
import logging

from flask import (
    render_template, request, redirect, 
    url_for, flash, session
)
from bson import ObjectId

from web.utils.decorators import login_required
from database.models.user import User
from database.models.activity_log import ActivityLog
from web.routes.users_apis.villages import extract_villages_internal

# Import Gold Club verification function
from web.utils.gold_club import check_gold_club_membership

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(user_bp):
    """Register travian settings routes with the user blueprint."""
    # Attach routes to the blueprint
    user_bp.route('/travian-settings', methods=['GET', 'POST'])(login_required(travian_settings))
    user_bp.route('/disconnect-travian', methods=['POST'])(login_required(disconnect_travian))



def is_travian_account_registered(username, server, exclude_user_id=None):
    """
    Check if a Travian account is already registered by another user.
    
    Args:
        username (str): Travian username
        server (str): Travian server URL
        exclude_user_id (str, optional): User ID to exclude from the check
        
    Returns:
        bool: True if account is already registered, False otherwise
    """
    user_model = User()
    
    # Normalize the server URL for comparison
    if server and not server.startswith(('http://', 'https://')):
        server = f"https://{server}"
    
    # Build query to find users with this Travian account
    query = {
        "travianCredentials.username": username
    }
    
    # If server is provided, include it in the query
    if server:
        query["travianCredentials.server"] = server
    
    # If we're updating an existing user, exclude them from the check
    if exclude_user_id:
        query["_id"] = {"$ne": ObjectId(exclude_user_id)}
    
    # Check if any user has this account registered
    count = user_model.collection.count_documents(query)
    return count > 0

@login_required
def travian_settings():
    """Travian account settings route."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        # Flash error message
        flash('User not found', 'danger')
        
        # Clear session and redirect to login
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Check if user has an active subscription
    if user['subscription']['status'] != 'active':
        # Flash error message
        flash('You need an active subscription to connect a Travian account', 'warning')
        
        # Redirect to subscription page
        return redirect(url_for('user.subscription'))
    
    # Process form submission
    if request.method == 'POST':
        # Get form data
        travian_username = request.form.get('travian_username', '')
        travian_password = request.form.get('travian_password', '')
        travian_server = request.form.get('travian_server', '')
        travian_tribe = request.form.get('travian_tribe', '')
        
        # Validate inputs
        error = False
        if not travian_username:
            flash('Travian username is required', 'danger')
            error = True
            
        # Check for changes in password field
        if travian_password == '********':
            # Password field was not changed, use existing password
            travian_password = user['travianCredentials'].get('password', '')
        elif not travian_password:
            flash('Travian password is required', 'danger')
            error = True
            
        # Check if account is already registered by another user
        if not error and is_travian_account_registered(travian_username, travian_server, session['user_id']):
            flash('This Travian account is already registered and cannot be added again', 'danger')
            error = True
        
        if error:
            # If there were validation errors, don't update and re-render the form
            # with the current values
            travian_settings = {
                'travian_credentials': {
                    'username': travian_username,
                    'password': '********' if user['travianCredentials'].get('password', '') else '',
                    'server': travian_server,
                    'tribe': travian_tribe
                },
                'last_connection': 'Never',  # Default value
                'connection_verified': False,
                'is_gold_member': user['travianCredentials'].get('is_gold_member', False)
            }
            
            # Try to get connection log information
            try:
                activity_model = ActivityLog()
                connection_log = activity_model.get_latest_user_activity(
                    user_id=session['user_id'],
                    activity_type='travian-connection'
                )
                
                if connection_log and connection_log.get('timestamp'):
                    travian_settings['last_connection'] = connection_log['timestamp'].strftime('%Y-%m-%d %H:%M')
                    travian_settings['connection_verified'] = connection_log.get('status') == 'success'
            except Exception as e:
                logger.error(f"Error getting connection log: {e}")
            
            return render_template(
                'user/travian_settings.html', 
                user_profile=travian_settings,
                current_user=user, 
                title='Travian Settings'
            )
        
        # Update travian credentials
        update_data = {
            'travianCredentials': {
                'username': travian_username,
                'password': travian_password,
                'server': travian_server,
                'tribe': travian_tribe,
                'is_gold_member': user['travianCredentials'].get('is_gold_member', False) # Preserve existing gold club status
            }
        }
        
        # Update user in database
        if user_model.update_user(session['user_id'], update_data):
            # Flash initial success message
            flash('Travian account settings updated successfully', 'success')
            logger.info(f"User '{user['username']}' updated Travian settings")
            
            # Attempt to verify connection with Travian servers
            try:
                # Get fresh user data with updated credentials
                updated_user = user_model.get_user_by_id(session['user_id'])
                
                # Notify user that we're trying connection
                flash('Verifying connection and extracting villages from your profile...', 'info')
                
                # Execute village extraction (which also verifies connection)
                extraction_result = extract_villages_internal(session['user_id'])
                
                if extraction_result.get('success'):
                    villages_count = len(extraction_result.get('data', []))
                    flash(f'Successfully extracted {villages_count} villages from your Travian profile!', 'success')
                    logger.info(f"Villages extracted for user '{user['username']}': {villages_count}")
                    
                    # Log successful connection
                    activity_model = ActivityLog()
                    activity_model.log_activity(
                        user_id=session['user_id'],
                        activity_type='travian-connection',
                        details='Successfully connected to Travian account and extracted villages from profile',
                        status='success',
                        data={
                            'villages_count': villages_count
                        }
                    )
                    
                    # Now check for Gold Club membership using the driver from the village extraction
                    if 'gold_club_check' in extraction_result:
                        is_gold_member = extraction_result.get('gold_club_check', False)
                        
                        # Update user's Gold Club status
                        user_model.update_user(session['user_id'], {
                            'travianCredentials.is_gold_member': is_gold_member
                        })
                        
                        # Show appropriate message based on result
                        if is_gold_member:
                            flash('Gold Club membership confirmed!', 'success')
                            
                            # Log Gold Club membership
                            activity_model.log_activity(
                                user_id=session['user_id'],
                                activity_type='gold-club-check',
                                details='Gold Club membership confirmed',
                                status='success'
                            )
                        else:
                            flash('You are not a Gold Club member. Some premium features may be unavailable.', 'warning')
                            
                            # Log non-Gold Club status
                            activity_model.log_activity(
                                user_id=session['user_id'],
                                activity_type='gold-club-check',
                                details='User is not a Gold Club member',
                                status='info'
                            )
                else:
                    flash(f"Your settings were saved but village extraction failed: {extraction_result.get('message', 'Unknown error')}", 'warning')
                    logger.warning(f"Village extraction failed for user '{user['username']}': {extraction_result.get('message', 'Unknown error')}")
                    
                    # Log failed connection
                    activity_model = ActivityLog()
                    activity_model.log_activity(
                        user_id=session['user_id'],
                        activity_type='travian-connection',
                        details=f"Failed to extract villages: {extraction_result.get('message', 'Unknown error')}",
                        status='error'
                    )
            except Exception as e:
                logger.error(f"Error during connection verification: {e}")
                flash('Settings saved but there was an error verifying the connection', 'warning')
                
                # Log error
                try:
                    activity_model = ActivityLog()
                    activity_model.log_activity(
                        user_id=session['user_id'],
                        activity_type='travian-settings-update',
                        details=f'Updated Travian settings but verification failed: {str(e)}',
                        status='warning'
                    )
                except Exception as log_err:
                    logger.error(f"Error logging activity: {log_err}")
        else:
            # Flash error message
            flash('Failed to update Travian account settings', 'danger')
            logger.warning(f"Failed to update Travian settings for user '{user['username']}'")
    
    # Get last connection data from logs
    connection_log = None
    travian_settings = {
        'travian_credentials': {
            'username': user['travianCredentials'].get('username', ''),
            'password': '********' if user['travianCredentials'].get('password', '') else '',
            'server': user['travianCredentials'].get('server', ''),
            'tribe': user['travianCredentials'].get('tribe', '')
        },
        'last_connection': 'Never',  # Default value
        'connection_verified': False,
        'villages_count': len(user.get('villages', [])),
        'is_gold_member': user['travianCredentials'].get('is_gold_member', False)
    }
    
    try:
        activity_model = ActivityLog()
        
        # Get latest connection activity
        connection_log = activity_model.get_latest_user_activity(
            user_id=session['user_id'],
            activity_type='travian-connection'
        )
        
        # Update last connection if available
        if connection_log and connection_log.get('timestamp'):
            travian_settings['last_connection'] = connection_log['timestamp'].strftime('%Y-%m-%d %H:%M')
            travian_settings['connection_verified'] = connection_log.get('status') == 'success'
    except Exception as e:
        logger.error(f"Error getting connection log: {e}")
    
    # Render travian settings template
    return render_template(
        'user/travian_settings.html', 
        user_profile=travian_settings,
        current_user=user, 
        title='Travian Settings'
    )
    
@login_required
def disconnect_travian():
    """Disconnect Travian account route."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        # Flash error message
        flash('User not found', 'danger')
        
        # Clear session and redirect to login
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Create empty travian credentials
    empty_credentials = {
        'username': '',
        'password': '',
        'server': '',
        'tribe': '',
        'is_gold_member': False
    }
    
    # Update user in database
    if user_model.update_user(session['user_id'], {'travianCredentials': empty_credentials}):
        # Clear villages - correct approach
        user_model.update_user(session['user_id'], {'villages': []})
        
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=session['user_id'],
            activity_type='travian-disconnect',
            details='Travian account disconnected successfully',
            status='success'
        )
        
        # Flash success message
        flash('Travian account disconnected successfully', 'success')
        logger.info(f"User '{user['username']}' disconnected Travian account")
    else:
        # Flash error message
        flash('Failed to disconnect Travian account', 'danger')
        logger.warning(f"Failed to disconnect Travian account for user '{user['username']}'")
    
    # Redirect back to travian settings
    return redirect(url_for('user.travian_settings'))