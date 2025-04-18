"""
Enhanced transaction routes for Travian Whispers.
This module provides improved handling of subscription transactions with better error handling.
"""
import logging
from datetime import datetime
from flask import render_template, flash, session, redirect, url_for, request, jsonify, Response
import json
import io
import csv

from web.utils.decorators import login_required, api_error_handler
from database.models.user import User
from database.models.subscription import SubscriptionPlan
from database.models.transaction import Transaction
from database.models.activity_log import ActivityLog

# Initialize logger
logger = logging.getLogger(__name__)

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
    if transaction.get('planId'):
        plan = plan_model.get_plan_by_id(str(transaction['planId']))
    
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
    
    # Log view activity
    try:
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=session['user_id'],
            activity_type='transaction-view',
            details=f"Viewed transaction details for {formatted_tx['id']}",
            status='info'
        )
    except Exception as e:
        logger.error(f"Error logging activity: {e}")
    
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
    
    # Generate receipt
    try:
        # Get user and plan data
        user_model = User()
        plan_model = SubscriptionPlan()
        
        user = user_model.get_user_by_id(session['user_id'])
        plan = None
        if transaction.get('planId'):
            plan = plan_model.get_plan_by_id(str(transaction['planId']))
        
        # Create CSV receipt
        output = io.StringIO()
        fieldnames = ['Item', 'Details']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Write receipt details
        writer.writerow({'Item': 'Receipt ID', 'Details': str(transaction['_id'])})
        writer.writerow({'Item': 'Transaction Date', 'Details': transaction['createdAt'].strftime('%Y-%m-%d %H:%M') if isinstance(transaction['createdAt'], datetime) else 'Unknown'})
        writer.writerow({'Item': 'User', 'Details': user['username']})
        writer.writerow({'Item': 'Email', 'Details': user['email']})
        writer.writerow({'Item': 'Plan', 'Details': plan['name'] if plan else 'Unknown Plan'})
        writer.writerow({'Item': 'Billing Period', 'Details': transaction.get('billingPeriod', 'monthly').capitalize()})
        writer.writerow({'Item': 'Amount', 'Details': f"${transaction['amount']:.2f}"})
        writer.writerow({'Item': 'Payment Method', 'Details': transaction['paymentMethod'].capitalize()})
        writer.writerow({'Item': 'Status', 'Details': transaction['status'].capitalize()})
        writer.writerow({'Item': 'Payment ID', 'Details': transaction.get('paymentId', 'N/A')})
        
        # Create response
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=receipt_{transaction_id}_{timestamp}.csv'
            }
        )
        
        # Log download activity
        try:
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=session['user_id'],
                activity_type='receipt-download',
                details=f"Downloaded receipt for transaction {transaction_id}",
                status='success'
            )
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
        
        return response
    except Exception as e:
        logger.error(f"Error generating receipt: {e}")
        flash('Error generating receipt. Please try again.', 'danger')
        return redirect(url_for('user.transaction_details', transaction_id=transaction_id))

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
    
    # Get plan data
    plan_model = SubscriptionPlan()
    
    # Generate CSV summary
    try:
        output = io.StringIO()
        fieldnames = ['Date', 'Plan', 'Billing Period', 'Amount', 'Status', 'Payment Method', 'Payment ID']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Write transactions
        for tx in transactions:
            # Get plan info
            plan_info = plan_model.get_plan_by_id(str(tx.get('planId'))) if tx.get('planId') else None
            plan_name = plan_info['name'] if plan_info else 'Unknown Plan'
            
            writer.writerow({
                'Date': tx['createdAt'].strftime('%Y-%m-%d %H:%M') if isinstance(tx['createdAt'], datetime) else 'Unknown',
                'Plan': plan_name,
                'Billing Period': tx.get('billingPeriod', 'monthly').capitalize(),
                'Amount': f"${tx['amount']:.2f}",
                'Status': tx['status'].capitalize(),
                'Payment Method': tx['paymentMethod'].capitalize(),
                'Payment ID': tx.get('paymentId', 'N/A')
            })
        
        # Create response
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=subscription_summary_{timestamp}.csv'
            }
        )
        
        # Log download activity
        try:
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=session['user_id'],
                activity_type='subscription-summary-download',
                details="Downloaded subscription transaction summary",
                status='success'
            )
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
        
        return response
    except Exception as e:
        logger.error(f"Error generating subscription summary: {e}")
        flash('Error generating subscription summary. Please try again.', 'danger')
        return redirect(url_for('user.subscription'))

@api_error_handler
@login_required
def get_transaction_history():
    """API endpoint to get transaction history."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get transaction history
    transaction_model = Transaction()
    transactions = transaction_model.get_user_transactions(session['user_id'])
    
    # Get plan model
    plan_model = SubscriptionPlan()
    
    # Format transaction history
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
    
    return jsonify({
        'success': True,
        'data': transaction_history
    })

@api_error_handler
@login_required
def get_transaction_details(transaction_id):
    """API endpoint to get transaction details."""
    # Get transaction details
    transaction_model = Transaction()
    transaction = transaction_model.get_transaction(transaction_id)
    
    if not transaction:
        return jsonify({
            'success': False,
            'message': 'Transaction not found'
        }), 404
    
    # Verify that this transaction belongs to the current user
    if str(transaction['userId']) != session['user_id']:
        return jsonify({
            'success': False,
            'message': 'You do not have permission to view this transaction'
        }), 403
    
    # Get plan details
    plan_model = SubscriptionPlan()
    plan = None
    if transaction.get('planId'):
        plan = plan_model.get_plan_by_id(str(transaction['planId']))
    
    # Format transaction
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
    
    return jsonify({
        'success': True,
        'data': formatted_tx
    })

def register_transaction_routes(user_bp):
    """Register transaction routes with the user blueprint."""
    user_bp.route('/transaction/<transaction_id>')(login_required(transaction_details))
    user_bp.route('/receipt/<transaction_id>')(login_required(download_receipt))
    user_bp.route('/subscription/download-summary')(login_required(download_subscription_summary))

def register_transaction_api_routes(api_bp):
    """Register transaction API routes."""
    api_bp.route('/user/transactions', methods=['GET'])(api_error_handler(login_required(get_transaction_history)))
    api_bp.route('/user/transactions/<transaction_id>', methods=['GET'])(api_error_handler(login_required(get_transaction_details)))
