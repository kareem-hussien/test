"""
System log model with enhanced features for maintenance logging.
"""
import logging
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import MongoClient, DESCENDING
from database.error_handler import handle_operation_error, log_database_activity
from database.mongodb import MongoDB

# Initialize logger
logger = logging.getLogger(__name__)

class SystemLog:
    """
    System log model for Travian Whispers.
    This model handles system logs, maintenance logs, etc.
    """
    
    def __init__(self):
        """Initialize system log model."""
        # Get database connection
        db_conn = MongoDB()
        self.db = db_conn.get_db()
        
        # Initialize collection
        if self.db is not None:  # Check explicitly if db is None
            self.collection = self.db.system_logs
        else:
            logger.error("Failed to connect to database")
            self.collection = None
    
    @handle_operation_error
    @log_database_activity("add log")
    def add_log(self, level, message, category="General", user="system", details="", ip_address=None, stack_trace=None):
        """
        Add a log entry to the system logs.
        
        Args:
            level (str): Log level ('info', 'warning', 'error', 'debug')
            message (str): Log message
            category (str, optional): Log category
            user (str, optional): Username or system
            details (str, optional): Additional details
            ip_address (str, optional): IP address
            stack_trace (str, optional): Stack trace for errors
            
        Returns:
            str: Log ID if successful, None otherwise
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return None
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.utcnow(),
            "level": level.lower(),
            "message": message,
            "category": category,
            "user": user,
            "details": details,
            "ip_address": ip_address,
            "stack_trace": stack_trace
        }
        
        # Insert log entry
        result = self.collection.insert_one(log_entry)
        
        if result.inserted_id:
            logger.debug(f"Added system log: {message}")
            return str(result.inserted_id)
        
        return None
    
    @handle_operation_error
    @log_database_activity("get logs")
    def get_logs(self, page=1, per_page=20, level=None, user=None, date_from=None, date_to=None, category=None):
        """
        Get logs with pagination and filtering.
        
        Args:
            page (int, optional): Page number
            per_page (int, optional): Items per page
            level (str, optional): Filter by log level
            user (str, optional): Filter by user
            date_from (datetime, optional): Filter by date (from)
            date_to (datetime, optional): Filter by date (to)
            category (str, optional): Filter by category
            
        Returns:
            dict: Dict with logs, total count, and pagination info
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return {
                "logs": [],
                "total": 0,
                "page": page,
                "per_page": per_page,
                "total_pages": 0
            }
        
        # Build query based on filters
        query = {}
        
        if level:
            query["level"] = level
        
        if user:
            query["user"] = {"$regex": user, "$options": "i"}
        
        if category:
            query["category"] = category
        
        # Add date filter if provided
        if date_from or date_to:
            query["timestamp"] = {}
            
            if date_from:
                query["timestamp"]["$gte"] = date_from
            
            if date_to:
                query["timestamp"]["$lte"] = date_to
        
        # Get total count
        total = self.collection.count_documents(query)
        
        # Calculate total pages
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        # Adjust page number if out of bounds
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
        
        # Calculate skip and limit
        skip = (page - 1) * per_page
        
        # Get logs from database
        logs_cursor = self.collection.find(query)\
            .sort("timestamp", DESCENDING)\
            .skip(skip)\
            .limit(per_page)
        
        # Convert cursor to list
        logs = list(logs_cursor)
        
        return {
            "logs": logs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }

    @handle_operation_error
    @log_database_activity("get log by id")
    def get_log_by_id(self, log_id):
        """
        Get a log by its ID.
        
        Args:
            log_id (str): Log ID
            
        Returns:
            dict: Log entry or None if not found
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return None
        
        try:
            # Find log by ID
            log = self.collection.find_one({"_id": ObjectId(log_id)})
            return log
        except Exception as e:
            logger.error(f"Error finding log {log_id}: {e}")
            return None

    @handle_operation_error
    @log_database_activity("count logs by level")
    def count_logs_by_level(self):
        """
        Count logs by level.
        
        Returns:
            dict: Counts for each log level
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return {
                "total": 0,
                "info": 0,
                "warning": 0,
                "error": 0,
                "debug": 0
            }
        
        # Count total logs
        total = self.collection.count_documents({})
        
        # Count logs by level
        info_count = self.collection.count_documents({"level": "info"})
        warning_count = self.collection.count_documents({"level": "warning"})
        error_count = self.collection.count_documents({"level": "error"})
        debug_count = self.collection.count_documents({"level": "debug"})
        
        return {
            "total": total,
            "info": info_count,
            "warning": warning_count,
            "error": error_count,
            "debug": debug_count
        }
        
    @handle_operation_error
    @log_database_activity("get logs by timespan")
    def get_logs_by_timespan(self, hours=24):
        """
        Get logs by timespan for charting.
        
        Args:
            hours (int, optional): Timespan in hours
            
        Returns:
            list: Logs grouped by hour with counts
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return []
        
        # Calculate start time (hours ago)
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Aggregation pipeline to group logs by hour and count by level
        pipeline = [
            # Match logs within timespan
            {
                "$match": {
                    "timestamp": {"$gte": start_time}
                }
            },
            # Group by hour and count by level
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"},
                        "day": {"$dayOfMonth": "$timestamp"},
                        "hour": {"$hour": "$timestamp"}
                    },
                    "info": {
                        "$sum": {"$cond": [{"$eq": ["$level", "info"]}, 1, 0]}
                    },
                    "warning": {
                        "$sum": {"$cond": [{"$eq": ["$level", "warning"]}, 1, 0]}
                    },
                    "error": {
                        "$sum": {"$cond": [{"$eq": ["$level", "error"]}, 1, 0]}
                    },
                    "debug": {
                        "$sum": {"$cond": [{"$eq": ["$level", "debug"]}, 1, 0]}
                    },
                    "total": {"$sum": 1}
                }
            },
            # Sort by timestamp
            {
                "$sort": {
                    "_id.year": 1,
                    "_id.month": 1,
                    "_id.day": 1,
                    "_id.hour": 1
                }
            }
        ]
        
        # Run aggregation
        result = list(self.collection.aggregate(pipeline))
        
        # Format for charting
        chart_data = []
        for entry in result:
            timestamp = f"{entry['_id']['year']}-{entry['_id']['month']:02d}-{entry['_id']['day']:02d} {entry['_id']['hour']:02d}:00"
            chart_data.append({
                "timestamp": timestamp,
                "info": entry["info"],
                "warning": entry["warning"],
                "error": entry["error"],
                "debug": entry["debug"],
                "total": entry["total"]
            })
        
        return chart_data

    @handle_operation_error
    @log_database_activity("delete logs")
    def delete_logs_older_than(self, days):
        """
        Delete logs older than the specified number of days.
        
        Args:
            days (int): Retention period in days
            
        Returns:
            int: Number of logs deleted
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return 0
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Delete logs older than cutoff date
        result = self.collection.delete_many({"timestamp": {"$lt": cutoff_date}})
        
        deleted_count = result.deleted_count
        logger.info(f"Deleted {deleted_count} logs older than {days} days")
        
        return deleted_count

    @handle_operation_error
    @log_database_activity("get logs by category")
    def get_logs_by_category(self, category, limit=10):
        """
        Get logs by category.
        
        Args:
            category (str): Log category
            limit (int, optional): Maximum number of logs to return
            
        Returns:
            list: List of logs for the specified category
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return []
        
        try:
            # Find logs by category
            logs_cursor = self.collection.find({"category": category})\
                .sort("timestamp", DESCENDING)\
                .limit(limit)
            
            # Convert cursor to list
            logs = list(logs_cursor)
            
            return logs
        except Exception as e:
            logger.error(f"Error finding logs by category '{category}': {e}")
            return []
