"""
Admin API for subscription management in Travian Whispers.
This module provides routes for admin subscription management.
"""

import logging
from datetime import datetime, timedelta
from flask import jsonify, request, flash, redirect, url_for
from bson import ObjectId

from web.utils.decorators import admin_required, api_error_handler
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.transaction import Transaction
from database.models.activity_log import ActivityLog

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(admin_bp):
    """Register routes with the admin blueprint."""
    # Subscription routes
    admin_bp.route('/api/subscriptions')(admin_required(get_subscriptions))
    admin_bp.route('/api/subscriptions/<subscription_id>')(admin_required(get_subscription))
    admin_bp.route('/api/subscriptions/<subscription_id>', methods=['PUT'])(admin_required(update_subscription))
    admin_bp.route('/api/subscriptions/<subscription_id>/cancel', methods=['POST'])(admin_required(cancel_subscription))
    admin_bp.route('/api/subscriptions/<subscription_id>/extend', methods=['POST'])(admin_required(extend_subscription))
    
    # Plan routes
    admin_bp.route('/api/plans')(admin_required(get_plans))
    admin_bp.route('/api/plans/<plan_id>')(admin_required(get_plan))
    admin_bp.route('/api/plans', methods=['POST'])(admin_required(create_plan))
    admin_bp.route('/api/plans/<plan_id>', methods=['PUT'])(admin_required(update_plan))
    admin_bp.route('/api/plans/<plan_id>', methods=['DELETE'])(admin_required(delete_plan))

    # Statistics
    admin_bp.route('/api/subscription-stats')(admin_required(get_subscription_stats))

@api_error_handler
def get_subscriptions():
    """Get all user subscriptions."""
    # Get query parameters
    status = request.args.get('status')
    plan_id = request.args.get('plan_id')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    
    # Build query
    query = {}
    
    if status:
        query['subscription.status'] = status
    
    if plan_id:
        query['subscription.planId'] = ObjectId(plan_id)
    
    # Get users with subscription data
    user_model = User()
    
    # Calculate pagination values
    skip = (page - 1) * limit
    
    # Get users with subscriptions
    users = user_model.collection.find(query).skip(skip).limit(limit)
    total = user_model.collection.count_documents(query)
    
    # Format response data
    result = []
    for user in users:
        # Get plan details if available
        plan_name = 'No Plan'
        if user['subscription'].get('planId'):
            plan_model = SubscriptionPlan()
            plan = plan_model.get_plan_by_id(str(user['subscription']['planId']))
            if plan:
                plan_name = plan['name']
        
        subscription_data = {
            'id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'status': user['subscription']['status'],
            'plan': plan_name,
            'start_date': user['subscription'].get('startDate'),
            'end_date': user['subscription'].get('endDate')
        }
        
        result.append(subscription_data)
    
    return jsonify({
        'success': True,
        'data': result,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit
        }
    })

@api_error_handler
def get_subscription(subscription_id):
    """Get a specific user subscription details."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(subscription_id)
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get plan details if available
    plan_model = SubscriptionPlan()
    plan_data = None
    
    if user['subscription'].get('planId'):
        plan = plan_model.get_plan_by_id(str(user['subscription']['planId']))
        if plan:
            plan_data = {
                'id': str(plan['_id']),
                'name': plan['name'],
                'price': plan['price'],
                'features': plan['features']
            }
    
    # Get transaction history
    transaction_model = Transaction()
    transactions = transaction_model.get_user_transactions(subscription_id, limit=5)
    
    transaction_history = []
    for tx in transactions:
        transaction_history.append({
            'id': str(tx['_id']),
            'date': tx['createdAt'],
            'amount': tx['amount'],
            'status': tx['status'],
            'payment_method': tx['paymentMethod']
        })
    
    # Format subscription data
    subscription_data = {
        'id': str(user['_id']),
        'username': user['username'],
        'email': user['email'],
        'subscription': {
            'status': user['subscription']['status'],
            'plan': plan_data,
            'start_date': user['subscription'].get('startDate'),
            'end_date': user['subscription'].get('endDate'),
            'billing_period': user['subscription'].get('billingPeriod')
        },
        'transactions': transaction_history
    }
    
    return jsonify({
        'success': True,
        'data': subscription_data
    })

@api_error_handler
def update_subscription(subscription_id):
    """Update a user subscription."""
    # Get request data
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(subscription_id)
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get admin user for logging
    admin_user = user_model.get_user_by_id(request.session['user_id'])
    
    # Update subscription status if provided
    if 'status' in data:
        user_model.update_subscription_status(subscription_id, data['status'])
    
    # Update plan if provided
    if 'plan_id' in data:
        # Get additional plan update data
        billing_period = data.get('billing_period', 'monthly')
        
        # Parse dates if provided
        start_date = None
        end_date = None
        
        if 'start_date' in data:
            try:
                start_date = datetime.fromisoformat(data['start_date'])
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid start date format'
                }), 400
        
        if 'end_date' in data:
            try:
                end_date = datetime.fromisoformat(data['end_date'])
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid end date format'
                }), 400
        
        # Update plan
        user_model.update_subscription_plan(
            subscription_id,
            data['plan_id'],
            billing_period,
            start_date,
            end_date
        )
    
    # Log the activity
    activity_model = ActivityLog()
    activity_model.log_activity(
        user_id=request.session['user_id'],
        activity_type='admin-subscription-update',
        details=f"Admin {admin_user['username']} updated subscription for user {user['username']}",
        status='success'
    )
    
    return jsonify({
        'success': True,
        'message': 'Subscription updated successfully'
    })

@api_error_handler
def cancel_subscription(subscription_id):
    """Cancel a user subscription."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(subscription_id)
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get admin user for logging
    admin_user = user_model.get_user_by_id(request.session['user_id'])
    
    # Cancel subscription
    if user_model.cancel_subscription(subscription_id):
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=request.session['user_id'],
            activity_type='admin-subscription-cancel',
            details=f"Admin {admin_user['username']} cancelled subscription for user {user['username']}",
            status='success'
        )
        
        return jsonify({
            'success': True,
            'message': 'Subscription cancelled successfully'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to cancel subscription'
        }), 500

@api_error_handler
def extend_subscription(subscription_id):
    """Extend a user subscription."""
    # Get request data
    data = request.get_json()
    
    if not data or 'days' not in data:
        return jsonify({
            'success': False,
            'message': 'Days parameter is required'
        }), 400
    
    # Parse days parameter
    try:
        days = int(data['days'])
        if days <= 0:
            raise ValueError("Days must be positive")
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid days parameter'
        }), 400
    
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(subscription_id)
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get admin user for logging
    admin_user = user_model.get_user_by_id(request.session['user_id'])
    
    # Check if user has an active subscription
    if user['subscription']['status'] != 'active' and user['subscription']['status'] != 'cancelled':
        return jsonify({
            'success': False,
            'message': 'User does not have an active or cancelled subscription'
        }), 400
    
    # Get current end date
    current_end_date = user['subscription'].get('endDate')
    
    if not current_end_date:
        return jsonify({
            'success': False,
            'message': 'User does not have a subscription end date'
        }), 400
    
    # Calculate new end date
    new_end_date = current_end_date + timedelta(days=days)
    
    # Update subscription
    result = user_model.collection.update_one(
        {'_id': ObjectId(subscription_id)},
        {
            '$set': {
                'subscription.endDate': new_end_date,
                'subscription.status': 'active',  # Reactivate if cancelled
                'updatedAt': datetime.utcnow()
            }
        }
    )
    
    if result.modified_count > 0:
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=request.session['user_id'],
            activity_type='admin-subscription-extend',
            details=f"Admin {admin_user['username']} extended subscription for user {user['username']} by {days} days",
            status='success'
        )
        
        return jsonify({
            'success': True,
            'message': f'Subscription extended by {days} days',
            'new_end_date': new_end_date
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to extend subscription'
        }), 500

@api_error_handler
def get_plans():
    """Get all subscription plans."""
    # Get plans
    plan_model = SubscriptionPlan()
    plans = plan_model.list_plans()
    
    # Format response data
    result = []
    for plan in plans:
        plan_data = {
            'id': str(plan['_id']),
            'name': plan['name'],
            'description': plan['description'],
            'price': plan['price'],
            'features': plan['features'],
            'created_at': plan['createdAt']
        }
        
        result.append(plan_data)
    
    return jsonify({
        'success': True,
        'data': result
    })

@api_error_handler
def get_plan(plan_id):
    """Get a specific plan details."""
    # Get plan
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        return jsonify({
            'success': False,
            'message': 'Plan not found'
        }), 404
    
    # Format plan data
    plan_data = {
        'id': str(plan['_id']),
        'name': plan['name'],
        'description': plan['description'],
        'price': plan['price'],
        'features': plan['features'],
        'created_at': plan['createdAt'],
        'updated_at': plan['updatedAt']
    }
    
    return jsonify({
        'success': True,
        'data': plan_data
    })

@api_error_handler
def create_plan():
    """Create a new subscription plan."""
    # Get request data
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Validate required fields
    required_fields = ['name', 'description', 'price', 'features']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'success': False,
                'message': f'Missing required field: {field}'
            }), 400
    
    # Create plan
    plan_model = SubscriptionPlan()
    plan = plan_model.create_plan(
        data['name'],
        data['description'],
        data['price']['monthly'],
        data['price']['yearly'],
        data['features']
    )
    
    if not plan:
        return jsonify({
            'success': False,
            'message': 'Failed to create plan'
        }), 500
    
    # Get admin user for logging
    user_model = User()
    admin_user = user_model.get_user_by_id(request.session['user_id'])
    
    # Log the activity
    activity_model = ActivityLog()
    activity_model.log_activity(
        user_id=request.session['user_id'],
        activity_type='admin-plan-create',
        details=f"Admin {admin_user['username']} created new plan: {data['name']}",
        status='success'
    )
    
    return jsonify({
        'success': True,
        'message': 'Plan created successfully',
        'data': {
            'id': str(plan['_id']),
            'name': plan['name']
        }
    })

@api_error_handler
def update_plan(plan_id):
    """Update a subscription plan."""
    # Get request data
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Get plan to check if it exists
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        return jsonify({
            'success': False,
            'message': 'Plan not found'
        }), 404
    
    # Update plan
    if plan_model.update_plan(plan_id, data):
        # Get admin user for logging
        user_model = User()
        admin_user = user_model.get_user_by_id(request.session['user_id'])
        
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=request.session['user_id'],
            activity_type='admin-plan-update',
            details=f"Admin {admin_user['username']} updated plan: {plan['name']}",
            status='success'
        )
        
        return jsonify({
            'success': True,
            'message': 'Plan updated successfully'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to update plan'
        }), 500

@api_error_handler
def delete_plan(plan_id):
    """Delete a subscription plan."""
    # Get plan to check if it exists
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        return jsonify({
            'success': False,
            'message': 'Plan not found'
        }), 404
    
    # Check if any users are using this plan
    user_model = User()
    users_with_plan = user_model.collection.count_documents({
        'subscription.planId': ObjectId(plan_id)
    })
    
    if users_with_plan > 0:
        return jsonify({
            'success': False,
            'message': f'Cannot delete plan: {users_with_plan} users are currently using this plan'
        }), 400
    
    # Delete plan
    if plan_model.delete_plan(plan_id):
        # Get admin user for logging
        admin_user = user_model.get_user_by_id(request.session['user_id'])
        
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=request.session['user_id'],
            activity_type='admin-plan-delete',
            details=f"Admin {admin_user['username']} deleted plan: {plan['name']}",
            status='success'
        )
        
        return jsonify({
            'success': True,
            'message': 'Plan deleted successfully'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to delete plan'
        }), 500

@api_error_handler
def get_subscription_stats():
    """Get subscription statistics."""
    # Get users
    user_model = User()
    
    # Count users by subscription status
    active_count = user_model.collection.count_documents({
        'subscription.status': 'active'
    })
    
    cancelled_count = user_model.collection.count_documents({
        'subscription.status': 'cancelled'
    })
    
    inactive_count = user_model.collection.count_documents({
        'subscription.status': 'inactive'
    })
    
    # Get count by plan
    plan_model = SubscriptionPlan()
    plans = plan_model.list_plans()
    
    plan_stats = []
    total_revenue = 0
    
    for plan in plans:
        # Count users on this plan
        users_count = user_model.collection.count_documents({
            'subscription.planId': plan['_id'],
            'subscription.status': 'active'
        })
        
        # Calculate monthly revenue
        monthly_revenue = users_count * plan['price']['monthly']
        total_revenue += monthly_revenue
        
        plan_stats.append({
            'id': str(plan['_id']),
            'name': plan['name'],
            'users_count': users_count,
            'monthly_revenue': monthly_revenue
        })
    
    # Get transaction stats
    transaction_model = Transaction()
    tx_stats = transaction_model.get_transaction_stats()
    
    return jsonify({
        'success': True,
        'data': {
            'subscriptions': {
                'active': active_count,
                'cancelled': cancelled_count,
                'inactive': inactive_count,
                'total': active_count + cancelled_count + inactive_count
            },
            'plans': plan_stats,
            'revenue': {
                'monthly': total_revenue,
                'annual': total_revenue * 12
            },
            'transactions': tx_stats
        }
    })