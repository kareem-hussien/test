"""
MongoDB connection and management module with improved error handling.
"""
import pymongo
from pymongo import MongoClient
import logging
from datetime import datetime
import config
from database.error_handler import (
    handle_connection_error, 
    handle_operation_error,
    log_database_activity,
    ConnectionError
)

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('mongodb')

class MongoDB:
    """MongoDB connection handler for Travian Whispers."""
    
    _instance = None
    
    def __new__(cls):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super(MongoDB, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.db = None
        return cls._instance
    
    @handle_connection_error
    @log_database_activity("connection")
    def connect(self, connection_string=None, db_name=None):
        """
        Connect to MongoDB using the provided connection string.
        
        Args:
            connection_string (str): MongoDB connection string
            db_name (str): Database name to use
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        # Use config values if not provided
        if connection_string is None:
            connection_string = config.MONGODB_URI
        
        if db_name is None:
            db_name = config.MONGODB_DB_NAME
        
        try:
            # Use a connection pool for better performance
            self.client = MongoClient(
                connection_string, 
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=45000,
                maxPoolSize=50,
                waitQueueTimeoutMS=2500,
                retryWrites=True,
                retryReads=True,
                tz_aware=True
            )
            # Ping the server to test connection
            self.client.admin.command('ping')
            self.db = self.client[db_name]
            logger.info(f"Connected to MongoDB - Database: {db_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self.client = None
            self.db = None
            # Re-raise to let the decorator handle it
            raise ConnectionError(f"MongoDB connection error: {str(e)}", e)
    
    def get_db(self):
        """
        Get the database instance.
        
        Returns:
            pymongo.database.Database: Database instance or None if not connected
        """
        if self.client is None or self.db is None:
            logger.warning("Database not connected. Attempting to connect...")
            try:
                # Attempt to connect if not already connected
                self.connect()
            except Exception as e:
                logger.error(f"Auto-connection attempt failed: {e}")
                return None
        return self.db
    
    def get_collection(self, collection_name):
        """
        Get a collection by name.
        
        Args:
            collection_name (str): Name of the collection
            
        Returns:
            pymongo.collection.Collection: Collection instance or None if not found
        """
        db = self.get_db()
        if db is None:
            logger.warning("Database not connected. Call connect() first.")
            return None
        return db[collection_name]
    
    @handle_operation_error
    @log_database_activity("index creation")
    def create_indexes(self):
        """
        Create required indexes for all collections.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            db = self.get_db()
            if db is None:
                logger.error("Database not connected. Cannot create indexes.")
                return False
                
            # User collection indexes
            db.users.create_index([("username", pymongo.ASCENDING)], unique=True)
            db.users.create_index([("email", pymongo.ASCENDING)], unique=True)
            db.users.create_index([("verificationToken", pymongo.ASCENDING)])
            db.users.create_index([("resetPasswordToken", pymongo.ASCENDING)])
            db.users.create_index([("subscription.status", pymongo.ASCENDING)])
            db.users.create_index([("subscription.endDate", pymongo.ASCENDING)])
            
            # Subscription plans indexes
            db.subscriptionPlans.create_index([("name", pymongo.ASCENDING)], unique=True)
            
            # Transactions indexes
            db.transactions.create_index([("userId", pymongo.ASCENDING)])
            db.transactions.create_index([("paymentId", pymongo.ASCENDING)], unique=True)
            db.transactions.create_index([("createdAt", pymongo.DESCENDING)])
            db.transactions.create_index([("status", pymongo.ASCENDING)])
            
            # Activity logs indexes
            db.activity_logs.create_index([("userId", pymongo.ASCENDING)])
            db.activity_logs.create_index([("timestamp", pymongo.DESCENDING)])
            db.activity_logs.create_index([("activityType", pymongo.ASCENDING)])
            
            # System logs indexes
            db.system_logs.create_index([("timestamp", pymongo.DESCENDING)])
            db.system_logs.create_index([("level", pymongo.ASCENDING)])
            
            # FAQ indexes
            db.faq.create_index([("category", pymongo.ASCENDING)])
            db.faq.create_index([("order", pymongo.ASCENDING)])
            
            # Settings indexes
            db.settings.create_index([("key", pymongo.ASCENDING)], unique=True)
            
            # IP addresses indexes
            if "ipAddresses" in db.list_collection_names():
                db.ipAddresses.create_index([("ip_address", pymongo.ASCENDING)], unique=True)
                db.ipAddresses.create_index([("status", pymongo.ASCENDING)])
                db.ipAddresses.create_index([("assigned_users", pymongo.ASCENDING)])
            
            # Proxy services indexes
            if "proxyServices" in db.list_collection_names():
                db.proxyServices.create_index([("name", pymongo.ASCENDING)], unique=True)
            
            # Auto farm configurations indexes
            if "auto_farm_configurations" in db.list_collection_names():
                db.auto_farm_configurations.create_index([("userId", pymongo.ASCENDING)], unique=True)
            
            # Trainer configurations indexes
            if "trainer_configurations" in db.list_collection_names():
                db.trainer_configurations.create_index([("userId", pymongo.ASCENDING)], unique=True)
            
            logger.info("All database indexes created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            # Re-raise to let the decorator handle it
            raise
    
    def disconnect(self):
        """Close the MongoDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("Disconnected from MongoDB")
    
    def test_connection(self):
        """
        Test the MongoDB connection.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
        if self.client is None:
            logger.warning("Client not initialized")
            return False
            
        try:
            # Ping the server to test connection
            self.client.admin.command('ping')
            logger.info("MongoDB connection test successful")
            return True
        except Exception as e:
            logger.error(f"MongoDB connection test failed: {e}")
            return False
    
    def __enter__(self):
        """Context manager enter."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
