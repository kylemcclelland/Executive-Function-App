"""Generate a VAPID keypair for Web Push and print export lines. Run once per environment.

Prints the private key to the terminal only (never writes a file, never logs). Put the values
in the backend environment (Railway variables or backend/.env); commit neither.

    python scripts/generate_vapid_keys.py
"""

import base64

from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private = b64url(key.private_numbers().private_value.to_bytes(32, "big"))
    numbers = key.public_key().public_numbers()
    public = b64url(b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big"))
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:you@example.org  # set to a real contact address")


if __name__ == "__main__":
    main()
