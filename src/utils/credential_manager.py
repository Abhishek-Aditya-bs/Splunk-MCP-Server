"""
Credential Manager for Splunk MCP Server

Handles secure decryption of passwords using machine-specific identifiers.
Passwords can only be decrypted on the same machine where they were encrypted.
"""

import os
import uuid
import hashlib
import platform
from base64 import urlsafe_b64encode, urlsafe_b64decode
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CredentialManager:
    """Manages secure credential decryption for Splunk connections."""
    
    def __init__(self):
        """Initialize the credential manager."""
        self._machine_id = self._get_machine_id()
        self._machine_hash = hashlib.sha256(self._machine_id.encode()).hexdigest()[:16]
    
    def _get_machine_id(self) -> str:
        """Generate a unique machine identifier using hardware information.
        
        This works across Windows, Mac, and Linux by using:
        - MAC address (network hardware identifier)
        - Current username (works on all OS)
        - Home directory path (cross-platform)
        - Platform info (OS and architecture)
        """
        # Get MAC address - works on all platforms
        mac = hex(uuid.getnode()).encode('utf-8')
        
        # Get username - cross-platform
        # Windows uses USERNAME, Unix-like systems use USER
        username = os.environ.get('USER', os.environ.get('USERNAME', 'default'))
        username_bytes = username.encode('utf-8')
        
        # Get home directory - os.path.expanduser works on all platforms
        # Windows: C:\Users\username
        # Mac/Linux: /home/username or /Users/username
        home = os.path.expanduser('~')
        home_bytes = home.encode('utf-8')
        
        # Get platform info - works on all OS
        platform_info = f"{platform.system()}-{platform.machine()}"
        platform_bytes = platform_info.encode('utf-8')
        
        # Combine all identifiers
        machine_id = mac + username_bytes + home_bytes + platform_bytes
        
        # Create a consistent hash
        return hashlib.sha256(machine_id).hexdigest()
    
    def _derive_key(self, salt: bytes) -> bytes:
        """Derive an encryption key from the machine ID and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        
        key = urlsafe_b64encode(kdf.derive(self._machine_id.encode()))
        return key
    
    def decrypt_password(self, encrypted_data: Dict[str, str]) -> str:
        """
        Decrypt a password that was encrypted with this machine's ID.
        
        Args:
            encrypted_data: Dictionary containing:
                - password_encrypted: The encrypted password
                - password_salt: The salt used for key derivation
                - machine_hash: Hash to verify same machine
        
        Returns:
            The decrypted password
            
        Raises:
            ValueError: If decryption fails or wrong machine
        """
        # Verify this is the same machine
        if encrypted_data.get('machine_hash') != self._machine_hash:
            raise ValueError(
                "Cannot decrypt password: This password was encrypted on a different machine. "
                "Please re-run encrypt_password.py on this machine."
            )
        
        try:
            # Decode the salt and encrypted password
            salt = urlsafe_b64decode(encrypted_data['password_salt'].encode())
            encrypted = urlsafe_b64decode(encrypted_data['password_encrypted'].encode())
            
            # Derive the key using the same salt
            key = self._derive_key(salt)
            
            # Decrypt the password
            f = Fernet(key)
            decrypted = f.decrypt(encrypted)
            
            # Clear sensitive data from memory (Python will garbage collect)
            password = decrypted.decode('utf-8')
            
            return password
            
        except InvalidToken:
            raise ValueError(
                "Failed to decrypt password. The encrypted data may be corrupted "
                "or the machine environment has changed."
            )
        except Exception as e:
            raise ValueError(f"Failed to decrypt password: {str(e)}")
    
    def get_credentials(self, splunk_config: Dict) -> Dict[str, str]:
        """
        Get decrypted credentials from Splunk configuration.
        
        Args:
            splunk_config: Splunk configuration dictionary
            
        Returns:
            Dictionary with 'username' and 'password' keys
            
        Raises:
            ValueError: If credentials not found or decryption fails
        """
        if 'username' not in splunk_config:
            raise ValueError("No username found in configuration")
        
        # Check if we have encrypted password
        if 'password_encrypted' in splunk_config:
            encrypted_data = {
                'password_encrypted': splunk_config['password_encrypted'],
                'password_salt': splunk_config['password_salt'],
                'machine_hash': splunk_config.get('machine_hash', '')
            }
            
            password = self.decrypt_password(encrypted_data)
            
            return {
                'username': splunk_config['username'],
                'password': password
            }
        
        # Fallback to plain password (not recommended)
        elif 'password' in splunk_config:
            import warnings
            warnings.warn(
                "Using plain text password. "
                "Please use encrypt_password.py for secure storage.",
                UserWarning
            )
            return {
                'username': splunk_config['username'],
                'password': splunk_config['password']
            }
        else:
            raise ValueError("No password found in configuration")


# Singleton instance
credential_manager = CredentialManager()
