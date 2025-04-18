"""
Fixed PayPal integration for Travian Whispers subscription payments.
This module fixes the datetime comparison issue in the payment processing function.
"""
import logging
import json
from datetime import datetime, timedelta
from bson import ObjectId
from payment.http_utils import perform_request, basic_auth_header

# Initialize logger
logger = logging.getLogger(__name__)

def get_paypal_config():
    """
    Get PayPal configuration from environment.
    
    Returns:
        dict: PayPal configuration
    """
    import config
    
    # Determine if we're in sandbox or production mode
    is_sandbox = config.PAYPAL_MODE.lower() != 'production'
    
    return {
        'client_id': config.PAYPAL_CLIENT_ID,
        'client_secret': config.PAYPAL_SECRET,
        'mode': config.PAYPAL_MODE,
        'base_url': 'https://api-m.sandbox.paypal.com' if is_sandbox else 'https://api-m.paypal.com',
        'is_sandbox': is_sandbox,
    }

def get_access_token():
    """
    Get PayPal API access token.
    
    Returns:
        str: Access token or None if failed
    """
    paypal_config = get_paypal_config()
    
    try:
        url = f"{paypal_config['base_url']}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
            **basic_auth_header(paypal_config['client_id'], paypal_config['client_secret'])
        }
        data = "grant_type=client_credentials"
        
        status, response_headers, content = perform_request(
            url,
            method="POST",
            headers=headers,
            data=data
        )
        
        if status == 200:
            response_data = json.loads(content.decode('utf-8'))
            token = response_data.get("access_token")
            
            if token:
                logger.debug("Successfully obtained PayPal access token")
                return token
            else:
                logger.error("PayPal response missing access_token field")
                return None
        
        error_message = f"Failed to get PayPal access token: Status {status}"
        try:
            error_data = json.loads(content.decode('utf-8', errors='replace'))
            error_details = error_data.get('error_description', str(error_data))
            error_message += f", Details: {error_details}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_message += f", Response: {content.decode('utf-8', errors='replace')}"
            
        logger.error(error_message)
        return None
    except Exception as e:
        error_message = f"Error getting PayPal access token: {str(e)}"
        logger.error(error_message)
        return None

def create_subscription_order(plan_id, user_id, success_url, cancel_url, billing_period='monthly'):
    """
    Create a PayPal order for subscription payment.
    Fixed to handle decimal precision properly.
    
    Args:
        plan_id (str): Subscription plan ID
        user_id (str): User ID
        success_url (str): Redirect URL after successful payment
        cancel_url (str): Redirect URL after cancelled payment
        billing_period (str): Billing period ('monthly' or 'yearly')
        
    Returns:
        tuple: (success, order_id, approval_url)
    """
    from database.models.subscription import SubscriptionPlan
    from database.models.user import User
    from database.models.transaction import Transaction
    from database.models.activity_log import ActivityLog
    
    # Get subscription plan
    plan_model = SubscriptionPlan()
    plan = plan_model.get_plan_by_id(plan_id)
    
    if not plan:
        logger.error(f"Subscription plan not found: {plan_id}")
        return False, None, None
    
    # Get user
    user_model = User()
    user = user_model.get_user_by_id(user_id)
    
    if not user:
        logger.error(f"User not found: {user_id}")
        return False, None, None
    
    # Get access token
    access_token = get_access_token()
    if not access_token:
        logger.error("Failed to get PayPal access token")
        return False, None, None
    
    try:
        paypal_config = get_paypal_config()
        url = f"{paypal_config['base_url']}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        # Determine price based on billing period
        if billing_period == 'yearly':
            price = plan['price']['yearly']
            period_display = 'year'
        else:
            price = plan['price']['monthly']
            period_display = 'month'
            billing_period = 'monthly'  # Ensure consistent value
        
        # Fix: Ensure price is formatted with exactly 2 decimal places
        formatted_price = f"{float(price):.2f}"
        
        # Create order payload
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": f"{user_id}_{plan_id}_{billing_period}",
                    "description": f"Travian Whispers {plan['name']} Subscription - {billing_period.capitalize()} billing",
                    "amount": {
                        "currency_code": "USD",
                        "value": formatted_price
                    },
                    "custom_id": f"{user_id}|{plan_id}|{billing_period}"
                }
            ],
            "application_context": {
                "brand_name": "Travian Whispers",
                "landing_page": "BILLING",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": success_url,
                "cancel_url": cancel_url
            }
        }
        
        # Convert payload to JSON string
        payload_json = json.dumps(payload)
        
        logger.debug(f"PayPal order payload: {payload_json}")
        
        status, response_headers, content = perform_request(
            url,
            method="POST",
            headers=headers,
            data=payload_json
        )
        
        # Log the raw response
        logger.debug(f"PayPal API response: Status {status}, Content: {content.decode('utf-8', errors='replace')}")
        
        if status in (200, 201):
            try:
                data = json.loads(content.decode('utf-8'))
                order_id = data.get("id")
                
                # Find approval URL
                approval_url = None
                for link in data.get("links", []):
                    if link.get("rel") == "approve":
                        approval_url = link.get("href")
                        break
                
                if not order_id or not approval_url:
                    logger.error(f"Failed to extract order details from PayPal response: {data}")
                    return False, None, None
                
                # Create transaction record
                transaction_model = Transaction()
                transaction_id = transaction_model.create_transaction(
                    user_id=user_id,
                    plan_id=plan_id,
                    amount=float(price),
                    payment_method="paypal",
                    payment_id=order_id,
                    billing_period=billing_period
                )
                
                if not transaction_id:
                    logger.error("Failed to create transaction record in database")
                    return False, None, None
                
                # Log transaction creation
                try:
                    activity_model = ActivityLog()
                    activity_model.log_activity(
                        user_id=user_id,
                        activity_type='payment-initiated',
                        details=f"Created PayPal payment order for {plan['name']} plan ({billing_period} billing)",
                        status='pending',
                        data={
                            'order_id': order_id,
                            'plan_id': plan_id,
                            'plan_name': plan['name'],
                            'amount': price,
                            'billing_period': billing_period
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to log activity: {e}")
                
                logger.info(f"Successfully created PayPal order {order_id} for user {user_id}, plan {plan_id}")
                return True, order_id, approval_url
            except json.JSONDecodeError:
                logger.error(f"Failed to parse PayPal response: {content.decode('utf-8', errors='replace')}")
                return False, None, None
        
        # Handle error response
        error_message = f"Failed to create PayPal order: Status {status}"
        try:
            error_data = json.loads(content.decode('utf-8', errors='replace'))
            error_details = []
            
            # Extract detailed error information
            if 'details' in error_data:
                for detail in error_data['details']:
                    error_details.append(f"{detail.get('issue', '')}: {detail.get('description', '')}")
            
            if error_details:
                error_message += f", Details: {' | '.join(error_details)}"
            else:
                error_message += f", Response: {error_data}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_message += f", Response: {content.decode('utf-8', errors='replace')}"
            
        logger.error(error_message)
        return False, None, None
        
    except Exception as e:
        logger.error(f"Error creating PayPal order: {e}", exc_info=True)
        return False, None, None

def process_successful_payment(order_id):
    """
    Process a successful payment and update user subscription.
    Retrieves all necessary data using just the order_id.
    
    Args:
        order_id (str): PayPal order ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from database.models.user import User
        from database.models.subscription import SubscriptionPlan
        from database.models.transaction import Transaction
        from database.models.activity_log import ActivityLog
        
        logger.info(f"Processing payment for order ID: {order_id}")
        
        # Get transaction details
        transaction_model = Transaction()
        transaction = transaction_model.get_transaction_by_payment_id(order_id)
        
        if not transaction:
            logger.error(f"Transaction not found for order_id: {order_id}")
            return False
        
        # Get the transaction ID for database operations
        transaction_id = str(transaction['_id'])
        
        # Check if transaction is already processed
        if transaction['status'] == 'completed':
            logger.info(f"Transaction {transaction_id} (order {order_id}) already processed")
            return True
        
        # Update transaction status
        result = transaction_model.update_transaction_status(transaction_id, 'completed')
        
        if not result:
            logger.error(f"Failed to update transaction status for {transaction_id}")
            return False
            
        logger.info(f"Transaction status updated to completed for {transaction_id}")
        
        # Get user and plan details
        user_model = User()
        plan_model = SubscriptionPlan()
        
        user = user_model.get_user_by_id(transaction['userId'])
        plan = plan_model.get_plan_by_id(str(transaction['planId']))
        
        if not user or not plan:
            logger.error(f"User or plan not found: user_id={transaction['userId']}, plan_id={transaction['planId']}")
            return False
        
        # Parse custom_id to get billing period if not in transaction
        billing_period = transaction.get('billingPeriod', 'monthly')
        
        # Calculate subscription dates
        start_date = datetime.utcnow()
        
        # If user already has active subscription, extend it from current end date
        if user['subscription']['status'] == 'active' and user['subscription'].get('endDate'):
            # Ensure both datetimes are timezone-naive for comparison
            end_date = user['subscription']['endDate']
            
            # Handle timezone-aware vs timezone-naive comparison
            if hasattr(end_date, 'tzinfo') and end_date.tzinfo and not start_date.tzinfo:
                # Make end_date timezone-naive by removing tzinfo
                end_date = end_date.replace(tzinfo=None)
            
            # If start_date has timezone info but end_date doesn't
            elif hasattr(start_date, 'tzinfo') and start_date.tzinfo and not (hasattr(end_date, 'tzinfo') and end_date.tzinfo):
                # Make start_date timezone-naive
                start_date = start_date.replace(tzinfo=None)
                
            # Now compare and use the later date
            if end_date > start_date:
                start_date = end_date
        
        # Calculate end date based on billing period
        if billing_period == 'yearly':
            end_date = start_date + timedelta(days=365)
        else:  # monthly
            end_date = start_date + timedelta(days=30)
        
        # Update subscription data
        subscription_data = {
            'subscription': {
                'planId': transaction['planId'],
                'status': 'active',
                'startDate': start_date,
                'endDate': end_date,
                'billingPeriod': billing_period,
                # Keep payment history if exists, otherwise initialize
                'paymentHistory': user['subscription'].get('paymentHistory', [])
            }
        }
        
        # Add this payment to history
        payment_record = {
            'transactionId': transaction['_id'],
            'amount': transaction['amount'],
            'date': datetime.utcnow(),
            'method': transaction['paymentMethod'],
            'orderId': order_id
        }
        
        # Update user subscription
        try:
            # First update the subscription data
            user_model.update_user(transaction['userId'], subscription_data)
            
            # Then add the payment record to history
            user_model.collection.update_one(
                {'_id': ObjectId(transaction['userId'])},
                {'$push': {'subscription.paymentHistory': payment_record}}
            )
            
            logger.info(f"User subscription updated successfully for user {transaction['userId']}")
        except Exception as e:
            logger.error(f"Failed to update user subscription: {e}")
            return False
        
        # Enable premium features based on plan
        try:
            settings_update = {
                'settings': user['settings'].copy()  # Start with existing settings
            }
            
            # Enable features included in the plan
            if plan['features'].get('autoFarm', False):
                settings_update['settings']['autoFarm'] = True
            
            if plan['features'].get('trainer', False):
                settings_update['settings']['trainer'] = True
                
            # Update user settings
            user_model.update_user(transaction['userId'], settings_update)
            
            logger.info(f"User settings updated successfully for user {transaction['userId']}")
        except Exception as e:
            logger.error(f"Failed to update user settings: {e}")
            # Not critical, continue processing
        
        # Send confirmation email
        try:
            from email_module.sender import send_subscription_confirmation_email
            
            # Format dates for email
            formatted_end_date = end_date.strftime("%B %d, %Y")
            formatted_amount = f"${transaction['amount']:.2f}"
            
            send_subscription_confirmation_email(
                to_email=user["email"],
                username=user["username"],
                plan_name=plan["name"],
                end_date=formatted_end_date,
                amount=formatted_amount,
                payment_id=order_id,
                billing_period=billing_period
            )
            
            logger.info(f"Subscription confirmation email sent to {user['email']}")
        except Exception as e:
            logger.error(f"Failed to send subscription confirmation email: {e}")
            # Non-critical error, continue processing
        
        # Log activity
        try:
            activity_model = ActivityLog()
            activity_model.log_activity(
                user_id=transaction['userId'],
                activity_type='subscription-activated',
                details=f"{plan['name']} subscription activated with {billing_period} billing",
                status='success',
                data={
                    'plan_id': str(plan['_id']),
                    'plan_name': plan['name'],
                    'amount': transaction['amount'],
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'billing_period': billing_period
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log subscription activity: {e}")
        
        logger.info(f"Successfully processed payment for user {user['username']}, plan {plan['name']}")
        return True
            
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}", exc_info=True)
        return False

def verify_webhook_signature(request_body, headers):
    """
    Verify webhook signature from PayPal.
    
    Args:
        request_body (bytes): Raw request body
        headers (dict): Request headers
        
    Returns:
        bool: True if signature is valid, False otherwise
    """
    # Add implementation for webhook signature verification
    # For now return True as placeholder
    return True

def handle_webhook_event(event_type, event_data):
    """
    Handle PayPal webhook event.
    
    Args:
        event_type (str): Event type
        event_data (dict): Event data
        
    Returns:
        bool: True if handled successfully, False otherwise
    """
    logger.info(f"Processing PayPal webhook event: {event_type}")
    
    try:
        # Handle different event types
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            # Process completed payment
            order_id = event_data.get('resource', {}).get('id')
            if order_id:
                return process_successful_payment(order_id)
            else:
                logger.error("Missing order ID in webhook event data")
                return False
        
        # Add handlers for other event types as needed
        
        # Default: log event but take no action
        logger.info(f"No specific handler for event type: {event_type}")
        return True
    except Exception as e:
        logger.error(f"Error handling webhook event: {e}")
        return False