"""
Fixed payment capture and processing implementation for Travian Whispers.
This module fixes the subscription payment processing to properly move payments
from Pending to Completed status.
"""


# Configure logger
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
        'webhook_id': config.PAYPAL_WEBHOOK_ID if hasattr(config, 'PAYPAL_WEBHOOK_ID') else None,
    }
