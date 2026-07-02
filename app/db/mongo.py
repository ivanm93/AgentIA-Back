# app/db/mongo.py
#
# Conexión centralizada a MongoDB. Un solo cliente para toda la app
# (motor maneja el pool de conexiones internamente, no hay que crear un
# cliente nuevo por request).

from motor.motor_asyncio import AsyncIOMotorClient
from app.config.config import MONGO_URI, MONGO_DB_NAME


class MongoDatabase:

    _client: AsyncIOMotorClient = None
    _db = None

    @classmethod
    def connect(cls):
        if cls._client is None:
            cls._client = AsyncIOMotorClient(MONGO_URI)
            cls._db = cls._client[MONGO_DB_NAME]

    @classmethod
    def get_db(cls):
        if cls._db is None:
            cls.connect()
        return cls._db

    @classmethod
    def close(cls):
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None

    @classmethod
    async def ping(cls) -> bool:
        """Usado por /health para chequear que Mongo responde."""
        try:
            db = cls.get_db()
            await db.command("ping")
            return True
        except Exception:
            return False


def get_collection(name: str):
    return MongoDatabase.get_db()[name]