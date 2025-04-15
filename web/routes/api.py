"""
API routes for Travian Whispers web application.
This module defines the blueprint for API endpoints.
"""
import logging
from flask import Blueprint, flash, redirect, request, jsonify, session, current_app, url_for
from bson import ObjectId
from datetime import datetime, timedelta

from web.utils.decorators import login_required, admin_required, api_error_handler
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.activity_log import ActivityLog
from payment.paypal import create_subscription_order, process_successful_payment

def jsonify_custom(obj):
    """Custom jsonify function that handles ObjectId and datetime objects."""
    from flask import jsonify
    from web.utils.json_encoder import to_json
    import json
    
    # Convert the object to JSON-serializable data using our custom converter
    serializable_obj = json.loads(json.dumps(obj, default=to_json))
    
    # Use Flask's jsonify with pre-serialized data
    return jsonify(serializable_obj)

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/user/profile', methods=['GET'])
@api_error_handler
@login_required
def get_user_profile():
    """API endpoint to get user profile data."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Prepare user profile data
    user_profile = {
        'username': user['username'],
        'email': user['email'],
        'role': user['role'],
        'subscription': {
            'status': user['subscription']['status'],
            'startDate': user['subscription'].get('startDate'),
            'endDate': user['subscription'].get('endDate')
        },
        'settings': {
            'notification': user['settings'].get('notification', True),
            'autoRenew': user['settings'].get('autoRenew', False),
            'autoFarm': user['settings'].get('autoFarm', False),
            'trainer': user['settings'].get('trainer', False)
        },
        'travianCredentials': {
            'username': user['travianCredentials'].get('username', ''),
            'server': user['travianCredentials'].get('server', ''),
            'tribe': user['travianCredentials'].get('tribe', '')
        },
        'villages': user['villages']
    }
    
    return jsonify({
        'success': True,
        'data': user_profile
    })


@api_bp.route('/user/villages', methods=['GET'])
@api_error_handler
@login_required
def get_user_villages():
    """API endpoint to get user villages."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    return jsonify({
        'success': True,
        'data': user['villages']
    })


@api_bp.route('/user/villages/update', methods=['POST'])
@api_error_handler
@login_required
def update_user_villages():
    """API endpoint to update user villages."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get subscription plan
    plan_model = SubscriptionPlan()
    plan = None
    if user['subscription']['planId']:
        plan = plan_model.get_plan_by_id(user['subscription']['planId'])
    
    # Check villages limit
    villages_limit = plan['features']['maxVillages'] if plan else 0
    
    # Get request data
    data = request.get_json()
    villages = data.get('villages', [])
    
    if len(villages) > villages_limit:
        return jsonify({
            'success': False,
            'message': f'You can only have {villages_limit} villages with your current subscription plan'
        }), 400
    
    # Update user villages
    if user_model.update_villages(session['user_id'], villages):
        logger.info(f"User '{user['username']}' updated villages")
        return jsonify({
            'success': True,
            'message': 'Villages updated successfully',
            'data': villages
        })
    else:
        logger.warning(f"Failed to update villages for user '{user['username']}'")
        return jsonify({
            'success': False,
            'message': 'Failed to update villages'
        }), 500


@api_bp.route('/user/settings/update', methods=['POST'])
@api_error_handler
@login_required
def update_user_settings():
    """API endpoint to update user settings."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get request data
    data = request.get_json()
    settings = data.get('settings', {})
    
    # Validate settings
    if 'autoFarm' in settings and settings['autoFarm']:
        # Check if user has auto-farm in subscription
        plan_model = SubscriptionPlan()
        plan = None
        if user['subscription']['planId']:
            plan = plan_model.get_plan_by_id(user['subscription']['planId'])
        
        if not plan or not plan['features'].get('autoFarm', False):
            return jsonify({
                'success': False,
                'message': 'Auto-Farm is not included in your subscription plan'
            }), 400
    
    if 'trainer' in settings and settings['trainer']:
        # Check if user has trainer in subscription
        plan_model = SubscriptionPlan()
        plan = None
        if user['subscription']['planId']:
            plan = plan_model.get_plan_by_id(user['subscription']['planId'])
        
        if not plan or not plan['features'].get('trainer', False):
            return jsonify({
                'success': False,
                'message': 'Troop Trainer is not included in your subscription plan'
            }), 400
    
    # Update user settings
    update_data = {
        'settings': {
            # Preserve existing settings
            'notification': user['settings'].get('notification', True),
            'autoRenew': user['settings'].get('autoRenew', False),
            'autoFarm': user['settings'].get('autoFarm', False),
            'trainer': user['settings'].get('trainer', False),
            # Update with new settings
            **settings
        }
    }
    
    if user_model.update_user(session['user_id'], update_data):
        logger.info(f"User '{user['username']}' updated settings")
        return jsonify({
            'success': True,
            'message': 'Settings updated successfully',
            'data': update_data['settings']
        })
    else:
        logger.warning(f"Failed to update settings for user '{user['username']}'")
        return jsonify({
            'success': False,
            'message': 'Failed to update settings'
        }), 500


@api_bp.route('/user/travian-credentials/update', methods=['POST'])
@api_error_handler
@login_required
def update_travian_credentials():
    """API endpoint to update travian credentials."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get request data
    data = request.get_json()
    travian_credentials = data.get('travianCredentials', {})
    
    # Check if password field is masked
    if travian_credentials.get('password') == '********':
        # Keep existing password
        travian_credentials['password'] = user['travianCredentials'].get('password', '')
    
    # Update travian credentials
    update_data = {
        'travianCredentials': travian_credentials
    }
    
    if user_model.update_user(session['user_id'], update_data):
        logger.info(f"User '{user['username']}' updated Travian credentials")
        return jsonify({
            'success': True,
            'message': 'Travian credentials updated successfully'
        })
    else:
        logger.warning(f"Failed to update Travian credentials for user '{user['username']}'")
        return jsonify({
            'success': False,
            'message': 'Failed to update Travian credentials'
        }), 500


@api_bp.route('/subscription/create-order', methods=['POST'])
@api_error_handler
@login_required
def create_subscription_order_route():
    """Form-based endpoint to create a PayPal order for subscription payment or activate free plan."""
    # Get user ID
    user_id = session['user_id']
    
    # Get form data
    plan_id = request.form.get('planId')
    billing_period = request.form.get('billingPeriod', 'monthly')
    
    if not plan_id:
        flash('Plan ID is required', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Check if this is a free plan
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        flash('Plan not found', 'danger')
        return redirect(url_for('user.subscription'))
    
    # For free plans, process directly without redirecting
    if plan['price']['monthly'] == 0 and plan['price']['yearly'] == 0:
        logger.info(f"Processing free plan activation for plan: {plan_id}, user: {user_id}")
        
        # Get user data
        user_model = User()
        user = user_model.get_user_by_id(user_id)
        
        if not user:
            logger.error(f"User not found for free plan activation: {user_id}")
            flash('User not found', 'danger')
            return redirect(url_for('user.subscription'))
        
        # Calculate subscription dates
        start_date = datetime.utcnow()
        
        # For free plans, give a long subscription period (1 year)
        end_date = start_date + timedelta(days=365)
        
        # Update subscription data
        subscription_data = {
            'subscription': {
                'planId': ObjectId(plan_id),
                'status': 'active',
                'startDate': start_date,
                'endDate': end_date,
                'billingPeriod': 'yearly',  # Free plans are considered yearly
                # Keep payment history if exists, otherwise initialize
                'paymentHistory': user['subscription'].get('paymentHistory', [])
            }
        }
        
        # Update user subscription
        success = False
        if user_model.update_user(user_id, subscription_data):
            # Log the activity
            try:
                activity_model = ActivityLog()
                activity_model.log_activity(
                    user_id=user_id,
                    activity_type='subscription-activated',
                    details=f"Free {plan['name']} plan activated",
                    status='success',
                    data={
                        'plan_id': str(plan['_id']),
                        'plan_name': plan['name'],
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Error logging activity: {e}")
            
            # Update user settings based on plan features
            try:
                settings_update = {
                    'settings': user['settings'].copy()  # Start with existing settings
                }
                
                # Enable features included in the plan
                settings_update['settings']['autoFarm'] = plan['features'].get('autoFarm', False)
                settings_update['settings']['trainer'] = plan['features'].get('trainer', False)
                
                if plan['features'].get('notification', False):
                    settings_update['settings']['notification'] = True
                
                # Update user settings
                user_model.update_user(user_id, settings_update)
                logger.info(f"Updated user settings based on free plan features for user {user_id}")
                success = True
            except Exception as e:
                logger.error(f"Failed to update user settings for free plan: {e}")
                
            if success:
                flash(f'You have successfully activated the free {plan["name"]} plan!', 'success')
            else:
                flash('Failed to activate free plan', 'danger')
                
            return redirect(url_for('user.subscription'))
    
    # Generate success and cancel URLs
    base_url = request.host_url.rstrip('/')
    success_url = f"{base_url}/dashboard/subscription/success"
    cancel_url = f"{base_url}/dashboard/subscription/cancel"
    
    # Create PayPal order
    success, order_id, approval_url = create_subscription_order(
        plan_id, 
        user_id, 
        success_url, 
        cancel_url,
        billing_period
    )
    
    if success and approval_url:
        # Log the activity
        try:
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=user_id,
                activity_type='subscription-order',
                details=f"Created subscription order with {billing_period} billing",
                status='pending'
            )
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
        
        # Redirect to PayPal for payment
        return redirect(approval_url)
    else:
        flash('Failed to create subscription order. Please try again or contact support.', 'danger')
        return redirect(url_for('user.subscription'))

@api_bp.route('/subscription/cancel', methods=['POST'])
@api_error_handler
@login_required
def cancel_subscription():
    """Form-based endpoint to cancel a subscription."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Check if user has an active subscription
    if user['subscription']['status'] != 'active':
        flash('No active subscription to cancel', 'warning')
        return redirect(url_for('user.subscription'))
    
    # Get the current subscription plan to provide better messaging
    plan_model = SubscriptionPlan()
    plan_name = "subscription"
    
    if user['subscription'].get('planId'):
        plan = plan_model.get_plan_by_id(user['subscription'].get('planId'))
        if plan:
            plan_name = plan['name']
    
    # Update subscription status directly since update_subscription_status doesn't exist
    try:
        result = user_model.collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {
                'subscription.status': 'cancelled',
                'updatedAt': datetime.utcnow()
            }}
        )
        
        success = result.modified_count > 0
        
        if success:
            # Log the activity
            try:
                activity_model = ActivityLog()
                activity_model.log_activity(
                    user_id=session['user_id'],
                    activity_type='subscription-cancel',
                    details=f'Cancelled {plan_name} subscription',
                    status='success'
                )
            except Exception as e:
                logger.error(f"Error logging activity: {e}")
            
            flash(f'Your {plan_name} subscription has been cancelled. You will continue to have access until the end of your current billing period.', 'success')
        else:
            flash('Failed to cancel subscription. Please try again or contact support.', 'danger')
            
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        flash('An error occurred while cancelling your subscription. Please try again or contact support.', 'danger')
    
    return redirect(url_for('user.subscription'))

def update_subscription_status(self, user_id, status):
    """
    Update user subscription status.
    
    Args:
        user_id (str): User ID
        status (str): New subscription status ('active', 'inactive', 'cancelled')
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if self.collection is None:
            logger.error("Database connection not available")
            return False
        
        # Validate status
        valid_statuses = ['active', 'inactive', 'cancelled']
        if status not in valid_statuses:
            logger.error(f"Invalid subscription status: {status}")
            return False
        
        # Get current user data to preserve other subscription fields
        user = self.get_user_by_id(user_id)
        if not user:
            logger.error(f"User not found: {user_id}")
            return False
        
        # Update subscription status
        subscription_data = {
            'subscription.status': status,
            'updatedAt': datetime.utcnow()
        }
        
        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': subscription_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated subscription status to {status} for user {user_id}")
            return True
        else:
            logger.warning(f"No changes made when updating subscription status for user {user_id}")
            return False
    except Exception as e:
        logger.error(f"Error updating subscription status: {e}")
        return False

@api_bp.route('/subscription/process-payment', methods=['POST'])
@api_error_handler
@login_required
def process_payment_route():
    """API endpoint to process a PayPal payment."""
    # Get request data
    data = request.get_json()
    order_id = data.get('orderId')
    
    if not order_id:
        return jsonify({
            'success': False,
            'message': 'Order ID is required'
        }), 400
    
    # Process payment
    if process_successful_payment(order_id):
        return jsonify({
            'success': True,
            'message': 'Payment processed successfully'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to process payment'
        }), 500

# -----------------------------------------------
# Admin API Routes
# -----------------------------------------------

@api_bp.route('/admin/refresh-stats', methods=['GET'])
@api_error_handler
@admin_required
def admin_refresh_stats():
    """API endpoint to refresh admin dashboard statistics."""
    # In a real implementation, this would recompute the statistics
    
    # Get current user for logging
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    logger.info(f"Admin '{current_user['username']}' refreshed dashboard statistics")
    
    return jsonify({
        'success': True,
        'message': 'Stats refreshed successfully'
    })

@api_bp.route('/admin/user/<user_id>', methods=['GET'])
@api_error_handler
@admin_required
def admin_get_user(user_id):
    """API endpoint to get user details for admin."""
    # Get current user for logging
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Get user to view
    user = user_model.get_user_by_id(user_id)
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get subscription data
    subscription_model = SubscriptionPlan()
    plan_name = "None"
    if user['subscription']['planId']:
        plan = subscription_model.get_plan_by_id(user['subscription']['planId'])
        if plan:
            plan_name = plan['name']
    
    # Format dates for JSON serialization
    start_date = None
    end_date = None
    if user['subscription'].get('startDate'):
        start_date = user['subscription']['startDate'].strftime('%Y-%m-%d') if isinstance(user['subscription']['startDate'], datetime) else None
    if user['subscription'].get('endDate'):
        end_date = user['subscription']['endDate'].strftime('%Y-%m-%d') if isinstance(user['subscription']['endDate'], datetime) else None
    
    # Prepare user data
    user_data = {
        'id': str(user['_id']),
        'username': user['username'],
        'email': user['email'],
        'role': user['role'],
        'status': 'active' if user.get('isVerified', False) else 'inactive',
        'createdAt': user['createdAt'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(user['createdAt'], datetime) else str(user['createdAt']),
        'subscription': {
            'status': user['subscription']['status'],
            'planId': str(user['subscription']['planId']) if user['subscription'].get('planId') else None,
            'planName': plan_name,
            'startDate': start_date,
            'endDate': end_date
        },
        'villages': user['villages'],
        'settings': user['settings']
    }
    
    logger.info(f"Admin '{current_user['username']}' viewed user '{user['username']}'")
    
    return jsonify({
        'success': True,
        'data': user_data
    })

"""
API route for user account deletion.
Add this to your web/routes/api.py file.
"""

"""
Fixed API route for user account deletion.
"""
@api_bp.route('/user/delete-account', methods=['POST'])
@api_error_handler
@login_required
def delete_user_account():
    """API endpoint to delete user account."""
    try:
        # Get user ID
        user_id = session['user_id']
        
        # Get user model
        user_model = User()
        user = user_model.get_user_by_id(user_id)
        
        if not user:
            # Handle case when user isn't found
            flash('User not found', 'danger')
            return redirect(url_for('user.profile'))
        
        # First, log the deletion request
        try:
            from database.models.activity_log import ActivityLog
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=user_id,
                activity_type='account-deletion',
                details=f"Account deletion requested by user {user['username']}",
                status='info'
            )
        except Exception as e:
            logger.error(f"Error logging deletion activity: {e}")
        
        # Delete user and all associated data
        success = False
        
        # Check if delete_user method exists
        if hasattr(user_model, 'delete_user'):
            success = user_model.delete_user(user_id)
        else:
            # Implement delete functionality if method doesn't exist
            try:
                # Delete user
                result = user_model.collection.delete_one({"_id": ObjectId(user_id)})
                
                if result.deleted_count > 0:
                    # Delete associated data (activities, etc.)
                    try:
                        from database.models.activity_log import ActivityLog
                        activity_model = ActivityLog()
                        activity_model.delete_user_logs(user_id)
                    except Exception as e:
                        logger.error(f"Error deleting user activities: {e}")
                    
                    success = True
            except Exception as e:
                logger.error(f"Error deleting user: {e}")
                success = False
        
        # Clear session regardless of success
        session.clear()
        
        if success:
            # Log successful deletion (in system logs since user is now deleted)
            logger.info(f"User account deleted: {user['username']} (ID: {user_id})")
            
            # Redirect to goodbye page
            return redirect(url_for('public.goodbye'))
        else:
            # Flash error and redirect to home page
            flash('An error occurred while deleting your account. Please try again later.', 'danger')
            return redirect(url_for('public.index'))
            
    except Exception as e:
        # Log the error
        logger.error(f"Error during account deletion: {e}")
        
        # Clear session in case of error too
        session.clear()
        
        # Flash error and redirect to home page
        flash('An unexpected error occurred. Please try again later.', 'danger')
        return redirect(url_for('public.index'))
    
@api_bp.route('/webhooks/paypal', methods=['POST'])
@api_error_handler
def paypal_webhook():
    """Webhook endpoint for PayPal payment notifications."""
    # Import PayPal webhook function
    from payment.paypal import handle_webhook_event, verify_webhook_signature
    
    # Verify webhook signature
    if not verify_webhook_signature(request.data, request.headers):
        logger.warning("Invalid PayPal webhook signature")
        return jsonify({
            'success': False,
            'message': 'Invalid webhook signature'
        }), 401
    
    # Get webhook event data
    event_data = request.get_json()
    
    # Extract event type
    event_type = event_data.get('event_type')
    
    if not event_type:
        logger.warning("Missing event type in PayPal webhook")
        return jsonify({
            'success': False,
            'message': 'Missing event type'
        }), 400
    
    # Handle webhook event
    if handle_webhook_event(event_type, event_data):
        logger.info(f"Successfully processed PayPal webhook event: {event_type}")
        return jsonify({
            'success': True,
            'message': 'Webhook processed successfully'
        })
    else:
        logger.warning(f"Failed to process PayPal webhook event: {event_type}")
        return jsonify({
            'success': False,
            'message': 'Failed to process webhook event'
        }), 500
