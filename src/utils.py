import struct
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class BufferReader:
  """Helper class to read binary data from a buffer"""

  def __init__(self, data: bytes):
    self.data = data
    self.pos = 0

  def read(self, format: str, offset: int = 0) -> tuple:
    """Read data at offset from current position with given format"""
    pos = self.pos + offset
    size = struct.calcsize(format)
    return struct.unpack(format, self.data[pos : pos + size])

  def read_uint8(self, offset: int = 0) -> int:
    """Read uint8_t at offset from current position"""
    pos = self.pos + offset
    return struct.unpack('B', self.data[pos : pos + 1])[0]

  def read_uint16(self, offset: int = 0, little_endian: bool = True) -> int:
    """Read uint16_t at offset from current position"""
    pos = self.pos + offset
    endian = '<' if little_endian else '>'
    return struct.unpack(f'{endian}H', self.data[pos : pos + 2])[0]

  def read_int32(self, offset: int = 0, little_endian: bool = True) -> int:
    """Read int32_t at offset from current position"""
    pos = self.pos + offset
    endian = '<' if little_endian else '>'
    return struct.unpack(f'{endian}i', self.data[pos : pos + 4])[0]

  def read_uint32(self, offset: int = 0, little_endian: bool = True) -> int:
    """Read uint32_t at offset from current position"""
    pos = self.pos + offset
    endian = '<' if little_endian else '>'
    return struct.unpack(f'{endian}I', self.data[pos : pos + 4])[0]

  def read_uint64(self, offset: int = 0, little_endian: bool = True) -> int:
    """Read uint64_t at offset from current position"""
    pos = self.pos + offset
    endian = '<' if little_endian else '>'
    return struct.unpack(f'{endian}Q', self.data[pos : pos + 8])[0]

  def read_bytes(self, offset: int = 0, length: int | None = None) -> bytes:
    """Read bytes at offset from current position"""
    pos = self.pos + offset
    if length is None:
      return self.data[pos:]
    return self.data[pos : pos + length]

  def advance(self, length: int):
    """Move position forward"""
    self.pos += length


def get_datetime(
  secs_since_1904: int | None, tz_offset: int = 0
) -> datetime | None:
  """Convert seconds since 1904-01-01 to a datetime object"""
  if not secs_since_1904:
    return None
  return datetime(1904, 1, 1) + timedelta(seconds=secs_since_1904 + tz_offset)


def check_signature(signature: bytes, expected: bytes):
  if signature != expected:
    raise ValueError(
      f'Invalid "{signature.decode()}" signature/header. '
      f'Expected: "{expected.decode()}"'
    )


def itlp_decrypt(encrypted_data: bytes, key: bytes) -> bytes:
  """
  Decrypts data using AES-128 in ECB mode with no padding,
  matching the logic of the provided C code.

  Args:
      encrypted_data (bytes): The input data to decrypt.
      key (bytes): The decryption key (Must be 16 bytes for AES-128).

  Returns:
      bytes: The decrypted data.
  """

  if len(key) != 16:
    raise ValueError(
      f'Key must be 16 bytes (128 bits) for AES-128. Provided: {len(key)}'
    )

  cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
  decryptor = cipher.decryptor()
  return decryptor.update(encrypted_data) + decryptor.finalize()
