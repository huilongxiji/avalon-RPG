"""密码哈希及离线哈希工具。此模块不会连接数据库或创建账号。"""

from __future__ import annotations

import base64
import binascii
import getpass
import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128 or not password.strip():
        raise ValueError("密码须为 12～128 个字符，不能全为空格")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not ITERATIONS <= int(rounds) <= 2_000_000:
            return False
        salt_bytes = base64.b64decode(salt, validate=True)
        expected_bytes = base64.b64decode(expected, validate=True)
        if len(salt_bytes) != 16 or len(expected_bytes) != 32:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, int(rounds))
        return hmac.compare_digest(digest, expected_bytes)
    except (ValueError, TypeError, binascii.Error):
        return False


def main() -> None:
    password = getpass.getpass("输入新密码（12～128 个字符，不回显）：")
    if password != getpass.getpass("再次输入："):
        raise SystemExit("两次密码不一致，未生成哈希")
    try:
        print(hash_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
