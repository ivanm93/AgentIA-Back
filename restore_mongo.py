# restore_mongo.py
#
# Restaura un backup generado por backup_mongo.py. Requiere confirmación
# explícita porque BORRA los datos actuales de cada colección antes de
# restaurar (si no, quedarían documentos viejos mezclados con los
# restaurados, generando duplicados o inconsistencias).
#
# Uso:
#   python restore_mongo.py backups/20260705_143000

import sys
import os

from pymongo import MongoClient
from bson import json_util

from app.config.config import MONGO_URI, MONGO_DB_NAME


COLLECTIONS_TO_RESTORE = ["users", "profiles", "conversations", "messages"]


def run_restore(backup_dir: str):
    if not os.path.isdir(backup_dir):
        print(f"❌ No existe la carpeta: {backup_dir}")
        return

    print(f"\n⚠️  ADVERTENCIA: esto va a BORRAR los datos actuales de las")
    print(f"   colecciones {COLLECTIONS_TO_RESTORE} en la base '{MONGO_DB_NAME}'")
    print(f"   y reemplazarlos por lo que hay en: {backup_dir}\n")

    confirm = input("Escribí RESTAURAR para confirmar: ")
    if confirm != "RESTAURAR":
        print("Cancelado -- no se tocó nada.")
        return

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]

    print(f"\n=== Restaurando desde {backup_dir} ===\n")

    for collection_name in COLLECTIONS_TO_RESTORE:
        file_path = os.path.join(backup_dir, f"{collection_name}.json")

        if not os.path.exists(file_path):
            print(f"  {collection_name}: no hay archivo de backup, se salta")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            documents = json_util.loads(f.read())

        collection = db[collection_name]
        collection.delete_many({})  # limpiar antes de restaurar

        if documents:
            collection.insert_many(documents)

        print(f"  {collection_name}: {len(documents)} documentos restaurados")

    print("\n✅ Restauración completa.")
    client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python restore_mongo.py <carpeta_de_backup>")
        print("Ejemplo: python restore_mongo.py backups/20260705_143000")
        sys.exit(1)

    run_restore(sys.argv[1])