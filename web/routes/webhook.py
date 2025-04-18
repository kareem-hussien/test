"""
Fixed webhook module for Travian Whispers web application.
This module handles webhooks from payment providers.
"""
import logging
import json
from bson import ObjectId
from datetime import datetime
from flask import Blueprint, request, jsonify

from database.models.transaction import Transaction
from database.models.user import User
from database.models.activity_log import ActivityLog
from payment.paypal import verify_webhook_signature, process_successful_payment

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize blueprint
webhook_bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')

@webhook_bp.route('/paypal', methods=['POST'])
def paypal_webhook():
    """Webhook endpoint for PayPal payment notifications."""
    logger.info("Received PayPal webhook")
    
    # Verify webhook signature
    if not verify_webhook_signature(request.data, request.headers):
        logger.warning("Invalid PayPal webhook signature")
        return jsonify({
            'success': False,
            'message': 'Invalid webhook signature'
        }), 401
    
    # Get webhook event data
    try:
        event_data = request.get_json()
        
        # Log the webhook data (sanitized for sensitive info)
        webhook_type = event_data.get('event_type', 'unknown')
        webhook_id = event_data.get('id', 'unknown')
        logger.info(f"Processing PayPal webhook: Type={webhook_type}, ID={webhook_id}")
        
        # Extract event type
        event_type = event_data.get('event_type')
        
        if not event_type:
            logger.warning("Missing event type in PayPal webhook")
            return jsonify({
                'success': False,
                'message': 'Missing event type'
            }), 400
        
        # Handle different event types
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            return handle_payment_completed(event_data)
        elif event_type == "PAYMENT.CAPTURE.DENIED":
            return handle_payment_denied(event_data)
        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            return handle_payment_refunded(event_data)
        elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            return handle_subscription_cancelled(event_data)
        elif event_type == "BILLING.SUBSCRIPTION.EXPIRED":
            return handle_subscription_expired(event_data)
        else:
            # Log unhandled event types
            logger.info(f"Unhandled PayPal webhook event type: {event_type}")
            return jsonify({
                'success': True,
                'message': f'Event type {event_type} not processed'
            })
    except Exception as e:
        logger.error(f"Error processing PayPal webhook: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error processing webhook: {str(e)}'
        }), 500

def handle_payment_completed(event_data):
    """
    Handle PAYMENT.CAPTURE.COMPLETED event.
    
    Args:
        event_data (dict): Event data from PayPal
        
    Returns:
        Response: JSON response
    """
    try:
        # Extract payment data
        resource = event_data.get('resource', {})
        payment_id = resource.get('id')
        
        if not payment_id:
            logger.error("Missing payment ID in PayPal webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing payment ID'
            }), 400
        
        # Get order ID from supplementary data or parent payment
        order_id = None
        
        # First try to get from supplementary data
        supplementary_data = resource.get('supplementary_data', {})
        related_ids = supplementary_data.get('related_ids', {})
        order_id = related_ids.get('order_id')
        
        # If not found, try to get from links
        if not order_id:
            links = resource.get('links', [])
            for link in links:
                if link.get('rel') == 'up':
                    href = link.get('href', '')
                    # Extract order ID from href
                    if '/orders/' in href:
                        order_id = href.split('/orders/')[1].split('/')[0]
                        break
        
        # If still not found, use payment ID as fallback
        if not order_id:
            order_id = payment_id
            logger.warning(f"No order ID found in webhook data, using payment ID as fallback: {payment_id}")
        
        logger.info(f"Processing completed payment for order: {order_id}")
        
        # Process the payment
        success = process_successful_payment(order_id)
        
        if success:
            logger.info(f"Successfully processed payment for order: {order_id}")
            return jsonify({
                'success': True,
                'message': 'Payment processed successfully'
            })
        else:
            logger.error(f"Failed to process payment for order: {order_id}")
            return jsonify({
                'success': False,
                'message': 'Failed to process payment'
            }), 500
    except Exception as e:
        logger.error(f"Error handling payment completed event: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error processing payment: {str(e)}'
        }), 500

def handle_payment_denied(event_data):
    """
    Handle PAYMENT.CAPTURE.DENIED event.
    
    Args:
        event_data (dict): Event data from PayPal
        
    Returns:
        Response: JSON response
    """
    try:
        # Extract payment data
        resource = event_data.get('resource', {})
        payment_id = resource.get('id')
        
        if not payment_id:
            logger.error("Missing payment ID in PayPal webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing payment ID'
            }), 400
        
        logger.info(f"Processing denied payment: {payment_id}")
        
        # Get transaction for this payment
        transaction_model = Transaction()
        transaction = transaction_model.get_transaction_by_payment_id(payment_id)
        
        if not transaction:
            logger.warning(f"No transaction found for payment ID: {payment_id}")
            return jsonify({
                'success': True,
                'message': 'No matching transaction found'
            })
        
        # Update transaction status
        transaction_id = str(transaction['_id'])
        result = transaction_model.update_transaction_status(transaction_id, 'failed')
        
        if result:
            # Log the activity
            try:
                activity_model = ActivityLog()
                activity_model.log_activity(
                    user_id=str(transaction['userId']),
                    activity_type='payment-failed',
                    details=f"Payment was denied for order (Payment ID: {payment_id})",
                    status='error'
                )
            except Exception as e:
                logger.error(f"Error logging activity: {e}")
            
            logger.info(f"Updated transaction status to failed for: {transaction_id}")
            return jsonify({
                'success': True,
                'message': 'Transaction status updated to failed'
            })
        else:
            logger.error(f"Failed to update transaction status for: {transaction_id}")
            return jsonify({
                'success': False,
                'message': 'Failed to update transaction status'
            }), 500
    except Exception as e:
        logger.error(f"Error handling payment denied event: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error processing payment denial: {str(e)}'
        }), 500

def handle_payment_refunded(event_data):
    """
    Handle PAYMENT.CAPTURE.REFUNDED event.
    
    Args:
        event_data (dict): Event data from PayPal
        
    Returns:
        Response: JSON response
    """
    try:
        # Extract payment data
        resource = event_data.get('resource', {})
        payment_id = resource.get('id')
        
        if not payment_id:
            logger.error("Missing payment ID in PayPal webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing payment ID'
            }), 400
        
        logger.info(f"Processing refunded payment: {payment_id}")
        
        # Get transaction for this payment
        transaction_model = Transaction()
        transaction = transaction_model.get_transaction_by_payment_id(payment_id)
        
        if not transaction:
            logger.warning(f"No transaction found for payment ID: {payment_id}")
            return jsonify({
                'success': True,
                'message': 'No matching transaction found'
            })
        
        # Update transaction status
        transaction_id = str(transaction['_id'])
        result = transaction_model.update_transaction_status(transaction_id, 'refunded')
        
        if result:
            # Update user subscription status
            user_model = User()
            user = user_model.get_user_by_id(str(transaction['userId']))
            
            if user and user['subscription']['status'] == 'active':
                # Check if this was the most recent successful payment
                recent_tx = transaction_model.get_user_transactions(
                    str(transaction['userId']), 
                    status='completed',
                    limit=1
                )
                
                if not recent_tx or str(recent_tx[0]['_id']) == transaction_id:
                    # This was the most recent payment, cancel the subscription
                    try:
                        if hasattr(user_model, 'cancel_subscription'):
                            user_model.cancel_subscription(str(transaction['userId']))
                        else:
                            # Direct update if method not available
                            user_model.collection.update_one(
                                {'_id': ObjectId(str(transaction['userId']))},
                                {'$set': {
                                    'subscription.status': 'cancelled',
                                    'updatedAt': datetime.utcnow()
                                }}
                            )
                        
                        logger.info(f"Cancelled subscription for user {transaction['userId']} due to refund")
                    except Exception as e:
                        logger.error(f"Error updating subscription status: {e}")
            
            # Log the activity
            try:
                activity_model = ActivityLog()
                activity_model.log_activity(
                    user_id=str(transaction['userId']),
                    activity_type='payment-refunded',
                    details=f"Payment was refunded (Payment ID: {payment_id})",
                    status='info'
                )
            except Exception as e:
                logger.error(f"Error logging activity: {e}")
            
            logger.info(f"Updated transaction status to refunded for: {transaction_id}")
            return jsonify({
                'success': True,
                'message': 'Transaction status updated to refunded'
            })
        else:
            logger.error(f"Failed to update transaction status for: {transaction_id}")
            return jsonify({
                'success': False,
                'message': 'Failed to update transaction status'
            }), 500
    except Exception as e:
        logger.error(f"Error handling payment refunded event: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error processing payment refund: {str(e)}'
        }), 500

def handle_subscription_cancelled(event_data):
    """
    Handle BILLING.SUBSCRIPTION.CANCELLED event.
    
    Args:
        event_data (dict): Event data from PayPal
        
    Returns:
        Response: JSON response
    """
    try:
        # Extract subscription data
        resource = event_data.get('resource', {})
        subscription_id = resource.get('id')
        
        if not subscription_id:
            logger.error("Missing subscription ID in PayPal webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing subscription ID'
            }), 400
        
        logger.info(f"Processing cancelled subscription: {subscription_id}")
        
        # Get user with this subscription ID
        user_model = User()
        
        # In a real implementation, you would need to store the PayPal subscription ID
        # For now, we'll log the webhook but not take action
        logger.info(f"Received subscription cancelled webhook for subscription ID: {subscription_id}")
        
        return jsonify({
            'success': True,
            'message': 'Subscription cancellation webhook received'
        })
    except Exception as e:
        logger.error(f"Error handling subscription cancelled event: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error processing subscription cancellation: {str(e)}'
        }), 500

def handle_subscription_expired(event_data):
    """
    Handle BILLING.SUBSCRIPTION.EXPIRED event.
    
    Args:
        event_data (dict): Event data from PayPal
        
    Returns:
        Response: JSON response
    """
    try:
        # Extract subscription data
        resource = event_data.get('resource', {})
        subscription_id = resource.get('id')
        
        if not subscription_id:
            logger.error("Missing subscription ID in PayPal webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing subscription ID'
            }), 400
        
        logger.info(f"Processing expired subscription: {subscription_id}")
        
        # Get user with this subscription ID
        user_model = User()
        
        # In a real implementation, you would need to store the PayPal subscription ID
        # For now, we'll log the webhook but not take action
        logger.info(f"Received subscription expired webhook for subscription ID: {subscription_id}")
        
        return jsonify({
            'success': True,
            'message': 'Subscription expiration webhook received'
        })
    except Exception as e:
        logger.error(f"Error handling subscription expired event: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error processing subscription expiration: {str(e)}'
        }), 500
