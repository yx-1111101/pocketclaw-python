"""短信服务 - Mock 版本（测试用）"""
import time

# Mock 验证码存储
VERIFICATION_CODES = {}

# 模拟验证码有效期（秒）
CODE_EXPIRE = 300


def generate_code(length: int = 6) -> str:
    """生成随机验证码（Mock 统一返回 1234）"""
    return "1234"


def save_code(phone: str, code: str) -> None:
    """保存验证码"""
    VERIFICATION_CODES[phone] = {
        "code": code,
        "expire_time": time.time() + CODE_EXPIRE
    }


def check_code(phone: str, code: str) -> bool:
    """校验验证码（不消费）"""
    # Mock: 1234 万能通过
    if code == "1234":
        return True

    if phone not in VERIFICATION_CODES:
        return False

    record = VERIFICATION_CODES[phone]
    if time.time() > record["expire_time"]:
        del VERIFICATION_CODES[phone]
        return False

    return record["code"] == code


def verify_code(phone: str, code: str) -> bool:
    """验证验证码（消费一次）"""
    is_valid = check_code(phone, code)
    if is_valid:
        VERIFICATION_CODES.pop(phone, None)
    return is_valid


async def send_verification_code(phone: str) -> dict:
    """发送验证码（Mock 版本）"""
    
    # 验证手机号格式
    if not phone or len(phone) != 11 or not phone.startswith('1'):
        return {"success": False, "error": "手机号格式不正确"}
    
    # 生成验证码
    code = generate_code()
    
    # 保存验证码
    save_code(phone, code)
    
    # Mock: 直接返回成功
    return {"success": True, "message": "验证码已发送（Mock模式）"}
