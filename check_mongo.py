import asyncio
from app.config.config import MONGO_URI, MONGO_DB_NAME
from app.db.mongo import MongoDatabase, get_collection


async def check():
    print(f"MONGO_URI configurada: {MONGO_URI}")
    print(f"MONGO_DB_NAME configurada: {MONGO_DB_NAME}")

    ok = await MongoDatabase.ping()
    print(f"Ping a Mongo: {'OK' if ok else 'FALLÓ'}")

    if not ok:
        return

    # Listar TODAS las bases de datos visibles desde esta conexión
    db_names = await MongoDatabase._client.list_database_names()
    print(f"\nBases de datos visibles desde esta conexión: {db_names}")

    profiles = get_collection("profiles")
    messages = get_collection("messages")

    profiles_count = await profiles.count_documents({})
    messages_count = await messages.count_documents({})

    print(f"\nDocumentos en 'profiles' (db={MONGO_DB_NAME}): {profiles_count}")
    print(f"Documentos en 'messages' (db={MONGO_DB_NAME}): {messages_count}")

    if profiles_count > 0:
        doc = await profiles.find_one({})
        print(f"\nEjemplo de documento en 'profiles':\n{doc}")


if __name__ == "__main__":
    asyncio.run(check())