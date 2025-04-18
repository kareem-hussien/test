"""
Enhanced Transaction model for Travian Whispers web application.
This module handles subscription transactions with improved error handling.
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
    
    # Transaction status constants
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    
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
                'status': self.STATUS_PENDING,
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
            
            if not transaction:
                logger.warning(f"No transaction found with ID: {transaction_id}")
                
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
                
            # Validate status
            valid_statuses = [self.STATUS_PENDING, self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_REFUNDED]
            if status not in valid_statuses:
                logger.error(f"Invalid transaction status: {status}")
                return False
                
            # Update transaction status
            result = self.collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {'status': status, 'updatedAt': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Updated transaction {transaction_id} status to {status}")
                return True
            elif result.matched_count > 0:
                # Transaction exists but status didn't change (e.g., already had this status)
                logger.info(f"Transaction {transaction_id} already has status {status}")
                return True
            else:
                logger.warning(f"No transaction found with ID {transaction_id}")
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
    
    def count_transactions_by_status(self, status=None):
        """
        Count transactions by status.
        
        Args:
            status (str, optional): Status to filter by
            
        Returns:
            int: Count of transactions
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return 0
                
            # Build query
            query = {}
            
            # Add status filter if provided
            if status:
                query['status'] = status
            
            # Count transactions
            count = self.collection.count_documents(query)
            
            return count
        except Exception as e:
            logger.error(f"Error counting transactions: {e}")
            return 0
    
    def get_transactions_by_period(self, start_date, end_date, status=None):
        """
        Get transactions within a date range.
        
        Args:
            start_date (datetime): Start date
            end_date (datetime): End date
            status (str, optional): Status to filter by
            
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
            
            # Find transactions
            transactions = list(self.collection.find(query).sort('createdAt', DESCENDING))
            
            return transactions
        except Exception as e:
            logger.error(f"Error getting transactions by period: {e}")
            return []
    
    def calculate_revenue(self, start_date=None, end_date=None):
        """
        Calculate total revenue from completed transactions.
        
        Args:
            start_date (datetime, optional): Start date for filtering
            end_date (datetime, optional): End date for filtering
            
        Returns:
            float: Total revenue
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return 0
                
            # Build query
            query = {'status': self.STATUS_COMPLETED}
            
            # Add date range if provided
            if start_date or end_date:
                query['createdAt'] = {}
                
                if start_date:
                    query['createdAt']['$gte'] = start_date
                
                if end_date:
                    query['createdAt']['$lte'] = end_date
            
            # Use aggregation pipeline to calculate sum
            pipeline = [
                {'$match': query},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ]
            
            results = list(self.collection.aggregate(pipeline))
            
            if results:
                return results[0]['total']
            else:
                return 0
        except Exception as e:
            logger.error(f"Error calculating revenue: {e}")
            return 0
    
    def get_monthly_revenue_stats(self, year=None):
        """
        Get monthly revenue statistics.
        
        Args:
            year (int, optional): Year to filter by
            
        Returns:
            list: Monthly revenue statistics
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return []
                
            # Determine year to use
            if year is None:
                year = datetime.utcnow().year
            
            # Use aggregation pipeline to calculate monthly stats
            pipeline = [
                # Match completed transactions for the specified year
                {
                    '$match': {
                        'status': self.STATUS_COMPLETED,
                        '$expr': {'$eq': [{'$year': '$createdAt'}, year]}
                    }
                },
                # Group by month
                {
                    '$group': {
                        '_id': {'$month': '$createdAt'},
                        'total': {'$sum': '$amount'},
                        'count': {'$sum': 1}
                    }
                },
                # Sort by month
                {
                    '$sort': {'_id': 1}
                }
            ]
            
            # Execute aggregation
            results = list(self.collection.aggregate(pipeline))
            
            # Format results
            monthly_stats = []
            for result in results:
                month = result['_id']
                monthly_stats.append({
                    'month': month,
                    'total': result['total'],
                    'count': result['count']
                })
            
            return monthly_stats
        except Exception as e:
            logger.error(f"Error getting monthly revenue stats: {e}")
            return []
