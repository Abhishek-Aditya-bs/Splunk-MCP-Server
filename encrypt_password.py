#!/usr/bin/env python3
"""
Standalone Password Encryption Utility for Splunk MCP Server

This script encrypts passwords using machine-specific identifiers.
The encrypted password can only be decrypted on the same machine.

Usage:
    python encrypt_password.py
"""

import os
import sys
import uuid
import hashlib
import getpass
import platform
from base64 import urlsafe_b64encode, urlsafe_b64decode
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2


def get_machine_id():
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


def derive_key(machine_id: str, salt: bytes = None) -> tuple:
    """Derive an encryption key from the machine ID."""
    if salt is None:
        salt = os.urandom(16)
    
    kdf = PBKDF2(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    
    key = urlsafe_b64encode(kdf.derive(machine_id.encode()))
    return key, salt


def encrypt_password(password: str) -> dict:
    """Encrypt a password using machine-specific key."""
    machine_id = get_machine_id()
    key, salt = derive_key(machine_id)
    
    f = Fernet(key)
    encrypted = f.encrypt(password.encode())
    
    return {
        'encrypted': urlsafe_b64encode(encrypted).decode('utf-8'),
        'salt': urlsafe_b64encode(salt).decode('utf-8'),
        'machine_hash': hashlib.sha256(machine_id.encode()).hexdigest()[:16]
    }


def decrypt_password(encrypted_data: dict) -> str:
    """Decrypt a password (for testing purposes only)."""
    machine_id = get_machine_id()
    
    # Verify this is the same machine
    current_hash = hashlib.sha256(machine_id.encode()).hexdigest()[:16]
    if current_hash != encrypted_data['machine_hash']:
        raise ValueError("Cannot decrypt: Different machine or environment")
    
    salt = urlsafe_b64decode(encrypted_data['salt'].encode())
    key, _ = derive_key(machine_id, salt)
    
    f = Fernet(key)
    encrypted = urlsafe_b64decode(encrypted_data['encrypted'].encode())
    decrypted = f.decrypt(encrypted)
    
    return decrypted.decode('utf-8')


def main():
    """Main function to encrypt passwords."""
    print("=" * 60)
    print("SPLUNK MCP SERVER - PASSWORD ENCRYPTION UTILITY")
    print("=" * 60)
    print()
    print("This utility encrypts your Splunk password using machine-specific")
    print("identifiers. The encrypted password can ONLY be decrypted")
    print("on this exact machine.")
    print()
    print("IMPORTANT: The same credentials will be used for both UAT and PROD.")
    print("Only the indexes differ between environments.")
    print()
    print("-" * 60)
    
    # Get username
    print("\nEnter Splunk credentials:")
    print("-" * 30)
    
    username = input("Enter username: ").strip()
    if not username:
        print("Username cannot be empty. Exiting.")
        sys.exit(1)
    
    # Get password
    password = getpass.getpass("Enter password: ")
    if not password:
        print("Password cannot be empty. Exiting.")
        sys.exit(1)
    
    # Confirm password
    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("Passwords don't match. Exiting.")
        sys.exit(1)
    
    # Encrypt the password
    encrypted_data = encrypt_password(password)
    
    # Test decryption to ensure it works
    try:
        decrypted = decrypt_password(encrypted_data)
        if decrypted != password:
            print("ERROR: Encryption verification failed!")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Could not verify encryption: {e}")
        sys.exit(1)
    
    print("✓ Password encrypted successfully")
    
    # Display the results
    print("\n" + "=" * 60)
    print("ENCRYPTED CREDENTIALS")
    print("=" * 60)
    print("\nUpdate the following in your config.yml file:")
    print("\n```yaml")
    print("splunk:")
    print(f"  username: {username}")
    print(f"  password_encrypted: {encrypted_data['encrypted']}")
    print(f"  password_salt: {encrypted_data['salt']}")
    print(f"  machine_hash: {encrypted_data['machine_hash']}")
    print("```")
    print("\n" + "=" * 60)
    print("IMPORTANT NOTES:")
    print("=" * 60)
    print("1. These encrypted passwords will ONLY work on this machine")
    print("2. Update config.yml with the values above")
    print("3. If you move to a different machine, re-run this script")
    print("4. Keep a secure backup of your actual password")
    print()


if __name__ == "__main__":
    main()
