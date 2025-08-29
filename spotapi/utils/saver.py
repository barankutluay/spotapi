"""
Saver module for session storage.
Supports JSON, SQLite, MongoDB, and Redis backends.
Thread-safe for parallel access.
"""

import atexit
import json
import os
import sqlite3
from typing import Any, List, Mapping

import pymongo
import redis
from readerwriterlock import rwlock

from spotapi.exceptions import SaverError
from spotapi.spotapitypes.interfaces import SaverProtocol

__all__ = ["JSONSaver", "MongoSaver", "RedisSaver", "SqliteSaver", "SaverProtocol"]


class JSONSaver(SaverProtocol):
    __slots__ = ("path", "rwlock", "rlock", "wlock")

    def __init__(self, path: str = "sessions.json") -> None:
        self.path = path
        self.rwlock = rwlock.RWLockFairD()
        self.rlock = self.rwlock.gen_rlock()
        self.wlock = self.rwlock.gen_wlock()

    def __str__(self) -> str:
        return "JSONSaver()"

    def _read_file(self) -> List[Mapping[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r") as f:
            content = f.read()
            return json.loads(content) if content.strip() else []

    def _write_file(self, data: List[Mapping[str, Any]]) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=4)

    def save(self, data: List[Mapping[str, Any]], overwrite: bool = False) -> None:
        if not data:
            raise ValueError("No data to save")

        with self.wlock:
            current = [] if overwrite else self._read_file()
            identifiers = {d["identifier"] for d in data}
            current = [
                item for item in current if item.get("identifier") not in identifiers
            ]
            current.extend(data)
            self._write_file(current)

    def load(
        self, query: Mapping[str, Any], raise_on_collision: bool = True
    ) -> Mapping[str, Any]:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        with self.rlock:
            data = self._read_file()
            matches = [
                item for item in data if all(item[k] == v for k, v in query.items())
            ]
            if raise_on_collision and len(matches) > 1:
                raise SaverError("Collision found")
            if not matches:
                raise SaverError("Item not found")
            return matches[0]

    def load_all(self) -> List[Mapping[str, Any]]:
        with self.rlock:
            return self._read_file()

    def delete(
        self,
        query: Mapping[str, Any],
        all_instances: bool = True,
        clear_all: bool = False,
    ) -> None:
        with self.wlock:
            if clear_all:
                return self._write_file([])
            if not query:
                raise ValueError("Query dictionary cannot be empty")
            data = self._read_file()
            new_data = []
            for item in data:
                if all(item[k] == v for k, v in query.items()):
                    if not all_instances:
                        continue
                else:
                    new_data.append(item)
            self._write_file(new_data)


class SqliteSaver(SaverProtocol):
    __slots__ = ("path", "conn", "cursor", "rwlock", "rlock", "wlock")

    def __init__(self, path: str = "sessions.db") -> None:
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                identifier TEXT PRIMARY KEY NOT NULL,
                password TEXT NOT NULL,
                cookies TEXT
            )
            """
        )
        atexit.register(
            lambda: (
                (self.cursor.close() if getattr(self, "cursor", None) else None),
                (self.conn.close() if getattr(self, "conn", None) else None),
            )
        )
        self.rwlock = rwlock.RWLockFairD()
        self.rlock = self.rwlock.gen_rlock()
        self.wlock = self.rwlock.gen_wlock()

    def __str__(self) -> str:
        return "SqliteSaver()"

    def _build_where_clause(self, query: Mapping[str, Any]) -> tuple[str, list]:
        sql = " AND ".join(f"{k}=?" for k in query)
        params = list(query.values())
        return sql, params

    def save(self, data: List[Mapping[str, Any]], overwrite: bool = False) -> None:
        if not data:
            raise ValueError("No data to save")
        with self.wlock:
            try:
                if overwrite:
                    self.cursor.execute("DELETE FROM sessions")
                    self.conn.commit()
                for item in data:
                    self.cursor.execute(
                        "INSERT INTO sessions VALUES (?, ?, ?)",
                        (
                            item["identifier"],
                            item["password"],
                            json.dumps(item["cookies"]),
                        ),
                    )
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                raise SaverError(str(e))

    def load(self, query: Mapping[str, Any], **kwargs) -> Mapping[str, Any]:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        with self.rlock:
            sql, params = self._build_where_clause(query)
            self.cursor.execute(f"SELECT * FROM sessions WHERE {sql}", tuple(params))
            result = self.cursor.fetchall()
            if not result:
                raise SaverError("Item not found")
            identifier, password, cookies = result[0]
            return {
                "identifier": identifier,
                "password": password,
                "cookies": json.loads(cookies) if cookies else {},
            }

    def load_all(self) -> List[Mapping[str, Any]]:
        with self.rlock:
            self.cursor.execute("SELECT identifier, password, cookies FROM sessions")
            rows = self.cursor.fetchall()
            return [
                {"identifier": i, "password": p, "cookies": json.loads(c) if c else {}}
                for i, p, c in rows
            ]

    def delete(self, query: Mapping[str, Any], **kwargs) -> None:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        with self.wlock:
            sql, params = self._build_where_clause(query)
            self.cursor.execute(f"DELETE FROM sessions WHERE {sql}", tuple(params))
            self.conn.commit()


class MongoSaver(SaverProtocol):
    __slots__ = ("conn", "database", "collection")

    def __init__(
        self,
        host: str = "mongodb://localhost:27017/",
        database_name: str = "spotify",
        collection: str = "sessions",
    ) -> None:
        self.conn = pymongo.MongoClient(host)
        self.database = self.conn[database_name]
        self.collection = self.database[collection]
        atexit.register(self.conn.close)

    def __str__(self) -> str:
        return "MongoSaver()"

    def save(self, data: List[Mapping[str, Any]], **kwargs) -> None:
        if not data:
            raise ValueError("No data to save")
        self.collection.insert_many(data)

    def load(self, query: Mapping[str, Any], **kwargs) -> Mapping[str, Any]:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        result = self.collection.find_one(query)
        if result is None:
            raise SaverError("Item not found")
        return result

    def load_all(self) -> List[Mapping[str, Any]]:
        return list(self.collection.find({}))

    def delete(self, query: Mapping[str, Any], **kwargs) -> None:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        self.collection.delete_one(query)


class RedisSaver(SaverProtocol):
    __slots__ = ("client", "rwlock", "rlock", "wlock")

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        self.client = redis.StrictRedis(host=host, port=port, db=db)
        atexit.register(self.client.close)
        self.rwlock = rwlock.RWLockFairD()
        self.rlock = self.rwlock.gen_rlock()
        self.wlock = self.rwlock.gen_wlock()

    def __str__(self) -> str:
        return "RedisSaver()"

    def save(self, data: List[Mapping[str, Any]], **kwargs) -> None:
        if not data:
            raise ValueError("No data to save")
        with self.wlock:
            for item in data:
                self.client.set(item["identifier"], json.dumps(item))

    def load(self, query: Mapping[str, Any], **kwargs) -> Mapping[str, Any]:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        identifier = query.get("identifier")
        if not identifier:
            raise ValueError("Identifier is required for Redis lookup")
        with self.rlock:
            result = self.client.get(identifier)
            if not result:
                raise SaverError("Item not found")
            return json.loads(result)

    def load_all(self) -> List[Mapping[str, Any]]:
        result = []
        with self.rlock:
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor=cursor, match="*", count=100)
                for key in keys:
                    value = self.client.get(key)
                    if value:
                        result.append(json.loads(value))
                if cursor == 0:
                    break
        return result

    def delete(self, query: Mapping[str, Any], **kwargs) -> None:
        if not query:
            raise ValueError("Query dictionary cannot be empty")
        identifier = query.get("identifier")
        if not identifier:
            raise ValueError("Identifier is required for Redis lookup")
        with self.wlock:
            self.client.delete(identifier)
