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

def update_transaction_status(transaction_id, status):
    """API endpoint to update transaction status."""
    # Get transaction details
    transaction_model = Transaction()
    tx = transaction_model.get_transaction(transaction_id)
    
    if not tx:
        return jsonify({
            'success': False,
            'message': 'Transaction not found'
        }), 404
    
    # Check if status is valid
    valid_statuses = ['pending', 'completed', 'failed', 'refunded']
    if status not in valid_statuses:
        return jsonify({
            'success': False,
            'message': f'Invalid status: {status}'
        }), 400
    
    # Check current status
    if tx['status'] == status:
        return jsonify({
            'success': True,
            'message': f'Transaction already has status: {status}'
        })
    
    # Special handling for 'completed' status
    if status == 'completed' and tx['status'] == 'pending':
        # Process the completed payment
        from payment.paypal import process_successful_payment
        
        # Call process_successful_payment with only the paymentId
        process_result = process_successful_payment(tx["paymentId"])
        
        if process_result:
            logger.info(f"Successfully processed payment for transaction {transaction_id}")
            
            return jsonify({
                'success': True,
                'message': 'Transaction status updated and payment processed successfully'
            })
        else:
            logger.error(f"Failed to process payment for transaction {transaction_id}")
            
            return jsonify({
                'success': False,
                'message': 'Failed to process payment'
            }), 500
    
    # For change from 'completed' to something else - handle subscription accordingly
    if tx['status'] == 'completed' and status != 'completed':
        # Get user model and update subscription status
        user_model = User()
        
        # Update subscription status to inactive
        user_model.update_subscription_status(str(tx["userId"]), "inactive")
        
        logger.info(f"Updated subscription status to inactive for user {tx['userId']}")
    
    # Update transaction status
    if transaction_model.update_transaction_status(transaction_id, status):
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=str(tx['userId']),
            activity_type='transaction-status-update',
            details=f"Transaction status updated from {tx['status']} to {status}",
            status='success'
        )
        
        logger.info(f"Transaction {transaction_id} status updated from {tx['status']} to {status}")
        
        return jsonify({
            'success': True,
            'message': 'Transaction status updated successfully'
        })
    else:
        logger.error(f"Failed to update transaction status for {transaction_id}")
        
        return jsonify({
            'success': False,
            'message': 'Failed to update transaction status'
        }), 500

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































"""
Enhanced subscription API routes for Travian Whispers.
This module includes fixes for subscription status updates, payment processing, and error handling.
"""
import logging
from datetime import datetime, timedelta
from flask import request, jsonify, session, current_app
from bson import ObjectId

from web.utils.decorators import login_required, api_error_handler
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.transaction import Transaction
from database.models.activity_log import ActivityLog
from payment.paypal import create_subscription_order, process_successful_payment

# Initialize logger
logger = logging.getLogger(__name__)

@api_error_handler
@login_required
def create_subscription_order_api():
    """API endpoint to create a PayPal order for subscription payment."""
    # Get user ID from session
    user_id = session.get('user_id')
    
    # Get request data
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Extract required data
    plan_id = data.get('plan_id')
    billing_period = data.get('billing_period', 'monthly')
    
    if not plan_id:
        return jsonify({
            'success': False,
            'message': 'Plan ID is required'
        }), 400
    
    # Get plan details
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        return jsonify({
            'success': False,
            'message': 'Plan not found'
        }), 404
    
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
                details=f"Created subscription order for {plan['name']} plan with {billing_period} billing",
                status='pending'
            )
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
        
        # Return success response
        return jsonify({
            'success': True,
            'message': 'Payment order created successfully',
            'data': {
                'order_id': order_id,
                'approval_url': approval_url
            }
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to create payment order'
        }), 500

@api_error_handler
@login_required
def process_payment_api():
    """API endpoint to process a PayPal payment."""
    # Get request data
    data = request.get_json()
    order_id = data.get('order_id')
    
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

@api_error_handler
@login_required
def cancel_subscription_api():
    """API endpoint to cancel a subscription."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session.get('user_id'))
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Check if user has an active subscription
    if user['subscription']['status'] != 'active':
        return jsonify({
            'success': False,
            'message': 'No active subscription to cancel'
        }), 400
    
    # Get the current subscription plan for better messaging
    plan_model = SubscriptionPlan()
    plan_name = "subscription"
    
    if user['subscription'].get('planId'):
        plan = plan_model.get_plan_by_id(str(user['subscription'].get('planId')))
        if plan:
            plan_name = plan['name']
    
    # Update subscription status to cancelled
    try:
        # Using the User model method if available
        if hasattr(user_model, 'cancel_subscription'):
            success = user_model.cancel_subscription(session.get('user_id'))
        else:
            # Direct update if method not available
            result = user_model.collection.update_one(
                {'_id': ObjectId(session.get('user_id'))},
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
                    user_id=session.get('user_id'),
                    activity_type='subscription-cancel',
                    details=f'Cancelled {plan_name} subscription',
                    status='success'
                )
            except Exception as e:
                logger.error(f"Error logging activity: {e}")
            
            return jsonify({
                'success': True,
                'message': f'Your {plan_name} subscription has been cancelled. You will continue to have access until the end of your current billing period.'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to cancel subscription'
            }), 500
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while cancelling your subscription'
        }), 500

@api_error_handler
@login_required
def get_subscription_status():
    """API endpoint to get user's subscription status."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session.get('user_id'))
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get subscription plan
    plan_model = SubscriptionPlan()
    current_plan = None
    if user['subscription']['planId']:
        current_plan = plan_model.get_plan_by_id(str(user['subscription']['planId']))
    
    # Get user's transaction history
    transaction_model = Transaction()
    transactions = transaction_model.get_user_transactions(session.get('user_id'), limit=5)
    
    # Format transaction history for display
    transaction_history = []
    for tx in transactions:
        # Get plan info
        plan_info = plan_model.get_plan_by_id(str(tx.get('planId'))) if tx.get('planId') else None
        plan_name = plan_info['name'] if plan_info else 'Unknown Plan'
        
        # Format dates properly for display
        created_at = tx.get('createdAt')
        tx_date = created_at.strftime('%Y-%m-%d %H:%M') if isinstance(created_at, datetime) else 'Unknown'
        
        transaction_history.append({
            'id': str(tx.get('_id')),
            'date': tx_date,
            'amount': tx.get('amount'),
            'plan': plan_name,
            'status': tx.get('status'),
            'payment_method': tx.get('paymentMethod'),
            'billing_period': tx.get('billingPeriod', 'monthly').capitalize()
        })
    
    # Calculate subscription statistics
    subscription_stats = {
        'status': user['subscription']['status'],
        'start_date': user['subscription'].get('startDate').strftime('%Y-%m-%d') if user['subscription'].get('startDate') else None,
        'end_date': user['subscription'].get('endDate').strftime('%Y-%m-%d') if user['subscription'].get('endDate') else None,
        'plan': current_plan['name'] if current_plan else None,
        'auto_renew': user['settings'].get('autoRenew', False),
        'features': current_plan['features'] if current_plan else {},
        'remaining_days': 0
    }
    
    # Calculate days until expiration
    if user['subscription'].get('endDate'):
        end_date = user['subscription']['endDate']
        now = datetime.utcnow()
        if hasattr(end_date, 'replace') and end_date > now:
            if end_date.tzinfo:
                end_date = end_date.replace(tzinfo=None)
            delta = end_date - now
            subscription_stats['remaining_days'] = delta.days
    
    return jsonify({
        'success': True,
        'data': {
            'subscription': subscription_stats,
            'transactions': transaction_history
        }
    })

@api_error_handler
@login_required
def update_auto_renew():
    """API endpoint to update auto-renew setting."""
    # Get request data
    data = request.get_json()
    auto_renew = data.get('auto_renew', False)
    
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session.get('user_id'))
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Update auto-renew setting
    settings = user['settings'].copy()
    settings['autoRenew'] = bool(auto_renew)
    
    if user_model.update_user(session.get('user_id'), {'settings': settings}):
        # Log the activity
        try:
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=session.get('user_id'),
                activity_type='settings-update',
                details=f"Updated auto-renew setting to {'enabled' if auto_renew else 'disabled'}",
                status='success'
            )
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
        
        return jsonify({
            'success': True,
            'message': f"Auto-renew {'enabled' if auto_renew else 'disabled'} successfully"
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to update auto-renew setting'
        }), 500

def register_subscription_api_routes(api_bp):
    """Register subscription API routes."""
    api_bp.route('/subscription/create-order', methods=['POST'])(api_error_handler(login_required(create_subscription_order_api)))
    api_bp.route('/subscription/process-payment', methods=['POST'])(api_error_handler(login_required(process_payment_api)))
    api_bp.route('/subscription/cancel', methods=['POST'])(api_error_handler(login_required(cancel_subscription_api)))
    api_bp.route('/subscription/status', methods=['GET'])(api_error_handler(login_required(get_subscription_status)))
    api_bp.route('/subscription/auto-renew', methods=['POST'])(api_error_handler(login_required(update_auto_renew)))