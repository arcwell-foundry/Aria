"""
Encryption utilities for sensitive data like API keys.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC) from the cryptography library.
The master key should be stored in APOLLO_ENCRYPTION_KEY environment variable.
"""

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Service for encrypting/decrypting sensitive data like customer API keys.

    Uses Fernet symmetric encryption. The master key is loaded from environment.
    Supports key rotation via version tracking.
    """

    def __init__(self, master_key: Optional[str] = None, key_version: int = 1):
        """
        Initialize encryption service.

        Args:
            master_key: Base64-encoded Fernet key. If None, loads from APOLLO_ENCRYPTION_KEY env var.
            key_version: Version of the key for rotation support.
        """
        self._key_version = key_version
        self._fernet: Optional[Fernet] = None

        if master_key:
            try:
                # Ensure key is properly formatted for Fernet
                key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
                if len(key_bytes) == 44:  # Standard Fernet key length when base64 encoded
                    self._fernet = Fernet(key_bytes)
                else:
                    # Try to use as-is if it's already a valid key
                    self._fernet = Fernet(key_bytes)
            except Exception as e:
                logger.error(f"Invalid encryption key format: {e}")
                self._fernet = None
        else:
            # Load from environment
            env_key = os.getenv("APOLLO_ENCRYPTION_KEY", "")
            if env_key:
                try:
                    self._fernet = Fernet(env_key.encode())
                except Exception as e:
                    logger.error(f"Failed to load APOLLO_ENCRYPTION_KEY from environment: {e}")
                    self._fernet = None

    @property
    def is_available(self) -> bool:
        """Check if encryption service is properly configured."""
        return self._fernet is not None

    @property
    def key_version(self) -> int:
        """Current key version for rotation tracking."""
        return self._key_version

    def encrypt(self, plaintext: str) -> Optional[str]:
        """
        Encrypt a string value.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded encrypted string, or None if encryption failed.
        """
        if not self._fernet:
            logger.warning("Encryption service not configured - cannot encrypt")
            return None

        if not plaintext:
            return None

        try:
            encrypted = self._fernet.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return None

    def decrypt(self, ciphertext: str) -> Optional[str]:
        """
        Decrypt an encrypted string.

        Args:
            ciphertext: Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string, or None if decryption failed.
        """
        if not self._fernet:
            logger.warning("Encryption service not configured - cannot decrypt")
            return None

        if not ciphertext:
            return None

        try:
            decrypted = self._fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Decryption failed: invalid token (wrong key or corrupted data)")
            return None
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet key.

        Returns:
            Base64-encoded Fernet key suitable for storage in environment.
        """
        return Fernet.generate_key().decode()


# Singleton instance for app-wide use
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get or create the singleton encryption service."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_api_key(api_key: str) -> Optional[str]:
    """Convenience function to encrypt an API key."""
    return get_encryption_service().encrypt(api_key)


def decrypt_api_key(encrypted_key: str) -> Optional[str]:
    """Convenience function to decrypt an API key."""
    return get_encryption_service().decrypt(encrypted_key)
