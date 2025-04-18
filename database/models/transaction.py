"""
Transaction model for Travian Whispers web application.
This module provides the Transaction model for handling subscription payments.
"""
import logging
from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING

from database.mongodb import MongoDB

# Initialize logger
logger = logging.getLogger(__name__)

class Transaction:
    """Transaction model for subscription payments."""
    
    def __init__(self):
        """Initialize transaction model."""
        db = MongoDB().get_db()
        self.collection = None
        if db is not None:
            self.collection = db["transactions"]
    
    def create_transaction(self, user_id, plan_id, amount, payment_method, payment_id, billing_period):
        """
        Create a new transaction record.
        
        Args:
            user_id (str): User ID
            plan_id (str): Subscription plan ID
            amount (float): Transaction amount
            payment_method (str): Payment method (paypal, credit_card, etc.)
            payment_id (str): Payment ID from payment gateway
            billing_period (str): Billing period (monthly, yearly)
        
        Returns:
            str: Transaction ID if successful, None otherwise
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return None
                
            # Create transaction record
            transaction = {
                'userId': user_id,
                'planId': ObjectId(plan_id),
                'amount': float(amount),
                'status': 'pending',
                'paymentMethod': payment_method,
                'paymentId': payment_id,
                'billingPeriod': billing_period,
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            # Insert transaction
            result = self.collection.insert_one(transaction)
            
            if result.inserted_id:
                logger.info(f"Created transaction record for user {user_id}, plan {plan_id}")
                return str(result.inserted_id)
            else:
                logger.error("Failed to insert transaction record")
                return None
        except Exception as e:
            logger.error(f"Error creating transaction: {e}")
            return None
    
    def get_transaction(self, transaction_id):
        """
        Get transaction details.
        
        Args:
            transaction_id (str): Transaction ID
        
        Returns:
            dict: Transaction details or None if not found
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return None
                
            # Get transaction
            transaction = self.collection.find_one({'_id': ObjectId(transaction_id)})
            
            return transaction
        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            return None
    
    def get_transaction_by_payment_id(self, payment_id):
        """
        Get transaction by payment ID.
        
        Args:
            payment_id (str): Payment ID from payment gateway
        
        Returns:
            dict: Transaction details or None if not found
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return None
                
            # Find transaction with the given payment ID
            transaction = self.collection.find_one({'paymentId': payment_id})
            
            if not transaction:
                logger.warning(f"No transaction found with payment ID: {payment_id}")
            
            return transaction
        except Exception as e:
            logger.error(f"Error getting transaction by payment ID: {e}")
            return None
    
    def update_transaction_status(self, transaction_id, status):
        """
        Update transaction status.
        
        Args:
            transaction_id (str): Transaction ID
            status (str): New status (completed, failed, refunded)
        
        Returns:
            bool: True if status was updated successfully, False otherwise
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return False
                
            # Update transaction status
            result = self.collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {'status': status, 'updatedAt': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Updated transaction {transaction_id} status to {status}")
                return True
            else:
                logger.warning(f"No changes made when updating transaction {transaction_id} status to {status}")
                return False
        except Exception as e:
            logger.error(f"Error updating transaction status: {e}")
            return False
    
    def get_user_transactions(self, user_id, status=None, limit=None):
        """
        Get transactions for a user.
        
        Args:
            user_id (str): User ID
            status (str, optional): Filter by status
            limit (int, optional): Maximum number of transactions to return
        
        Returns:
            list: List of transactions
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return []
                
            # Build query
            query = {'userId': user_id}
            
            # Add status filter if provided
            if status:
                query['status'] = status
            
            # Create cursor with sorting
            cursor = self.collection.find(query).sort('createdAt', DESCENDING)
            
            # Apply limit if provided
            if limit:
                cursor = cursor.limit(limit)
            
            # Get transactions
            transactions = list(cursor)
            
            return transactions
        except Exception as e:
            logger.error(f"Error getting user transactions: {e}")
            return []
            
    def get_transactions_by_date_range(self, start_date, end_date, status=None):
        """
        Get transactions within a date range.
        
        Args:
            start_date (datetime): Start date
            end_date (datetime): End date
            status (str, optional): Filter by status
            
        Returns:
            list: List of transactions
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return []
                
            # Build query
            query = {
                'createdAt': {
                    '$gte': start_date,
                    '$lte': end_date
                }
            }
            
            # Add status filter if provided
            if status:
                query['status'] = status
            
            # Create cursor with sorting
            cursor = self.collection.find(query).sort('createdAt', DESCENDING)
            
            # Get transactions
            transactions = list(cursor)
            
            return transactions
        except Exception as e:
            logger.error(f"Error getting transactions by date range: {e}")
            return []
    
    def get_recent_transactions(self, limit=10, status=None):
        """
        Get recent transactions.
        
        Args:
            limit (int): Maximum number of transactions to return
            status (str, optional): Filter by status
            
        Returns:
            list: List of transactions
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return []
                
            # Build query
            query = {}
            
            # Add status filter if provided
            if status:
                query['status'] = status
            
            # Create cursor with sorting and limit
            cursor = self.collection.find(query).sort('createdAt', DESCENDING).limit(limit)
            
            # Get transactions
            transactions = list(cursor)
            
            return transactions
        except Exception as e:
            logger.error(f"Error getting recent transactions: {e}")
            return []
    
    def get_transaction_stats(self):
        """
        Get transaction statistics.
        
        Returns:
            dict: Transaction statistics
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return {
                    'total': 0,
                    'completed': 0,
                    'pending': 0,
                    'failed': 0,
                    'total_amount': 0
                }
                
            # Count total transactions
            total = self.collection.count_documents({})
            
            # Count transactions by status
            completed = self.collection.count_documents({'status': 'completed'})
            pending = self.collection.count_documents({'status': 'pending'})
            failed = self.collection.count_documents({'status': 'failed'})
            
            # Calculate total amount from completed transactions
            total_amount = 0
            completed_transactions = self.collection.find({'status': 'completed'})
            for transaction in completed_transactions:
                total_amount += transaction.get('amount', 0)
            
            return {
                'total': total,
                'completed': completed,
                'pending': pending,
                'failed': failed,
                'total_amount': total_amount
            }
        except Exception as e:
            logger.error(f"Error getting transaction stats: {e}")
            return {
                'total': 0,
                'completed': 0,
                'pending': 0,
                'failed': 0,
                'total_amount': 0
            }
