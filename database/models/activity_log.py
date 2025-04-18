"""
Enhanced Activity Log model for Travian Whispers application.
This module provides improved activity logging capabilities.
"""
import logging
import math
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import DESCENDING

from database.mongodb import MongoDB

# Initialize logger
logger = logging.getLogger(__name__)

class ActivityLog:
    """Enhanced Activity Log model for tracking user activities."""
    
    def __init__(self):
        """Initialize activity log model."""
        db = MongoDB().get_db()
        self.collection = None
        if db is not None:
            self.collection = db["activity_logs"]
    
    def log_activity(self, user_id, activity_type, details=None, status='success', village=None, data=None):
        """
        Log a user activity.
        
        Args:
            user_id (str): User ID
            activity_type (str): Type of activity (e.g., 'auto-farm', 'troop-training', 'login', 'profile-update')
            details (str): Details of the activity
            status (str): Status of the activity (success, warning, error, info)
            village (str): Village name or ID (optional)
            data (dict): Additional data for the activity (optional)
        
        Returns:
            bool: True if the activity was logged successfully, False otherwise
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return False
                
            # Create log entry
            log_entry = {
                'userId': user_id,
                'activityType': activity_type,
                'details': details or f"{activity_type.replace('-', ' ').title()} activity",
                'status': status,
                'timestamp': datetime.utcnow()
            }
            
            # Add optional fields
            if village:
                log_entry['village'] = village
            
            if data:
                log_entry['data'] = data
            
            # Insert log entry
            result = self.collection.insert_one(log_entry)
            
            return bool(result.inserted_id)
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
            return False
    
    def get_user_logs(self, user_id, page=1, per_page=20, filter_query=None):
        """
        Get paginated user activity logs.
        
        Args:
            user_id (str): User ID
            page (int): Page number
            per_page (int): Number of logs per page
            filter_query (dict): Additional filter criteria
        
        Returns:
            dict: Dictionary containing logs, pagination info, and total count
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return {
                    'logs': [],
                    'page': page,
                    'per_page': per_page,
                    'total': 0,
                    'total_pages': 0
                }
                
            # Build query
            query = {'userId': user_id}
            
            # Add additional filter criteria if provided
            if filter_query:
                for key, value in filter_query.items():
                    if key != 'userId':  # Don't override user ID
                        query[key] = value
            
            # Get total count
            total = self.collection.count_documents(query)
            
            # Calculate pagination
            total_pages = math.ceil(total / per_page)
            skip = (page - 1) * per_page
            
            # Get logs
            logs = list(self.collection.find(query)
                         .sort('timestamp', DESCENDING)
                         .skip(skip)
                         .limit(per_page))
            
            return {
                'logs': logs,
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': total_pages
            }
        except Exception as e:
            logger.error(f"Error getting user logs: {e}")
            return {
                'logs': [],
                'page': page,
                'per_page': per_page,
                'total': 0,
                'total_pages': 0
            }
    
    def get_latest_user_activity(self, user_id, activity_type=None, village=None, filter_query=None):
        """
        Get the latest user activity of a specific type.
        
        Args:
            user_id (str): User ID
            activity_type (str): Type of activity (optional)
            village (str): Village name or ID to filter by (optional)
            filter_query (dict): Additional filter criteria (optional)
        
        Returns:
            dict: Latest activity log or None if not found
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return None
                
            # Build query
            query = {'userId': user_id}
            
            # Add activity type if provided
            if activity_type:
                query['activityType'] = activity_type
            
            # Add village filter if provided
            if village:
                query['village'] = village
                
            # Add additional filter criteria if provided
            if filter_query:
                for key, value in filter_query.items():
                    if key != 'userId':  # Don't override user ID
                        query[key] = value
            
            # Get latest activity
            activity = self.collection.find_one(
                query,
                sort=[('timestamp', DESCENDING)]
            )
            
            return activity
        except Exception as e:
            logger.error(f"Error getting latest user activity: {e}")
            return None
    
    def count_user_activities(self, user_id, activity_type=None, status=None, village=None):
        """
        Count user activities by type or status.
        
        Args:
            user_id (str): User ID
            activity_type (str): Type of activity (optional)
            status (str): Status of activity (optional)
            village (str): Village name or ID (optional)
        
        Returns:
            int: Count of activities
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return 0
                
            # Build query
            query = {'userId': user_id}
            
            # Add activity type if provided
            if activity_type:
                query['activityType'] = activity_type
            
            # Add status if provided
            if status:
                query['status'] = status
                
            # Add village if provided
            if village:
                query['village'] = village
            
            # Count activities
            count = self.collection.count_documents(query)
            
            return count
        except Exception as e:
            logger.error(f"Error counting user activities: {e}")
            return 0
    
    def delete_user_logs(self, user_id):
        """
        Delete all logs for a user.
        
        Args:
            user_id (str): User ID
        
        Returns:
            bool: True if logs were deleted successfully, False otherwise
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return False
                
            # Delete logs
            result = self.collection.delete_many({'userId': user_id})
            
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting user logs: {e}")
            return False
    
    def get_activities_by_period(self, start_date, end_date, user_id=None, activity_type=None):
        """
        Get activities within a specific time period.
        
        Args:
            start_date (datetime): Start date
            end_date (datetime): End date
            user_id (str, optional): Filter by user ID
            activity_type (str, optional): Filter by activity type
            
        Returns:
            list: List of activities within the period
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return []
                
            # Build query
            query = {
                'timestamp': {
                    '$gte': start_date,
                    '$lte': end_date
                }
            }
            
            # Add user ID if provided
            if user_id:
                query['userId'] = user_id
                
            # Add activity type if provided
            if activity_type:
                query['activityType'] = activity_type
                
            # Get activities
            activities = list(self.collection.find(query).sort('timestamp', DESCENDING))
            
            return activities
        except Exception as e:
            logger.error(f"Error getting activities by period: {e}")
            return []
    
    def get_user_activity_stats(self, user_id, days=30):
        """
        Get activity statistics for a user over a period of time.
        
        Args:
            user_id (str): User ID
            days (int): Number of days to include in the stats
            
        Returns:
            dict: Activity statistics
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return {}
                
            # Calculate start date
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Get activities
            activities = self.get_activities_by_period(
                start_date=start_date,
                end_date=datetime.utcnow(),
                user_id=user_id
            )
            
            # Calculate statistics
            total_activities = len(activities)
            activity_types = {}
            activity_status = {
                'success': 0,
                'warning': 0,
                'error': 0,
                'info': 0
            }
            
            for activity in activities:
                # Count by type
                activity_type = activity.get('activityType')
                if activity_type:
                    activity_types[activity_type] = activity_types.get(activity_type, 0) + 1
                
                # Count by status
                status = activity.get('status')
                if status in activity_status:
                    activity_status[status] += 1
            
            return {
                'total': total_activities,
                'by_type': activity_types,
                'by_status': activity_status
            }
        except Exception as e:
            logger.error(f"Error getting user activity stats: {e}")
            return {}
    
    def get_activity_trends(self, user_id, days=30, group_by='day'):
        """
        Get activity trends for a user.
        
        Args:
            user_id (str): User ID
            days (int): Number of days to include
            group_by (str): Group by 'day', 'week', or 'month'
            
        Returns:
            list: Activity trends
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return []
                
            # Calculate start date
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Determine grouping format
            if group_by == 'week':
                format_str = '%Y-%U'  # Year and week number
            elif group_by == 'month':
                format_str = '%Y-%m'  # Year and month
            else:
                format_str = '%Y-%m-%d'  # Year, month, day
            
            # Use aggregation pipeline
            pipeline = [
                # Match activities for the user within the date range
                {
                    '$match': {
                        'userId': user_id,
                        'timestamp': {
                            '$gte': start_date,
                            '$lte': datetime.utcnow()
                        }
                    }
                },
                # Group by formatted date
                {
                    '$group': {
                        '_id': {
                            'date': {
                                '$dateToString': {
                                    'format': format_str,
                                    'date': '$timestamp'
                                }
                            }
                        },
                        'count': {'$sum': 1}
                    }
                },
                # Sort by date
                {
                    '$sort': {'_id.date': 1}
                }
            ]
            
            # Execute aggregation
            results = list(self.collection.aggregate(pipeline))
            
            # Format results
            trends = []
            for result in results:
                date_str = result['_id']['date']
                trends.append({
                    'date': date_str,
                    'count': result['count']
                })
            
            return trends
        except Exception as e:
            logger.error(f"Error getting activity trends: {e}")
            return []
    
    def clean_old_logs(self, days=90):
        """
        Delete logs older than the specified number of days.
        
        Args:
            days (int): Number of days to keep logs for
            
        Returns:
            int: Number of logs deleted
        """
        try:
            if self.collection is None:
                logger.error("Database connection not available")
                return 0
                
            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Delete old logs
            result = self.collection.delete_many({
                'timestamp': {'$lt': cutoff_date}
            })
            
            deleted_count = result.deleted_count
            
            if deleted_count > 0:
                logger.info(f"Cleaned {deleted_count} old logs (older than {days} days)")
                
            return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning old logs: {e}")
            return 0
