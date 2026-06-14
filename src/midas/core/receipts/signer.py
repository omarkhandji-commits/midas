"""Ed25519 signing for receipts.

The signing key can be injected (tests, deterministic seeds) or loaded from the OS
keychain via `keyring` (production). The key never enters model context.
"""

from __future__ import annotations

from nacl import encoding, signing
from nacl.exceptions import BadSignatureError

_KEYRING_SERVICE = "midas"
_KEYRING_USER = "receipt-signing-key"


class Signer:
    def __init__(self, signing_key: signing.SigningKey) -> None:
        self._sk = signing_key
        self._vk = signing_key.verify_key

    @classmethod
    def generate(cls) -> Signer:
        return cls(signing.SigningKey.generate())

    @classmethod
    def from_hex_seed(cls, seed_hex: str) -> Signer:
        return cls(signing.SigningKey(seed_hex.encode("ascii"), encoder=encoding.HexEncoder))

    @property
    def public_key_hex(self) -> str:
        return self._vk.encode(encoder=encoding.HexEncoder).decode()

    def seed_hex(self) -> str:
        return self._sk.encode(encoder=encoding.HexEncoder).decode()

    def sign(self, message: str) -> str:
        return self._sk.sign(message.encode("utf-8")).signature.hex()

    @staticmethod
    def verify(public_key_hex: str, message: str, sig_hex: str) -> bool:
        try:
            vk = signing.VerifyKey(public_key_hex.encode("ascii"), encoder=encoding.HexEncoder)
            vk.verify(message.encode("utf-8"), bytes.fromhex(sig_hex))
            return True
        except (BadSignatureError, ValueError):
            return False


def load_or_create_keyring_signer(
    service: str = _KEYRING_SERVICE, username: str = _KEYRING_USER
) -> Signer:
    """Load the signing seed from the OS keychain, creating one on first use."""
    import keyring

    seed = keyring.get_password(service, username)
    if seed is None:
        signer = Signer.generate()
        keyring.set_password(service, username, signer.seed_hex())
        return signer
    return Signer.from_hex_seed(seed)
