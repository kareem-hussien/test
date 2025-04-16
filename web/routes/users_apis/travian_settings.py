"""
Updated Travian settings module that automatically checks Gold Club membership.
This module combines verification and village extraction into a single flow.
"""
import logging
import time
from flask import (
    render_template, request, redirect, 
    url_for, flash, session, jsonify
)

from bson import ObjectId
from web.utils.decorators import login_required
from database.models.user import User
from database.models.activity_log import ActivityLog

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(user_bp):
    """Register travian settings routes with the user blueprint."""
    # Attach routes to the blueprint
    user_bp.route('/travian-settings', methods=['GET', 'POST'])(login_required(travian_settings))

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
        
        # Gold club status will be determined automatically during validation
        
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
        
        if error:
            travian_settings = {
                'travian_credentials': {
                    'username': travian_username,
                    'password': '********' if user['travianCredentials'].get('password', '') else '',
                    'server': travian_server,
                    'tribe': travian_tribe,
                    'gold_club_member': user['travianCredentials'].get('gold_club_member', False)
                },
                'last_connection': 'Never',  # Default value
                'connection_verified': False,
                'villages_count': len(user.get('villages', []))
            }
            
            # Get connection log information if available
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
        
        # The process now becomes:
        # 1. Save the credentials first
        # 2. Verify Travian connection
        # 3. Check Gold Club membership
        # 4. Extract villages
        # All of these steps are done automatically
        
        # First, update travian credentials without Gold Club status
        update_data = {
            'travianCredentials': {
                'username': travian_username,
                'password': travian_password,
                'server': travian_server,
                'tribe': travian_tribe,
                # Keep existing Gold Club status for now
                'gold_club_member': user['travianCredentials'].get('gold_club_member', False)
            }
        }
        
        # Update user in database
        if user_model.update_user(session['user_id'], update_data):
            flash('Travian account settings saved successfully', 'success')
            logger.info(f"User '{user['username']}' updated Travian settings")
            
            # Step 2: Verify connection and detect Gold Club membership
            connection_verified = False
            is_gold_club_member = False
            
            try:
                # First, verify connection
                from travian_api.connector import test_connection
                connection_result = test_connection(
                    travian_username, 
                    travian_password, 
                    travian_server
                )
                connection_verified = connection_result['success']
                
                if connection_verified:
                    flash('Travian account successfully connected and verified!', 'success')
                    logger.info(f"Travian connection verified for user '{user['username']}'")
                    
                    # Now check Gold Club membership
                    try:
                        from web.routes.gold_club_api import check_gold_club_membership
                        is_gold_club_member = check_gold_club_membership(
                            travian_username,
                            travian_password,
                            travian_server
                        )
                        
                        # Update user with Gold Club status
                        user_model.update_user(session['user_id'], {
                            'travianCredentials.gold_club_member': is_gold_club_member
                        })
                        
                        if is_gold_club_member:
                            flash('Gold Club membership detected! Additional features are available.', 'success')
                            logger.info(f"Gold Club membership verified for user '{user['username']}'")
                        else:
                            logger.info(f"User '{user['username']}' is not a Gold Club member")
                        
                        # Step 3: Extract villages
                        villages_extracted = False
                        villages_count = 0
                        
                        try:
                            from web.routes.users_apis.villages import extract_villages_internal
                            
                            # Extract villages
                            extraction_result = extract_villages_internal(session['user_id'])
                            
                            if extraction_result.get('success'):
                                villages_extracted = True
                                villages_count = len(extraction_result.get('data', []))
                                flash(f'Successfully extracted {villages_count} villages from your Travian account!', 'success')
                                logger.info(f"Villages extracted for user '{user['username']}': {villages_count}")
                            else:
                                flash(f"Villages could not be extracted: {extraction_result.get('message', 'Unknown error')}", 'warning')
                                logger.warning(f"Village extraction failed for user '{user['username']}': {extraction_result.get('message', 'Unknown error')}")
                        except Exception as e:
                            logger.error(f"Error during village extraction: {e}")
                            flash('Connection verified, but village extraction failed. Please try manually extracting villages.', 'warning')
                    except Exception as e:
                        logger.error(f"Error checking Gold Club membership: {e}")
                        flash('Connection verified, but Gold Club verification failed.', 'warning')
                else:
                    flash(f"Settings saved but connection could not be verified: {connection_result.get('message', 'Unknown error')}", 'warning')
                    logger.warning(f"Travian connection failed for user '{user['username']}': {connection_result.get('message', 'Unknown error')}")
            except ImportError as import_err:
                logger.warning(f"Required module not available: {import_err}")
                flash('Settings saved. Automatic verification is not available. Please try extracting villages manually.', 'info')
            except Exception as e:
                logger.error(f"Error verifying Travian connection: {e}")
                flash('Settings saved but there was an error verifying the connection', 'warning')
            
            # Log the activity
            try:
                activity_model = ActivityLog()
                
                # Log various activities depending on what succeeded
                if connection_verified:
                    activity_model.log_activity(
                        user_id=session['user_id'],
                        activity_type='travian-connection',
                        details='Successfully connected to Travian account',
                        status='success',
                        data={
                            'gold_club_member': is_gold_club_member
                        }
                    )
                    
                    if is_gold_club_member:
                        activity_model.log_activity(
                            user_id=session['user_id'],
                            activity_type='gold-club-verification',
                            details='Gold Club membership verified automatically',
                            status='success'
                        )
                else:
                    activity_model.log_activity(
                        user_id=session['user_id'],
                        activity_type='travian-settings-update',
                        details='Updated Travian account settings',
                        status='success'
                    )
            except Exception as e:
                logger.error(f"Error logging activity: {e}")
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
            'tribe': user['travianCredentials'].get('tribe', ''),
            'gold_club_member': user['travianCredentials'].get('gold_club_member', False)
        },
        'last_connection': 'Never',  # Default value
        'connection_verified': False,
        'villages_count': len(user.get('villages', []))
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