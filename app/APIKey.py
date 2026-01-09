import secrets
import string
import hmac
import hashlib
import json
import os
import platform
from datetime import datetime, timedelta, UTC
from enum import Enum, Flag, auto
from typing import Optional, List, Dict, Union, Set


# ===================== 跨平台文件锁 =====================
class FileLock:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.lock_fd = None
        self.is_windows = platform.system() == "Windows"

    def __enter__(self):
        if self.is_windows:
            import msvcrt

            self.lock_fd = open(self.file_path, "a+")
            msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            self.lock_fd = open(self.file_path, "a+")
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_fd:
            if self.is_windows:
                import msvcrt

                msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
            self.lock_fd.close()
        return False


# ===================== 权限枚举（显式指定数值，避免auto()兼容问题）=====================
class APIPermission(Flag):
    """APIKey 权限枚举（显式指定整数值，解决转换兼容问题）"""

    NONE = 0  # 无权限
    READ = 1  # 只读（显式赋值1）
    WRITE = 2  # 只写（显式赋值2）
    DELETE = 4  # 删除（显式赋值4）
    READ_WRITE = READ | WRITE  # 组合权限（1+2=3，自动推导）
    FULL_ACCESS = READ | WRITE | DELETE  # 7

    @classmethod
    def from_str(cls, permission_str: str) -> "APIPermission":
        if not permission_str:
            return cls.NONE
        permission_map = {
            "read": cls.READ,
            "write": cls.WRITE,
            "delete": cls.DELETE,
            "read_write": cls.READ_WRITE,
            "full_access": cls.FULL_ACCESS,
            "none": cls.NONE,
        }
        permissions = cls.NONE
        for part in permission_str.lower().split(","):
            part = part.strip()
            if part in permission_map:
                permissions |= permission_map[part]
        return permissions


# ===================== APIKey 管理类（核心修复序列化逻辑）=====================
class APIKeyManager:
    def __init__(
        self,
        salt: str = "your-global-secret-salt-2025",
        default_length: int = 32,
        default_prefix: Optional[str] = "sk-",
        use_safe_chars: bool = True,
        include_symbols: bool = False,
        persist_file: str = "./apikey_store.m5",
    ):
        self.salt = salt
        self.default_length = default_length
        self.default_prefix = default_prefix
        self.use_safe_chars = use_safe_chars
        self.include_symbols = include_symbols
        self.persist_file = persist_file
        self.apikey_store: Dict[str, Dict] = self._load_from_file()

    def _get_charset(self) -> str:
        letters = string.ascii_letters
        digits = string.digits
        if self.use_safe_chars:
            letters = (
                letters.replace("l", "")
                .replace("L", "")
                .replace("O", "")
                .replace("o", "")
            )
            digits = digits.replace("0", "").replace("1", "")
        charset = letters + digits
        if self.include_symbols:
            charset += "!@#$%^&*()_+-=[]{}|;:,.<>?~"
        if len(charset) == 0:
            raise ValueError("字符集不能为空")
        return charset

    def _hash_apikey(self, apikey: str) -> str:
        return hmac.new(
            self.salt.encode("utf-8"), apikey.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _serialize_value(self, value):
        """
        核心修复：改用枚举的 _value_ 属性获取整数值
        """
        try:
            if isinstance(value, datetime):
                return value.isoformat()
            # 终极修复：Flag枚举用 _value_ 属性取整数值（兼容所有Python版本）
            elif isinstance(value, APIPermission):
                return value._value_  # 代替int(value)，这是枚举的标准取值方式
            elif isinstance(value, (int, float, str, bool, type(None))):
                return value
            else:
                return str(value)
        except Exception as e:
            raise RuntimeError(
                f"序列化失败（值：{value}，类型：{type(value)}）：{str(e)}"
            )

    def _deserialize_value(self, key, value):
        try:
            if key in ["expire_at", "created_at"] and value is not None:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            elif key == "permissions" and value is not None:
                # 兼容整数/字符串，转成int后再实例化枚举
                val_int = int(value) if isinstance(value, str) else value
                return APIPermission(val_int)
            else:
                return value
        except Exception as e:
            raise RuntimeError(f"反序列化失败（键：{key}，值：{value}）：{str(e)}")

    def _load_from_file(self) -> Dict[str, Dict]:
        if not os.path.exists(self.persist_file):
            return {}
        try:
            with FileLock(self.persist_file):
                with open(self.persist_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            apikey_store = {}
            for hashed_key, meta in raw_data.items():
                deserialized_meta = {}
                for k, v in meta.items():
                    deserialized_meta[k] = self._deserialize_value(k, v)
                apikey_store[hashed_key] = deserialized_meta
            print(f"✅ 从 {self.persist_file} 加载 {len(apikey_store)} 条记录")
            return apikey_store
        except json.JSONDecodeError:
            print(f"⚠️ {self.persist_file} 格式错误，初始化空存储")
            return {}
        except PermissionError:
            raise PermissionError(f"❌ 无权限读取 {self.persist_file}")
        except Exception as e:
            raise RuntimeError(f"❌ 加载失败：{str(e)}")

    def _save_to_file(self):
        try:
            serialized_data = {}
            for hashed_key, meta in self.apikey_store.items():
                serialized_meta = {}
                for k, v in meta.items():
                    serialized_meta[k] = self._serialize_value(v)
                serialized_data[hashed_key] = serialized_meta

            with FileLock(self.persist_file):
                temp_file = f"{self.persist_file}.tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(serialized_data, f, indent=2, ensure_ascii=False)
                os.replace(temp_file, self.persist_file)
        except PermissionError:
            raise PermissionError(f"❌ 无权限写入 {self.persist_file}")
        except Exception as e:
            raise RuntimeError(f"❌ 保存失败：{str(e)}")

    def generate_apikey(
        self,
        expire_at: Optional[Union[datetime, timedelta]] = None,
        permissions: Union[APIPermission, str] = APIPermission.NONE,
        user_id: Optional[str] = None,
        length: Optional[int] = None,
        prefix: Optional[str] = None,
    ) -> str:
        length = length or self.default_length
        prefix = prefix or self.default_prefix
        if length < 8:
            raise ValueError("APIKey长度≥8位")

        # 强制转换为APIPermission实例
        if isinstance(permissions, str):
            permissions = APIPermission.from_str(permissions)
        if not isinstance(permissions, APIPermission):
            raise TypeError(
                f"权限必须是APIPermission或字符串，当前：{type(permissions)}"
            )

        # 处理过期时间
        now = datetime.now(UTC)
        if isinstance(expire_at, timedelta):
            expire_at = now + expire_at
        elif isinstance(expire_at, datetime):
            expire_at = (
                expire_at.replace(tzinfo=UTC) if expire_at.tzinfo is None else expire_at
            )
        elif expire_at is not None:
            raise TypeError("expire_at仅支持datetime/timedelta/None")

        # 生成APIKey
        charset = self._get_charset()
        random_part = "".join(secrets.choice(charset) for _ in range(length))
        raw_apikey = f"{prefix}{random_part}" if prefix else random_part

        # 存储元信息
        hashed_apikey = self._hash_apikey(raw_apikey)
        self.apikey_store[hashed_apikey] = {
            "raw_apikey": raw_apikey,
            "expire_at": expire_at,
            "permissions": permissions,
            "created_at": now,
            "user_id": user_id,
            "is_active": True,
        }
        self._save_to_file()
        return raw_apikey

    def validate_apikey(
        self, api_key: str, required_permissions: Optional[APIPermission] = None
    ) -> Dict[str, Union[bool, str, APIPermission, datetime]]:
        hashed_apikey = self._hash_apikey(api_key)
        if hashed_apikey not in self.apikey_store:
            return {
                "is_valid": False,
                "is_expired": False,
                "has_permission": False,
                "message": "APIKey不存在",
            }

        meta = self.apikey_store[hashed_apikey]
        if not meta["is_active"]:
            return {
                "is_valid": False,
                "is_expired": False,
                "has_permission": False,
                "message": "APIKey已禁用",
            }

        # 检查过期
        now = datetime.now(UTC)
        if meta["expire_at"] and now > meta["expire_at"]:
            return {
                "is_valid": False,
                "is_expired": True,
                "has_permission": False,
                "message": f"APIKey已过期（{meta['expire_at']}）",
            }

        # 检查权限
        has_perm = True
        if required_permissions:
            has_perm = (
                meta["permissions"] & required_permissions
            ) == required_permissions
            if not has_perm:
                return {
                    "is_valid": True,
                    "is_expired": False,
                    "has_permission": False,
                    "message": f"权限不足（当前：{meta['permissions']}，需要：{required_permissions}）",
                }

        return {
            "is_valid": True,
            "is_expired": False,
            "has_permission": has_perm,
            "message": "校验通过",
            "permissions": meta["permissions"],
            "expire_at": meta["expire_at"],
            "created_at": meta["created_at"],
            "user_id": meta["user_id"],
        }

    def disable_apikey(self, raw_apikey: str) -> bool:
        hashed = self._hash_apikey(raw_apikey)
        if hashed not in self.apikey_store:
            return False
        self.apikey_store[hashed]["is_active"] = False
        self._save_to_file()
        return True

    def delete_apikey(self, raw_apikey: str) -> bool:
        hashed = self._hash_apikey(raw_apikey)
        if hashed not in self.apikey_store:
            return False
        del self.apikey_store[hashed]
        self._save_to_file()
        return True

    def get_apikey_meta(self, raw_apikey: str) -> Optional[Dict]:
        return self.apikey_store.get(self._hash_apikey(raw_apikey))


# ===================== 测试 =====================
if __name__ == "__main__":
    # 初始化
    manager = APIKeyManager(salt="test-salt-123", persist_file="./apikey_store.m5")

    # 生成带组合权限的APIKey
    apikey = manager.generate_apikey(
        expire_at=timedelta(days=7),
        permissions=APIPermission.READ_WRITE,
        user_id="test_user",
        prefix="sk-",
        length=24,
    )
    print(f"生成的APIKey：{apikey}")

    # 校验
    res = manager.validate_apikey(apikey, APIPermission.READ)
    print(f"校验结果：{res}")

    # 禁用
    manager.disable_apikey(apikey)
    res = manager.validate_apikey(apikey, APIPermission.READ)
    print(f"禁用后校验：{res}")

    # 重启验证
    new_manager = APIKeyManager(salt="test-salt-123", persist_file="./apikey_store.m5")
    res = new_manager.validate_apikey(apikey, APIPermission.READ)
    print(f"重启后校验：{res}")
