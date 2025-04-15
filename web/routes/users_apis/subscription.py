"""
Enhanced subscription management routes for Travian Whispers web application.
This module provides the subscription management functionality with production-ready
PayPal integration and improved error handling.
"""
import logging
from datetime import datetime, timedelta
from flask import (
    render_template, flash, session, redirect, 
    url_for, request, jsonify, current_app
)
from bson import ObjectId

from web.utils.decorators import login_required, api_error_handler
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.transaction import Transaction
from database.models.activity_log import ActivityLog
from payment.paypal import process_successful_payment

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(user_bp):
    """Register subscription routes with the user blueprint."""
    # Attach routes to the blueprint
    user_bp.route('/subscription')(login_required(subscription))
    user_bp.route('/subscription/success')(login_required(subscription_success))
    user_bp.route('/subscription/cancel')(login_required(subscription_cancel))
    user_bp.route('/subscription/activate-free', methods=['POST'])(login_required(activate_free_plan))
    
    # Add the transaction detail routes
    user_bp.route('/transaction/<transaction_id>')(login_required(transaction_details))
    user_bp.route('/receipt/<transaction_id>')(login_required(download_receipt))
    
    # Add subscription summary download
    user_bp.route('/subscription/download-summary')(login_required(download_subscription_summary))

@login_required
def subscription():
    """Subscription management route."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        # Flash error message
        flash('User not found', 'danger')
        
        # Clear session and redirect to login
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Get subscription plans
    plan_model = SubscriptionPlan()
    plans = plan_model.list_plans()
    
    # Get current plan
    current_plan = None
    if user['subscription']['planId']:
        current_plan = plan_model.get_plan_by_id(user['subscription']['planId'])
    
    # Get user's transaction history
    transaction_model = Transaction()
    transactions = transaction_model.get_user_transactions(session['user_id'])
    
    # Format transaction history for display
    transaction_history = []
    for tx in transactions:
        # Get plan info
        plan_info = plan_model.get_plan_by_id(tx.get('planId'))
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
    subscription_stats = calculate_subscription_stats(user, transactions)
    
    # Enhance plans data with current status and free plan detection
    for plan in plans:
        plan['is_current'] = current_plan and str(current_plan['_id']) == str(plan['_id'])
        
        # Detect if this is a free plan
        plan['is_free'] = plan['price']['monthly'] == 0 and plan['price']['yearly'] == 0
        
        # Calculate yearly savings
        if 'price' in plan and 'monthly' in plan['price'] and 'yearly' in plan['price']:
            monthly_annual_cost = plan['price']['monthly'] * 12
            yearly_cost = plan['price']['yearly']
            
            if monthly_annual_cost > 0:
                plan['yearly_savings'] = round(100 * (1 - (yearly_cost / monthly_annual_cost)))
            else:
                plan['yearly_savings'] = 0
    
    # Log a view activity
    activity_model = ActivityLog()
    activity_model.log_activity(
        user_id=session['user_id'],
        activity_type='subscription-view',
        details='Viewed subscription management page',
        status='info'
    )
    
    # Render subscription template
    return render_template(
        'user/subscription.html', 
        plans=plans,
        current_plan=current_plan,
        transaction_history=transaction_history,
        subscription_stats=subscription_stats,
        current_user=user, 
        title='Subscription Management'
    )

def calculate_subscription_stats(user, transactions):
    """
    Calculate subscription statistics for display.
    
    Args:
        user (dict): User data
        transactions (list): Transaction history
        
    Returns:
        dict: Subscription statistics
    """
    stats = {
        'status': user['subscription']['status'],
        'start_date': 'N/A',
        'end_date': 'N/A',
        'total_spent': sum(tx.get('amount', 0) for tx in transactions if tx.get('status') == 'completed'),
        'transactions_count': len(transactions),
        'next_payment': 'N/A',
        'subscription_age': 0,
        'remaining_days': 0,
        'auto_renew': user['settings'].get('autoRenew', False)
    }
    
    # Format dates if available
    if user['subscription'].get('startDate'):
        stats['start_date'] = user['subscription']['startDate'].strftime('%Y-%m-%d')
        
        # Calculate subscription age safely
        try:
            # Get the subscription age in days
            now = datetime.utcnow()
            start_date = user['subscription']['startDate']
            
            # Ensure start_date is timezone aware for comparison
            if hasattr(start_date, 'replace') and not start_date.tzinfo:
                start_date = start_date.replace(tzinfo=None)
                delta = now - start_date
                stats['subscription_age'] = delta.days
        except (TypeError, AttributeError) as e:
            logger.warning(f"Error calculating subscription age: {e}")
            stats['subscription_age'] = 0
    
    if user['subscription'].get('endDate'):
        end_date = user['subscription']['endDate']
        stats['end_date'] = end_date.strftime('%Y-%m-%d')
        
        # Calculate days until expiration
        now = datetime.utcnow()

        if hasattr(end_date, 'replace'):
            # Make end_date timezone-naive if it has timezone info
            if end_date.tzinfo:
                end_date = end_date.replace(tzinfo=None)
            
            # Now compare with now (which is already naive)
            if end_date > now:
                delta = end_date - now
                stats['remaining_days'] = delta.days
        
        # For active subscriptions, set next payment date as end date
        if user['subscription']['status'] == 'active':
            stats['next_payment'] = stats['end_date']
    
    # Override next payment message for cancelled, inactive, and free plans
    if user['subscription']['status'] == 'cancelled':
        stats['next_payment'] = 'None - Subscription cancelled'
    elif user['subscription']['status'] == 'inactive':
        stats['next_payment'] = 'None - No active subscription'
    elif stats['total_spent'] == 0 and user['subscription']['status'] == 'active':
        stats['next_payment'] = 'None - Free plan'
    
    return stats

@login_required
def activate_free_plan():
    """
    Activate a free subscription plan for the user.
    This is a special route for handling free plan activation without payment processing.
    """
    # Get plan ID from form
    plan_id = request.form.get('planId')
    
    if not plan_id:
        flash('Plan ID is required', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('auth.login'))
    
    # Get plan details to verify it's really free
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        flash('Plan not found', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Verify this is a free plan
    if plan['price']['monthly'] != 0 or plan['price']['yearly'] != 0:
        flash('Invalid free plan selection', 'danger')
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
    if user_model.update_user(session['user_id'], subscription_data):
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=session['user_id'],
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
        
        # Update user settings based on plan features
        try:
            settings_update = {
                'settings': user['settings'].copy()  # Start with existing settings
            }
            
            # Enable features included in the plan
            if plan['features'].get('autoFarm', False):
                settings_update['settings']['autoFarm'] = True
            else:
                settings_update['settings']['autoFarm'] = False
                
            if plan['features'].get('trainer', False):
                settings_update['settings']['trainer'] = True
            else:
                settings_update['settings']['trainer'] = False
                
            if plan['features'].get('notification', False):
                settings_update['settings']['notification'] = True
            
            # Update user settings
            user_model.update_user(session['user_id'], settings_update)
            logger.info(f"Updated user settings based on free plan features for user {session['user_id']}")
        except Exception as e:
            logger.error(f"Failed to update user settings for free plan: {e}")
        
        flash(f'You have successfully activated the free {plan["name"]} plan!', 'success')
    else:
        flash('Failed to activate free plan', 'danger')
    
    return redirect(url_for('user.subscription'))

logger = logging.getLogger(__name__)

def subscription_success():
    """
    Handle successful subscription payment.
    Process the payment and update the subscription status.
    """
    # Get payment details from query parameters
    order_id = request.args.get('token')
    payer_id = request.args.get('PayerID')
    
    if not order_id:
        flash('Invalid payment parameters: Missing order ID', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Log detailed information about the payment attempt
    user_id = session.get('user_id')
    logger.info(f"Processing payment success for order: {order_id}, payer: {payer_id}, user: {user_id}")
    
    # Process the successful payment
    try:
        # Directly import and use our fixed implementation

        success = process_successful_payment(order_id)
        
        if success:
            # Flash success message
            flash('Your subscription has been successfully activated! You now have access to premium features.', 'success')
            
            # Log the activity
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=user_id,
                activity_type='subscription-payment',
                details=f'Successfully processed payment for subscription (Order ID: {order_id})',
                status='success'
            )
            
            logger.info(f"Payment successfully processed for user {user_id}, order {order_id}")
        else:
            # Flash error message
            flash('There was an issue processing your payment. Please contact support if your subscription is not activated.', 'danger')
            
            # Log the activity
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=user_id,
                activity_type='subscription-payment',
                details=f'Failed to process payment for subscription (Order ID: {order_id})',
                status='error'
            )
            
            logger.error(f"Payment processing failed for user {user_id}, order {order_id}")
    except Exception as e:
        # Log the error in detail
        logger.error(f"Exception during payment processing: {e}", exc_info=True)
        flash('An error occurred while processing your payment. Please contact support.', 'danger')
    
    # Redirect to subscription page
    return redirect(url_for('user.subscription'))

@login_required
def subscription_cancel():
    """Handle cancelled subscription payment."""
    # Flash info message
    flash('Subscription payment was cancelled.', 'info')
    
    # Log the activity
    activity_model = ActivityLog()
    activity_model.log_activity(
        user_id=session['user_id'],
        activity_type='subscription-payment',
        details='Payment process was cancelled by user',
        status='info'
    )
    
    # Redirect to subscription page
    return redirect(url_for('user.subscription'))

@login_required
def transaction_details(transaction_id):
    """Transaction details page."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('auth.login'))
    
    # Get transaction details
    transaction_model = Transaction()
    transaction = transaction_model.get_transaction(transaction_id)
    
    if not transaction:
        flash('Transaction not found', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Verify that this transaction belongs to the current user
    if str(transaction['userId']) != session['user_id']:
        flash('You do not have permission to view this transaction', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Get plan details
    plan_model = SubscriptionPlan()
    plan = None
    if transaction['planId']:
        plan = plan_model.get_plan_by_id(transaction['planId'])
    
    # Format transaction for template
    formatted_tx = {
        'id': str(transaction['_id']),
        'date': transaction['createdAt'].strftime('%Y-%m-%d %H:%M') if isinstance(transaction['createdAt'], datetime) else 'Unknown',
        'plan': plan['name'] if plan else 'Unknown Plan',
        'amount': transaction['amount'],
        'status': transaction['status'],
        'payment_method': transaction['paymentMethod'],
        'payment_id': transaction.get('paymentId', 'N/A'),
        'billing_period': transaction.get('billingPeriod', 'monthly').capitalize()
    }
    
    # Render transaction details template
    return render_template(
        'user/transaction_details.html',
        transaction=formatted_tx,
        current_user=user,
        title='Transaction Details'
    )

@login_required
def download_receipt(transaction_id):
    """Download receipt for transaction."""
    # Get transaction details
    transaction_model = Transaction()
    transaction = transaction_model.get_transaction(transaction_id)
    
    if not transaction:
        flash('Transaction not found', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Verify that this transaction belongs to the current user
    if str(transaction['userId']) != session['user_id']:
        flash('You do not have permission to download this receipt', 'danger')
        return redirect(url_for('user.subscription'))
    
    # Verify transaction is completed
    if transaction['status'] != 'completed':
        flash('Receipt is only available for completed transactions', 'warning')
        return redirect(url_for('user.subscription'))
    
    # Return receipt PDF (implementation depends on your receipt generation)
    try:
        # Here you would generate or fetch the receipt
        # For demonstration, we'll just show a message
        flash('Receipt download functionality is not fully implemented yet', 'info')
        return redirect(url_for('user.subscription'))
    except Exception as e:
        logger.error(f"Error downloading receipt: {e}")
        flash('Error downloading receipt', 'danger')
        return redirect(url_for('user.subscription'))

@login_required
def download_subscription_summary():
    """Download subscription summary."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('auth.login'))
    
    # Get transaction history
    transaction_model = Transaction()
    transactions = transaction_model.get_user_transactions(session['user_id'])
    
    # In a real implementation, you would generate a PDF or CSV summary
    # For now, we'll just redirect back with a message
    flash('Subscription summary download will be implemented soon', 'info')
    return redirect(url_for('user.subscription'))
