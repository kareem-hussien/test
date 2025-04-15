"""
IP Manager for Travian Whispers application.
This module handles IP assignment, rotation, and management for user isolation.
"""
import logging
import random
import time
import threading
from datetime import datetime, timedelta
from bson import ObjectId

# Configure logger
logger = logging.getLogger(__name__)

class IPManager:
    """
    Manages a pool of proxy IPs for user isolation.
    Handles assignment, rotation, and status tracking.
    """
    
    def __init__(self):
        """Initialize the IP Manager."""
        self.ip_collection = None
        self.ip_assignments = None
        self.lock = threading.RLock()  # Reentrant lock for thread safety
    
    def initialize(self):
        """
        Initialize database connections and ensure indexes.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            # Connect to database collections
            from database.mongodb import MongoDB
            
            db = MongoDB().get_db()
            if not db:
                logger.error("Failed to connect to database")
                return False
            
            self.ip_collection = db["ip_pool"]
            self.ip_assignments = db["ip_assignments"]
            
            # Create indexes
            self._create_indexes()
            
            logger.info("IP Manager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing IP Manager: {e}")
            return False
    
    def _create_indexes(self):
        """Create necessary indexes for IP management collections."""
        # Indexes for ip_pool collection
        self.ip_collection.create_index("ip_address", unique=True)
        self.ip_collection.create_index("status")
        self.ip_collection.create_index("provider")
        self.ip_collection.create_index("last_rotation")
        
        # Indexes for ip_assignments collection
        self.ip_assignments.create_index("userId", unique=True)
        self.ip_assignments.create_index("ipId")
        self.ip_assignments.create_index("assignedAt")
    
    def get_ip_for_user(self, user_id):
        """
        Get or assign an IP for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            dict: IP information or None if no IP available
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return None
        
        with self.lock:
            # Check if user already has an assigned IP
            existing_assignment = self.ip_assignments.find_one({"userId": user_id})
            
            if existing_assignment:
                # Get the IP details
                ip = self.ip_collection.find_one({"_id": existing_assignment["ipId"]})
                
                if not ip:
                    # IP record missing, clean up assignment and assign new IP
                    logger.warning(f"IP not found for existing assignment for user {user_id}")
                    self.ip_assignments.delete_one({"userId": user_id})
                    return self._assign_new_ip(user_id)
                
                # Check if IP is still valid
                if ip["status"] != "in_use":
                    logger.info(f"IP {ip['ip_address']} status changed to {ip['status']}, rotating for user {user_id}")
                    self.ip_assignments.delete_one({"userId": user_id})
                    return self._assign_new_ip(user_id)
                
                # Update last activity time
                self.ip_assignments.update_one(
                    {"userId": user_id},
                    {"$set": {"lastActivity": datetime.utcnow()}}
                )
                
                logger.debug(f"Retrieved existing IP {ip['ip_address']} for user {user_id}")
                return ip
            else:
                # User needs a new IP assignment
                return self._assign_new_ip(user_id)
    
    def _assign_new_ip(self, user_id):
        """
        Assign a new IP to a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            dict: IP information or None if no IP available
        """
        # Find an available IP
        available_ips = list(self.ip_collection.find(
            {"status": "available", "inUse": False},
            sort=[("last_rotation", 1)]  # Prioritize IPs that haven't been used recently
        ).limit(10))  # Get several options to choose from
        
        if not available_ips:
            logger.warning(f"No available IPs for user {user_id}")
            return None
        
        # Select a random IP from available ones to avoid predictable patterns
        selected_ip = random.choice(available_ips)
        ip_id = selected_ip["_id"]
        
        # Update IP status
        result = self.ip_collection.update_one(
            {"_id": ip_id, "status": "available", "inUse": False},  # Double-check to prevent race conditions
            {"$set": {
                "status": "in_use",
                "inUse": True,
                "lastAssigned": datetime.utcnow()
            }}
        )
        
        if result.modified_count == 0:
            logger.warning(f"Failed to update IP status for {selected_ip['ip_address']}")
            # Try again with a different IP
            available_ips.remove(selected_ip)
            if not available_ips:
                return None
            return self._assign_new_ip(user_id)
        
        # Create assignment record
        self.ip_assignments.insert_one({
            "userId": user_id,
            "ipId": ip_id,
            "assignedAt": datetime.utcnow(),
            "lastActivity": datetime.utcnow()
        })
        
        # Update IP document with assigned user
        self.ip_collection.update_one(
            {"_id": ip_id},
            {"$push": {"assigned_users": user_id}}
        )
        
        logger.info(f"Assigned IP {selected_ip['ip_address']} to user {user_id}")
        return selected_ip
    
    def rotate_ip_for_user(self, user_id):
        """
        Rotate a user's IP assignment.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            dict: New IP information or None if rotation failed
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return None
        
        with self.lock:
            # Get current assignment
            current_assignment = self.ip_assignments.find_one({"userId": user_id})
            
            if current_assignment:
                # Release the current IP
                self._release_ip(current_assignment["ipId"], user_id)
            
            # Assign a new IP
            return self._assign_new_ip(user_id)
    
    def _release_ip(self, ip_id, user_id):
        """
        Release an IP assignment.
        
        Args:
            ip_id (ObjectId): The IP ID
            user_id (str): The user ID
            
        Returns:
            bool: True if released successfully, False otherwise
        """
        try:
            # Get the IP
            ip = self.ip_collection.find_one({"_id": ip_id})
            
            if not ip:
                logger.warning(f"IP not found for ID {ip_id}")
                return False
            
            # Remove user from assigned_users
            self.ip_collection.update_one(
                {"_id": ip_id},
                {"$pull": {"assigned_users": user_id}}
            )
            
            # Check if there are other users assigned to this IP
            remaining_assignments = self.ip_assignments.count_documents({"ipId": ip_id, "userId": {"$ne": user_id}})
            
            if remaining_assignments == 0:
                # No other users, mark IP as available
                self.ip_collection.update_one(
                    {"_id": ip_id},
                    {"$set": {
                        "status": "available",
                        "inUse": False,
                        "last_rotation": datetime.utcnow()
                    }}
                )
            
            # Delete the assignment
            self.ip_assignments.delete_one({"userId": user_id, "ipId": ip_id})
            
            logger.info(f"Released IP {ip['ip_address']} from user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error releasing IP {ip_id} for user {user_id}: {e}")
            return False
    
    def report_ip_failure(self, ip_id, failure_type, details=None):
        """
        Report an IP failure.
        
        Args:
            ip_id (str): The IP ID
            failure_type (str): Type of failure (banned, connection_error, etc.)
            details (str, optional): Additional details about the failure
            
        Returns:
            bool: True if report processed successfully, False otherwise
        """
        if not self.ip_collection:
            logger.error("IP Manager not initialized")
            return False
        
        try:
            with self.lock:
                # Get the IP
                ip = self.ip_collection.find_one({"_id": ObjectId(ip_id)})
                
                if not ip:
                    logger.warning(f"IP not found for ID {ip_id}")
                    return False
                
                # Update failure count
                self.ip_collection.update_one(
                    {"_id": ObjectId(ip_id)},
                    {"$inc": {"failure_count": 1}}
                )
                
                # Add failure to history
                failure_record = {
                    "type": failure_type,
                    "details": details,
                    "timestamp": datetime.utcnow()
                }
                
                self.ip_collection.update_one(
                    {"_id": ObjectId(ip_id)},
                    {"$push": {"failure_history": failure_record}}
                )
                
                # Check if IP should be banned
                if failure_type == "banned" or failure_type == "suspected_ban":
                    return self.ban_ip(ip_id, f"Reported as {failure_type}: {details}")
                
                # Check if we've reached the failure threshold
                ip = self.ip_collection.find_one({"_id": ObjectId(ip_id)})
                if ip.get("failure_count", 0) >= 5:  # Arbitrary threshold
                    return self.ban_ip(ip_id, f"Exceeded failure threshold: {ip['failure_count']} failures")
                
                logger.info(f"Recorded {failure_type} failure for IP {ip['ip_address']}")
                return True
        except Exception as e:
            logger.error(f"Error reporting IP failure for {ip_id}: {e}")
            return False
    
    def ban_ip(self, ip_id, reason):
        """
        Ban an IP.
        
        Args:
            ip_id (str): The IP ID
            reason (str): Reason for banning
            
        Returns:
            bool: True if ban processed successfully, False otherwise
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return False
        
        try:
            with self.lock:
                # Get the IP
                ip = self.ip_collection.find_one({"_id": ObjectId(ip_id)})
                
                if not ip:
                    logger.warning(f"IP not found for ID {ip_id}")
                    return False
                
                # Update IP status
                self.ip_collection.update_one(
                    {"_id": ObjectId(ip_id)},
                    {"$set": {
                        "status": "banned",
                        "inUse": False,
                        "ban_reason": reason,
                        "banned_at": datetime.utcnow(),
                        "ban_count": ip.get("ban_count", 0) + 1
                    }}
                )
                
                # Get all users currently assigned to this IP
                assignments = list(self.ip_assignments.find({"ipId": ObjectId(ip_id)}))
                
                # Reassign all users to new IPs
                for assignment in assignments:
                    user_id = assignment["userId"]
                    logger.info(f"Reassigning user {user_id} due to banned IP {ip['ip_address']}")
                    
                    # Delete current assignment
                    self.ip_assignments.delete_one({"_id": assignment["_id"]})
                    
                    # Try to assign a new IP
                    self._assign_new_ip(user_id)
                
                logger.warning(f"Banned IP {ip['ip_address']} for reason: {reason}")
                return True
        except Exception as e:
            logger.error(f"Error banning IP {ip_id}: {e}")
            return False
    
    def get_ip_by_id(self, ip_id):
        """
        Get IP information by ID.
        
        Args:
            ip_id (str): The IP ID
            
        Returns:
            dict: IP information or None if not found
        """
        if not self.ip_collection:
            logger.error("IP Manager not initialized")
            return None
        
        try:
            return self.ip_collection.find_one({"_id": ObjectId(ip_id)})
        except Exception as e:
            logger.error(f"Error getting IP {ip_id}: {e}")
            return None
    
    def add_ip(self, ip_address, port, username=None, password=None, proxy_type="http"):
        """
        Add a new IP to the pool.
        
        Args:
            ip_address (str): The IP address
            port (int): The port number
            username (str, optional): Proxy username
            password (str, optional): Proxy password
            proxy_type (str): Type of proxy (http, socks5, etc.)
            
        Returns:
            str: IP ID if added successfully, None otherwise
        """
        if not self.ip_collection:
            logger.error("IP Manager not initialized")
            return None
        
        try:
            # Check if IP already exists
            existing_ip = self.ip_collection.find_one({"ip_address": ip_address})
            if existing_ip:
                logger.warning(f"IP {ip_address} already exists")
                return str(existing_ip["_id"])
            
            # Construct proxy URL
            if username and password:
                proxy_url = f"{proxy_type}://{username}:{password}@{ip_address}:{port}"
            else:
                proxy_url = f"{proxy_type}://{ip_address}:{port}"
            
            # Create IP document
            ip_doc = {
                "ip_address": ip_address,
                "port": port,
                "proxy_type": proxy_type,
                "username": username,
                "password": password,
                "proxy_url": proxy_url,
                "status": "available",
                "inUse": False,
                "added_at": datetime.utcnow(),
                "last_rotation": None,
                "last_check": None,
                "failure_count": 0,
                "ban_count": 0,
                "assigned_users": [],
                "provider": "manual",
                "failure_history": []
            }
            
            result = self.ip_collection.insert_one(ip_doc)
            
            logger.info(f"Added IP {ip_address} to pool with ID {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error adding IP {ip_address}: {e}")
            return None
    
    def remove_ip(self, ip_id):
        """
        Remove an IP from the pool.
        
        Args:
            ip_id (str): The IP ID
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return False
        
        try:
            with self.lock:
                # Get the IP
                ip = self.ip_collection.find_one({"_id": ObjectId(ip_id)})
                
                if not ip:
                    logger.warning(f"IP not found for ID {ip_id}")
                    return False
                
                # Get all assignments for this IP
                assignments = list(self.ip_assignments.find({"ipId": ObjectId(ip_id)}))
                
                # Reassign all users to new IPs
                for assignment in assignments:
                    user_id = assignment["userId"]
                    logger.info(f"Reassigning user {user_id} due to IP removal {ip['ip_address']}")
                    
                    # Delete current assignment
                    self.ip_assignments.delete_one({"_id": assignment["_id"]})
                    
                    # Try to assign a new IP
                    self._assign_new_ip(user_id)
                
                # Delete the IP
                self.ip_collection.delete_one({"_id": ObjectId(ip_id)})
                
                logger.info(f"Removed IP {ip['ip_address']} from pool")
                return True
        except Exception as e:
            logger.error(f"Error removing IP {ip_id}: {e}")
            return False
    
    def list_ips(self, status=None, provider=None, limit=100):
        """
        List IPs in the pool with optional filtering.
        
        Args:
            status (str, optional): Filter by status
            provider (str, optional): Filter by provider
            limit (int, optional): Maximum number of IPs to return
            
        Returns:
            list: List of IP information
        """
        if not self.ip_collection:
            logger.error("IP Manager not initialized")
            return []
        
        try:
            # Build query
            query = {}
            
            if status:
                query["status"] = status
            
            if provider:
                query["provider"] = provider
            
            # Execute query
            return list(self.ip_collection.find(query).limit(limit))
        except Exception as e:
            logger.error(f"Error listing IPs: {e}")
            return []
    
    def schedule_ip_rotation(self, max_age_hours=24):
        """
        Schedule rotation for IPs that have been used for too long.
        
        Args:
            max_age_hours (int): Maximum time in hours an IP should be used
            
        Returns:
            int: Number of IPs scheduled for rotation
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return 0
        
        try:
            # Calculate cutoff time
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            # Find all assignments older than the cutoff
            old_assignments = list(self.ip_assignments.find({
                "assignedAt": {"$lt": cutoff_time}
            }))
            
            rotation_count = 0
            
            # Process each assignment
            for assignment in old_assignments:
                user_id = assignment["userId"]
                ip_id = assignment["ipId"]
                
                logger.info(f"Rotating IP for user {user_id} due to age > {max_age_hours} hours")
                
                # Rotate IP
                if self.rotate_ip_for_user(user_id):
                    rotation_count += 1
            
            logger.info(f"Scheduled rotation for {rotation_count} IPs older than {max_age_hours} hours")
            return rotation_count
        except Exception as e:
            logger.error(f"Error scheduling IP rotation: {e}")
            return 0

    def get_user_ip_info(self, user_id):
        """
        Get information about a user's assigned IP.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            dict: Information about the user's IP assignment
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return None
        
        try:
            # Get assignment
            assignment = self.ip_assignments.find_one({"userId": user_id})
            
            if not assignment:
                return {
                    "has_ip": False,
                    "message": "No IP assigned"
                }
            
            # Get IP details
            ip = self.ip_collection.find_one({"_id": assignment["ipId"]})
            
            if not ip:
                return {
                    "has_ip": False,
                    "message": "IP record not found"
                }
            
            # Calculate assignment duration
            assignment_duration = datetime.utcnow() - assignment["assignedAt"]
            duration_hours = assignment_duration.total_seconds() / 3600
            
            return {
                "has_ip": True,
                "ip_address": self._mask_ip(ip["ip_address"]),  # Mask for security
                "assigned_at": assignment["assignedAt"],
                "duration_hours": round(duration_hours, 1),
                "status": ip["status"],
                "provider": ip["provider"],
                "last_activity": assignment.get("lastActivity")
            }
        except Exception as e:
            logger.error(f"Error getting IP info for user {user_id}: {e}")
            return {
                "has_ip": False,
                "message": f"Error: {str(e)}"
            }
    
    def _mask_ip(self, ip_address):
        """
        Mask an IP address for security.
        
        Args:
            ip_address (str): The IP address
            
        Returns:
            str: Masked IP address
        """
        if not ip_address or "." not in ip_address:
            return ip_address
        
        parts = ip_address.split(".")
        if len(parts) != 4:
            return ip_address
        
        return f"{parts[0]}.{parts[1]}.***.***"
    
    def get_stats(self):
        """
        Get statistics about the IP pool.
        
        Returns:
            dict: IP pool statistics
        """
        if not self.ip_collection or not self.ip_assignments:
            logger.error("IP Manager not initialized")
            return {}
        
        try:
            # Get counts by status
            available_count = self.ip_collection.count_documents({"status": "available"})
            in_use_count = self.ip_collection.count_documents({"status": "in_use"})
            banned_count = self.ip_collection.count_documents({"status": "banned"})
            
            # Get total counts
            total_ips = self.ip_collection.count_documents({})
            total_assignments = self.ip_assignments.count_documents({})
            
            # Calculate utilization
            utilization = 0
            if total_ips > 0:
                utilization = (in_use_count / total_ips) * 100
            
            return {
                "total_ips": total_ips,
                "available": available_count,
                "in_use": in_use_count,
                "banned": banned_count,
                "total_assignments": total_assignments,
                "utilization": round(utilization, 1)
            }
        except Exception as e:
            logger.error(f"Error getting IP stats: {e}")
            return {}
