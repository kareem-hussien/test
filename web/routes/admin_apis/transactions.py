"""
Admin API for transaction management in Travian Whispers.
This module provides routes for admin transaction management.
"""

import logging
from datetime import datetime, timedelta
from flask import jsonify, request, flash, redirect, url_for
from bson import ObjectId

from web.utils.decorators import admin_required, api_error_handler
from web.utils.error_handlers import ApiError
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.transaction import Transaction
from database.models.activity_log import ActivityLog

# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(admin_bp):
    """Register routes with the admin blueprint."""
    # Transaction routes
    admin_bp.route('/api/transactions')(admin_required(get_transactions))
    admin_bp.route('/api/transactions/<transaction_id>')(admin_required(get_transaction))
    admin_bp.route('/api/transactions/<transaction_id>/update', methods=['POST'])(admin_required(update_transaction))
    admin_bp.route('/api/transactions/stats')(admin_required(get_transaction_stats))
    admin_bp.route('/api/transactions/recent')(admin_required(get_recent_transactions))
    admin_bp.route('/api/transactions/export', methods=['GET'])(admin_required(export_transactions))

@api_error_handler
def get_transactions():
    """Get all transactions with pagination and filtering."""
    # Get query parameters
    status = request.args.get('status')
    user_id = request.args.get('user_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    
    # Build query
    query = {}
    
    if status:
        query['status'] = status
    
    if user_id:
        query['userId'] = user_id
    
    # Parse date range if provided
    if start_date or end_date:
        query['createdAt'] = {}
        
        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                query['createdAt']['$gte'] = start_datetime
            except ValueError:
                raise ApiError('Invalid start date format', 400)
        
        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                # Set end date to end of day
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                query['createdAt']['$lte'] = end_datetime
            except ValueError:
                raise ApiError('Invalid end date format', 400)
    
    # Get transactions
    transaction_model = Transaction()
    
    # Calculate pagination values
    skip = (page - 1) * limit
    
    # Get transactions from database
    cursor = transaction_model.collection.find(query).sort('createdAt', -1).skip(skip).limit(limit)
    total = transaction_model.collection.count_documents(query)
    
    # Format response data
    result = []
    for tx in cursor:
        # Get user info
        user_model = User()
        user = user_model.get_user_by_id(tx['userId'])
        
        # Get plan info
        plan_model = SubscriptionPlan()
        plan = plan_model.get_plan_by_id(str(tx['planId']))
        
        transaction_data = {
            'id': str(tx['_id']),
            'user': {
                'id': str(tx['userId']),
                'username': user['username'] if user else 'Unknown',
                'email': user['email'] if user else 'Unknown'
            },
            'plan': {
                'id': str(tx['planId']),
                'name': plan['name'] if plan else 'Unknown'
            },
            'amount': tx['amount'],
            'status': tx['status'],
            'payment_method': tx['paymentMethod'],
            'payment_id': tx.get('paymentId', 'N/A'),
            'billing_period': tx.get('billingPeriod', 'monthly'),
            'created_at': tx['createdAt'],
            'updated_at': tx.get('updatedAt', tx['createdAt'])
        }
        
        result.append(transaction_data)
    
    return jsonify({
        'success': True,
        'data': result,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit if limit > 0 else 0
        }
    })

@api_error_handler
def get_transaction(transaction_id):
    """Get a specific transaction details."""
    # Get transaction
    transaction_model = Transaction()
    tx = transaction_model.get_transaction(transaction_id)
    
    if not tx:
        return jsonify({
            'success': False,
            'message': 'Transaction not found'
        }), 404
    
    # Get user info
    user_model = User()
    user = user_model.get_user_by_id(tx['userId'])
    
    # Get plan info
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(str(tx['planId']))
    
    # Format transaction data
    transaction_data = {
        'id': str(tx['_id']),
        'user': {
            'id': str(tx['userId']),
            'username': user['username'] if user else 'Unknown',
            'email': user['email'] if user else 'Unknown'
        },
        'plan': {
            'id': str(tx['planId']),
            'name': plan['name'] if plan else 'Unknown'
        },
        'amount': tx['amount'],
        'status': tx['status'],
        'payment_method': tx['paymentMethod'],
        'payment_id': tx.get('paymentId', 'N/A'),
        'billing_period': tx.get('billingPeriod', 'monthly'),
        'created_at': tx['createdAt'],
        'updated_at': tx.get('updatedAt', tx['createdAt'])
    }
    
    return jsonify({
        'success': True,
        'data': transaction_data
    })

@api_error_handler
def update_transaction(transaction_id):
    """Update a transaction status."""
    # Get request data
    data = request.get_json()
    
    if not data or 'status' not in data:
        return jsonify({
            'success': False,
            'message': 'Status parameter is required'
        }), 400
    
    # Validate status
    valid_statuses = ['pending', 'completed', 'failed', 'refunded']
    if data['status'] not in valid_statuses:
        return jsonify({
            'success': False,
            'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
        }), 400
    
    # Get transaction
    transaction_model = Transaction()
    tx = transaction_model.get_transaction(transaction_id)
    
    if not tx:
        return jsonify({
            'success': False,
            'message': 'Transaction not found'
        }), 404
    
    # Get admin user for logging
    user_model = User()
    admin_user = user_model.get_user_by_id(session['user_id'])
    
    # Update transaction status
    if transaction_model.update_transaction_status(transaction_id, data['status']):
        # If changing to completed, process the payment
        if data['status'] == 'completed' and tx['status'] != 'completed':
            # Import PayPal processing function
            from payment.paypal import process_successful_payment
            
            # Process the payment
            if tx.get('paymentId'):
                process_successful_payment(tx['paymentId'])
        
        # Log the activity
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=session['user_id'],
            activity_type='admin-transaction-update',
            details=f"Admin {admin_user['username']} updated transaction {transaction_id} status to {data['status']}",
            status='success'
        )
        
        return jsonify({
            'success': True,
            'message': f'Transaction status updated to {data["status"]}'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to update transaction status'
        }), 500

@api_error_handler
def get_transaction_stats():
    """Get transaction statistics."""
    # Get overall stats
    transaction_model = Transaction()
    stats = transaction_model.get_transaction_stats()
    
    # Get stats for current month
    today = datetime.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get monthly transactions
    monthly_transactions = transaction_model.get_transactions_by_date_range(start_of_month, today)
    
    # Calculate monthly stats
    monthly_total = len(monthly_transactions)
    monthly_completed = sum(1 for tx in monthly_transactions if tx['status'] == 'completed')
    monthly_amount = sum(tx['amount'] for tx in monthly_transactions if tx['status'] == 'completed')
    
    # Get stats for last month
    last_month_end = start_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get last month transactions
    last_month_transactions = transaction_model.get_transactions_by_date_range(last_month_start, last_month_end)
    
    # Calculate last month stats
    last_month_completed = sum(1 for tx in last_month_transactions if tx['status'] == 'completed')
    last_month_amount = sum(tx['amount'] for tx in last_month_transactions if tx['status'] == 'completed')
    
    # Calculate growth
    payment_growth = 0
    revenue_growth = 0
    
    if last_month_completed > 0:
        payment_growth = ((monthly_completed - last_month_completed) / last_month_completed) * 100
        
    if last_month_amount > 0:
        revenue_growth = ((monthly_amount - last_month_amount) / last_month_amount) * 100
    
    return jsonify({
        'success': True,
        'data': {
            'overall': stats,
            'monthly': {
                'total': monthly_total,
                'completed': monthly_completed,
                'amount': monthly_amount
            },
            'growth': {
                'payments': payment_growth,
                'revenue': revenue_growth
            }
        }
    })

@api_error_handler
def get_recent_transactions():
    """Get recent transactions."""
    # Get query parameters
    limit = int(request.args.get('limit', 5))
    
    # Get transactions
    transaction_model = Transaction()
    transactions = transaction_model.get_recent_transactions(limit)
    
    # Format response data
    result = []
    for tx in transactions:
        # Get user info
        user_model = User()
        user = user_model.get_user_by_id(tx['userId'])
        
        # Get plan info
        plan_model = SubscriptionPlan()
        plan = plan_model.get_plan_by_id(str(tx['planId']))
        
        transaction_data = {
            'id': str(tx['_id']),
            'user': {
                'id': str(tx['userId']),
                'username': user['username'] if user else 'Unknown'
            },
            'plan': {
                'name': plan['name'] if plan else 'Unknown'
            },
            'amount': tx['amount'],
            'status': tx['status'],
            'payment_method': tx['paymentMethod'],
            'created_at': tx['createdAt']
        }
        
        result.append(transaction_data)
    
    return jsonify({
        'success': True,
        'data': result
    })

@api_error_handler
def export_transactions():
    """Export transactions to CSV or JSON."""
    # Get query parameters
    format_type = request.args.get('format', 'csv')
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Build query
    query = {}
    
    if status:
        query['status'] = status
    
    # Parse date range if provided
    start_datetime = None
    end_datetime = None
    
    if start_date:
        try:
            start_datetime = datetime.fromisoformat(start_date)
            query['createdAt'] = {'$gte': start_datetime}
        except ValueError:
            raise ApiError('Invalid start date format', 400)
    
    if end_date:
        try:
            end_datetime = datetime.fromisoformat(end_date)
            # Set end date to end of day
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            
            if 'createdAt' in query:
                query['createdAt']['$lte'] = end_datetime
            else:
                query['createdAt'] = {'$lte': end_datetime}
        except ValueError:
            raise ApiError('Invalid end date format', 400)
    
    # Get transactions
    transaction_model = Transaction()
    transactions = list(transaction_model.collection.find(query).sort('createdAt', -1))
    
    # Format data for export
    export_data = []
    
    for tx in transactions:
        # Get user info
        user_model = User()
        user = user_model.get_user_by_id(tx['userId'])
        
        # Get plan info
        plan_model = SubscriptionPlan()
        plan = plan_model.get_plan_by_id(str(tx['planId']))
        
        export_item = {
            'transaction_id': str(tx['_id']),
            'created_at': tx['createdAt'].strftime('%Y-%m-%d %H:%M:%S'),
            'user_id': str(tx['userId']),
            'username': user['username'] if user else 'Unknown',
            'email': user['email'] if user else 'Unknown',
            'plan_id': str(tx['planId']),
            'plan_name': plan['name'] if plan else 'Unknown',
            'amount': tx['amount'],
            'status': tx['status'],
            'payment_method': tx['paymentMethod'],
            'payment_id': tx.get('paymentId', 'N/A'),
            'billing_period': tx.get('billingPeriod', 'monthly')
        }
        
        export_data.append(export_item)
    
    # Export data in the requested format
    if format_type == 'json':
        return jsonify({
            'success': True,
            'data': export_data
        })
    else:  # CSV format
        import csv
        import io
        
        # Create CSV in memory
        output = io.StringIO()
        
        # Get field names from first item or use defaults
        field_names = export_data[0].keys() if export_data else [
            'transaction_id', 'created_at', 'user_id', 'username', 'email',
            'plan_id', 'plan_name', 'amount', 'status', 'payment_method',
            'payment_id', 'billing_period'
        ]
        
        # Create CSV writer
        writer = csv.DictWriter(output, fieldnames=field_names)
        writer.writeheader()
        
        # Write data rows
        for item in export_data:
            writer.writerow(item)
        
        # Prepare response
        from flask import Response
        
        # Generate filename
        filename = f"transactions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Create response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
        return response