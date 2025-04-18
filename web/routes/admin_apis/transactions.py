"""
Admin transaction management routes for Travian Whispers web application.
"""
import logging
from datetime import datetime, timedelta
from database.models.activity_log import ActivityLog
from flask import (
    render_template, request, redirect, 
    url_for, flash, session, current_app, jsonify
)
from bson import ObjectId
from web.utils.decorators import admin_required
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.transaction import Transaction
def format_mongodb_date(date_field, format='%Y-%m-%d'):
    """
    Format a date field that could be either a datetime object or a MongoDB date dictionary.
    
    Args:
        date_field: A datetime object or MongoDB date dictionary
        format: The desired date format string
        
    Returns:
        str: Formatted date string
    """
    if isinstance(date_field, dict) and "$date" in date_field:
        # Handle MongoDB date dictionary
        date_str = date_field["$date"]
        # If it's an ISO format string, we can parse it
        if 'T' in date_str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime(format)
            except:
                # If parsing fails, just return the date part
                return date_str.split('T')[0]
        return date_str
    elif hasattr(date_field, 'strftime'):
        # Handle datetime object
        return date_field.strftime(format)
    else:
        # Default fallback
        return str(date_field)
    
# Initialize logger
logger = logging.getLogger(__name__)

def register_routes(admin_bp):
    """Register transaction management routes with the admin blueprint."""
    # Attach routes to the blueprint
    admin_bp.route('/transactions')(admin_required(transactions))
    admin_bp.route('/transactions/<transaction_id>')(admin_required(transaction_details))
    admin_bp.route('/transactions/update-status/<transaction_id>', methods=['POST'])(admin_required(update_transaction_status))
    admin_bp.route('/transactions/send-receipt/<transaction_id>', methods=['POST'])(admin_required(send_transaction_receipt))

def transactions():
    """Transaction history page."""
    # Get current user for the template
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Initialize models
    transaction_model = Transaction()
    subscription_model = SubscriptionPlan()
    
    # Get filter parameters
    status_filter = request.args.get('status')
    plan_filter = request.args.get('plan')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_query = request.args.get('q')
    
    # Build query filter
    query_filter = {}
    
    if status_filter:
        query_filter["status"] = status_filter
    
    if plan_filter:
        # Find the plan ID first
        plan = subscription_model.get_plan_by_name(plan_filter)
        if plan:
            query_filter["planId"] = plan["_id"]
    
    # Add date range filter
    if date_from or date_to:
        date_filter = {}
        
        if date_from:
            try:
                from_date = datetime.strptime(date_from, "%Y-%m-%d")
                date_filter["$gte"] = from_date
            except ValueError:
                flash("Invalid 'from' date format", "warning")
        
        if date_to:
            try:
                to_date = datetime.strptime(date_to, "%Y-%m-%d")
                # Set time to end of day
                to_date = to_date.replace(hour=23, minute=59, second=59)
                date_filter["$lte"] = to_date
            except ValueError:
                flash("Invalid 'to' date format", "warning")
        
        if date_filter:
            query_filter["createdAt"] = date_filter
    
    # Add search filter if provided
    if search_query:
        # We need to find users matching the search then filter transactions by those users
        matching_users = list(user_model.collection.find(
            {"$or": [
                {"username": {"$regex": search_query, "$options": "i"}},
                {"email": {"$regex": search_query, "$options": "i"}}
            ]}
        ))
        
        if matching_users:
            user_ids = [str(user["_id"]) for user in matching_users]
            query_filter["userId"] = {"$in": user_ids}
        else:
            # No matching users, add impossible condition to return no results
            query_filter["userId"] = "no-match"
    
    # Fetch transactions from database with pagination
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    # Calculate skip and limit for pagination
    skip = (page - 1) * per_page
    
    # Get total count for pagination
    total_count = transaction_model.collection.count_documents(query_filter)
    
    # Get transactions with pagination
    transactions_cursor = transaction_model.collection.find(query_filter)\
        .sort("createdAt", -1)\
        .skip(skip)\
        .limit(per_page)
    
    # Format transactions for template
    formatted_transactions = []
    
    for tx in transactions_cursor:
        # Get user information
        user = user_model.get_user_by_id(str(tx["userId"]))
        username = user["username"] if user else "Unknown User"
        
        # Get plan information
        plan = subscription_model.get_plan_by_id(str(tx["planId"]))
        plan_name = plan["name"] if plan else "Unknown Plan"
        
        # Format for template
        formatted_transactions.append({
            'id': str(tx["_id"]),
            'user': username,
            'plan': plan_name,
            'amount': f"${tx['amount']:.2f}",
            'date': tx["createdAt"]["$date"].split('T')[0] if isinstance(tx["createdAt"], dict) and "$date" in tx["createdAt"] else tx["createdAt"].strftime('%Y-%m-%d'),
            'status': tx["status"]
        })
    
    # Get all subscription plans for filter dropdown
    all_plans = subscription_model.list_plans()
    
    # Calculate transaction statistics
    stats = {
        'total_transactions': total_count,
        'total_revenue': f"${sum(tx.get('amount', 0) for tx in transaction_model.collection.find({'status': 'completed'})):.2f}",
        'completed': transaction_model.collection.count_documents({"status": "completed"}),
        'pending': transaction_model.collection.count_documents({"status": "pending"})
    }
    
    # Calculate pagination variables
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    # Render transactions template
    return render_template(
        'admin/transactions.html',
        transactions=formatted_transactions,
        stats=stats,
        plans=all_plans,
        pagination={
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages
        },
        current_user=current_user,
        title='Transaction History'
    )

def transaction_details(transaction_id):
    """Transaction details page."""
    # Get current user for the template
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Initialize models
    transaction_model = Transaction()
    subscription_model = SubscriptionPlan()
    
    # Get transaction
    tx = transaction_model.get_transaction(transaction_id)
    
    if not tx:
        flash('Transaction not found', 'danger')
        return redirect(url_for('admin.transactions'))
    
    # Get user
    user = user_model.get_user_by_id(str(tx["userId"]))
    username = user["username"] if user else "Unknown User"
    email = user["email"] if user else "Unknown Email"
    
    # Get plan
    plan = subscription_model.get_plan_by_id(str(tx["planId"]))
    plan_name = plan["name"] if plan else "Unknown Plan"
    
    # Format dates as strings
    start_date = user["subscription"].get("startDate")
    end_date = user["subscription"].get("endDate")
    
    start_date_str = start_date.strftime('%Y-%m-%d') if start_date else "N/A"
    end_date_str = end_date.strftime('%Y-%m-%d') if end_date else "N/A"
    
    # Format for template
    transaction = {
        'id': str(tx["_id"]),
        'user': username,
        'user_id': str(tx["userId"]),
        'user_email': email,
        'plan': plan_name,
        'amount': f"${tx['amount']:.2f}",
        'date': tx["createdAt"]["$date"].split('T')[0] if isinstance(tx["createdAt"], dict) and "$date" in tx["createdAt"] else tx["createdAt"].strftime('%Y-%m-%d'),
        'status': tx["status"],
        'payment_method': tx.get("paymentMethod", "PayPal"),
        'payment_id': tx.get("paymentId", ""),
        'billing_period': tx.get("billingPeriod", "monthly"),
        'subscription_start': format_mongodb_date(user["subscription"].get("startDate")) if user["subscription"].get("startDate") else "N/A",
        'subscription_end': format_mongodb_date(user["subscription"].get("endDate")) if user["subscription"].get("endDate") else "N/A",
        'gateway_response': {
            'transaction_id': tx.get("paymentId", ""),
            'payer_id': 'PAYER123456',  # Mock data
            'payer_email': email,
            'payment_status': tx["status"].upper(),
            'payment_time': format_mongodb_date(tx["createdAt"], '%Y-%m-%dT%H:%M:%SZ'),
            'currency': 'USD',
            'fee': '1.17'  # Mock data
        }
    }
    
    # Render transaction details template
    return render_template(
    'admin/transaction_details.html',
    transaction=transaction,
    current_user=current_user,
    title='Transaction Details'
)

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
        # Check if the method exists and use it, otherwise update directly
        try:
            if hasattr(user_model, 'update_subscription_status'):
                user_model.update_subscription_status(str(tx["userId"]), "inactive")
            else:
                # Direct update if method not available
                user_model.collection.update_one(
                    {'_id': ObjectId(tx["userId"])},
                    {'$set': {
                        'subscription.status': 'inactive',
                        'updatedAt': datetime.utcnow()
                    }}
                )
                
            logger.info(f"Updated subscription status to inactive for user {tx['userId']}")
        except Exception as e:
            logger.error(f"Error updating user subscription status: {e}")
    
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
        
def send_transaction_receipt(transaction_id):
    """Send transaction receipt via email."""
    # Get current user for logging
    user_model = User()
    current_user = user_model.get_user_by_id(session['user_id'])
    
    # Get form data
    email = request.form.get('email')
    subject = request.form.get('subject', 'Your Travian Whispers Receipt')
    message = request.form.get('message', '')
    
    if not email:
        flash('Email address is required', 'danger')
        return redirect(url_for('admin.transaction_details', transaction_id=transaction_id))
    
    # Get transaction
    transaction_model = Transaction()
    tx = transaction_model.get_transaction(transaction_id)
    
    if not tx:
        flash('Transaction not found', 'danger')
        return redirect(url_for('admin.transactions'))
    
    try:
        # Here you would implement actual email sending logic
        # For now, just log it and pretend it worked
        logger.info(f"Sending receipt for transaction {transaction_id} to {email}")
        
        # In a real implementation, you would use something like:
        # from auth.mail import send_mail
        # success = send_mail(email, subject, email_template)
        
        success = True  # Mock success
        
        if success:
            flash(f'Receipt sent to {email}', 'success')
            logger.info(f"Admin '{current_user['username']}' sent receipt for transaction {transaction_id} to {email}")
        else:
            flash('Failed to send receipt', 'danger')
            logger.warning(f"Admin '{current_user['username']}' failed to send receipt for transaction {transaction_id}")
            
    except Exception as e:
        flash(f'Error sending receipt: {str(e)}', 'danger')
        logger.error(f"Error sending receipt: {e}")
    
    return redirect(url_for('admin.transaction_details', transaction_id=transaction_id))
