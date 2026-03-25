"""MySQL 数据库客户端"""
import json
import aiomysql
from typing import Optional, Any, List, Dict


class MemoryClient:
    """
    本地内存数据库（用于无 MySQL 配置时的联调）。
    数据在进程重启后清空，仅供开发测试使用。
    """

    def __init__(self):
        self._tables: Dict[str, List[dict]] = {}

    def _table(self, name: str) -> List[dict]:
        return self._tables.setdefault(name, [])

    async def get(self, table: str, filters: dict = None) -> Any:
        rows = self._table(table)
        if not filters:
            return list(rows)
        result = []
        for row in rows:
            if all(row.get(k) == v for k, v in filters.items()):
                result.append(row)
        return result

    async def post(self, table: str, data: dict) -> Any:
        self._table(table).append(dict(data))
        return [dict(data)]

    async def patch(self, table: str, filters: dict, data: dict) -> Any:
        updated = []
        for row in self._table(table):
            if all(row.get(k) == v for k, v in filters.items()):
                row.update(data)
                updated.append(dict(row))
        return updated

    async def delete(self, table: str, filters: dict) -> Any:
        rows = self._table(table)
        self._tables[table] = [
            r for r in rows
            if not all(r.get(k) == v for k, v in filters.items())
        ]
        return {"success": True}


class MySQLClient:
    """MySQL 数据库客户端"""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._pool: Optional[aiomysql.Pool] = None

    async def _get_pool(self) -> aiomysql.Pool:
        if self._pool is None:
            self._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                autocommit=True,
                charset="utf8mb4",
            )
        return self._pool

    @staticmethod
    def _build_where(filters: dict | None) -> tuple:
        if not filters:
            return "", []
        conditions = " AND ".join(f"`{k}` = %s" for k in filters.keys())
        return f" WHERE {conditions}", list(filters.values())

    @staticmethod
    def _serialize(data: dict) -> dict:
        result = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                result[k] = json.dumps(v, ensure_ascii=False)
            else:
                result[k] = v
        return result

    async def get(self, table: str, filters: dict = None) -> Any:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    where, params = self._build_where(filters)
                    await cur.execute(f"SELECT * FROM `{table}`{where}", params)
                    return list(await cur.fetchall())
        except Exception as e:
            return {"error": str(e)}

    async def post(self, table: str, data: dict) -> Any:
        try:
            serialized = self._serialize(data)
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    cols = ", ".join(f"`{k}`" for k in serialized.keys())
                    placeholders = ", ".join(["%s"] * len(serialized))
                    await cur.execute(
                        f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})",
                        list(serialized.values()),
                    )
                    return [data]
        except Exception as e:
            return {"error": str(e)}

    async def patch(self, table: str, filters: dict, data: dict) -> Any:
        try:
            serialized = self._serialize(data)
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sets = ", ".join(f"`{k}` = %s" for k in serialized.keys())
                    where, where_params = self._build_where(filters)
                    await cur.execute(
                        f"UPDATE `{table}` SET {sets}{where}",
                        list(serialized.values()) + where_params,
                    )
                    return [data]
        except Exception as e:
            return {"error": str(e)}

    async def delete(self, table: str, filters: dict) -> Any:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    where, params = self._build_where(filters)
                    await cur.execute(f"DELETE FROM `{table}`{where}", params)
                    return {"success": True}
        except Exception as e:
            return {"error": str(e)}


# 全局数据库客户端
db: Optional[Any] = None


def init_db(host: str, port: int, user: str, password: str, database: str):
    """初始化数据库客户端；host 或 user 为空时自动使用内存模式"""
    global db
    if host and user:
        db = MySQLClient(host, port, user, password, database)
        print("[DB] 使用 MySQL 数据库")
    else:
        db = MemoryClient()
        print("[DB] MySQL 未配置，使用内存数据库（仅限本地联调）")


def get_db() -> Any:
    """获取数据库客户端"""
    return db
