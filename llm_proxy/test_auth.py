"""测试设备认证"""
import time
from llm_proxy.auth import DeviceAuth


def test_signature_generation():
    """测试签名生成"""
    device_id = "ocl-test123"
    device_secret = "test_secret_key"
    timestamp = int(time.time())

    signature = DeviceAuth.generate_signature(device_id, timestamp, device_secret)
    print(f"Device ID: {device_id}")
    print(f"Timestamp: {timestamp}")
    print(f"Signature: {signature}")
    print()

    is_valid = DeviceAuth.verify_signature(device_id, timestamp, signature, device_secret)
    print(f"Signature valid: {is_valid}")
    assert is_valid, "Signature should be valid"


def test_signature_verification():
    """测试签名验证"""
    device_id = "ocl-test123"
    device_secret = "test_secret_key"
    timestamp = int(time.time())

    # 正确的签名
    correct_signature = DeviceAuth.generate_signature(device_id, timestamp, device_secret)
    assert DeviceAuth.verify_signature(device_id, timestamp, correct_signature, device_secret)

    # 错误的签名
    wrong_signature = "wrong_signature"
    assert not DeviceAuth.verify_signature(device_id, timestamp, wrong_signature, device_secret)

    # 过期的时间戳
    old_timestamp = timestamp - 400  # 超过 300 秒容差
    old_signature = DeviceAuth.generate_signature(device_id, old_timestamp, device_secret)
    assert not DeviceAuth.verify_signature(device_id, old_timestamp, old_signature, device_secret)

    print("All signature verification tests passed!")


def generate_test_request():
    """生成测试请求示例"""
    device_id = "ocl-3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e"
    device_secret = "your_device_secret_here"
    timestamp = int(time.time())

    signature = DeviceAuth.generate_signature(device_id, timestamp, device_secret)
    print("=== Test Request Headers ===")
    print(f"X-Device-Id: {device_id}")
    print(f"X-Timestamp: {timestamp}")
    print(f"Authorization: HMAC-SHA256 {signature}")
    print()

    print("=== cURL Command ===")
    print(f"""curl -X POST http://localhost:8764/llm/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "X-Device-Id: {device_id}" \\
  -H "X-Timestamp: {timestamp}" \\
  -H "Authorization: HMAC-SHA256 {signature}" \\
  -d '{{
    "messages": [{{"role": "user", "content": "你好"}}],
    "model": "glm-4",
    "provider": "zhipu"
  }}'""")


if __name__ == "__main__":
    print("=== Testing Device Authentication ===\n")
    test_signature_generation()
    print()
    test_signature_verification()
    print()
    generate_test_request()
