"""
Fixed User profile routes for Travian Whispers web application.
"""
import logging
from datetime import datetime, timezone
from flask import (
    render_template, request, redirect, 
    url_for, flash, session, current_app
)

from web.utils.decorators import login_required
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.activity_log import ActivityLog
from auth.password_reset import change_password

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(user_bp):
    """Register profile routes with the user blueprint."""
    # Attach routes to the blueprint
    user_bp.route('/profile', methods=['GET', 'POST'])(login_required(profile))
    
    # Add API route for profile update
    user_bp.route('/api/user/profile/update', methods=['POST'])(login_required(update_profile_api))
    
    # Add route for account deletion
    user_bp.route('/profile/delete-account', methods=['GET', 'POST'])(login_required(delete_account))

@login_required
def profile():
    """User profile route."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        # Flash error message
        flash('User not found', 'danger')
        
        # Clear session and redirect to login
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Process form submission
    if request.method == 'POST':
        form_type = request.form.get('form_type', '')
        
        if form_type == 'profile':
            # Update profile information
            notification_email = 'notification_email' in request.form
            auto_renew = 'auto_renew' in request.form
            
            # Update settings (email is not included as it cannot be changed)
            update_data = {
                'settings': {
                    'notification': notification_email,
                    'autoRenew': auto_renew,
                    # Preserve existing settings
                    'autoFarm': user['settings'].get('autoFarm', False),
                    'trainer': user['settings'].get('trainer', False),
                }
            }
            
            # Update user in database
            if user_model.update_user(session['user_id'], update_data):
                # Log the activity
                activity_model = ActivityLog()
                activity_model.log_activity(
                    user_id=session['user_id'],
                    activity_type='profile-update',
                    details='Profile information updated',
                    status='success'
                )
                
                # Flash success message
                flash('Profile updated successfully', 'success')
                logger.info(f"User '{user['username']}' updated profile")
            else:
                # Flash error message
                flash('Failed to update profile', 'danger')
                logger.warning(f"Failed to update profile for user '{user['username']}'")
                
        elif form_type == 'password':
            # Change password
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Update password
            success, message = change_password(
                session['user_id'],
                current_password,
                new_password,
                confirm_password
            )
            
            # Flash appropriate message
            if success:
                # Log the activity
                activity_model = ActivityLog()
                activity_model.log_activity(
                    user_id=session['user_id'],
                    activity_type='password-change',
                    details='Password changed successfully',
                    status='success'
                )
                
                flash(message, 'success')
                logger.info(f"User '{user['username']}' changed password")
            else:
                flash(message, 'danger')
                logger.warning(f"Failed to change password for user '{user['username']}': {message}")
    
    # Get current subscription plan if available
    plan_model = SubscriptionPlan()
    current_plan = None
    
    if user['subscription']['planId']:
        plan = plan_model.get_plan_by_id(user['subscription']['planId'])
        if plan:
            current_plan = plan['name']
    
    # Get user activity statistics
    activity_model = ActivityLog()
    
    # Count activities for the user
    activity_count = activity_model.count_user_activities(user_id=session['user_id'])
    
    # Get recent login activity
    login_activity = activity_model.get_latest_user_activity(
        user_id=session['user_id'],
        activity_type='login'
    )
    
    last_login_date = None
    if login_activity and 'timestamp' in login_activity:
        last_login_date = login_activity['timestamp']
    
    # Get account age in days
    utcnow_aware = datetime.utcnow().replace(tzinfo=timezone.utc)
    account_age_days = 0
    if isinstance(user['createdAt'], datetime):
        # Make sure createdAt has timezone info for comparison
        created_at = user['createdAt']
        if not created_at.tzinfo:
            created_at = created_at.replace(tzinfo=timezone.utc)
        account_age_days = (utcnow_aware - created_at).days
    
    # Prepare user profile data
    user_profile = {
        'username': user['username'],
        'email': user['email'],
        'settings': {
            'notification_email': user['settings'].get('notification', True),
            'auto_renew': user['settings'].get('autoRenew', False)
        },
        'subscription': {
            'status': user['subscription']['status'],
            'plan': current_plan or 'None',
            'start_date': user['subscription'].get('startDate'),
            'end_date': user['subscription'].get('endDate')
        },
        'stats': {
            'account_age': account_age_days,
            'activities': activity_count,
            'last_login': last_login_date or user.get('lastLoginAt', 'Never'),
            'villages_count': len(user.get('villages', []))
        }
    }
    
    # Render profile template
    return render_template(
        'user/profile.html', 
        user_profile=user_profile,
        current_user=user, 
        title='Profile Settings'
    )

@login_required
def update_profile_api():
    """API endpoint to update user profile."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        from flask import jsonify
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get request data
    try:
        from flask import request, jsonify
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Update settings
        settings = user['settings'].copy()
        
        if 'notification' in data:
            settings['notification'] = bool(data['notification'])
        
        if 'autoRenew' in data:
            settings['autoRenew'] = bool(data['autoRenew'])
        
        # Update user in database
        update_data = {'settings': settings}
        
        if user_model.update_user(session['user_id'], update_data):
            # Log the activity
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=session['user_id'],
                activity_type='profile-update',
                details='Profile settings updated via API',
                status='success'
            )
            
            # Return success response
            return jsonify({
                'success': True,
                'message': 'Profile updated successfully',
                'data': {'settings': settings}
            })
        else:
            # Return error response
            return jsonify({
                'success': False,
                'message': 'Failed to update profile'
            }), 500
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        from flask import jsonify
        return jsonify({
            'success': False,
            'message': f'Error updating profile: {str(e)}'
        }), 500

@login_required
def delete_account():
    """Delete user account route."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        # Flash error message
        flash('User not found', 'danger')
        
        # Clear session and redirect to login
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Handle form submission
    if request.method == 'POST':
        # Get confirmation
        confirmation = request.form.get('confirm_delete', '').strip().lower()
        
        if confirmation != 'delete':
            flash('Please type "delete" to confirm account deletion', 'danger')
            return redirect(url_for('user.profile'))
        
        # Log the deletion request
        try:
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=session['user_id'],
                activity_type='account-deletion',
                details='Account deletion requested',
                status='info'
            )
        except Exception as e:
            logger.error(f"Error logging account deletion: {e}")
        
        # Delete user
        if hasattr(user_model, 'delete_user'):
            success = user_model.delete_user(session['user_id'])
        else:
            # Fallback method
            result = user_model.collection.delete_one({"_id": ObjectId(session['user_id'])})
            success = result.deleted_count > 0
        
        # Clear session
        session.clear()
        
        if success:
            # Log successful deletion
            logger.info(f"User account {user['username']} (ID: {session['user_id']}) deleted")
            
            # Redirect to goodbye page
            return redirect(url_for('public.goodbye'))
        else:
            # Flash error and redirect to login
            flash('An error occurred while deleting your account. Please try again later.', 'danger')
            return redirect(url_for('auth.login'))
    
    # Render confirmation page
    return render_template(
        'user/delete_account.html',
        current_user=user,
        title='Delete Account'
    )
