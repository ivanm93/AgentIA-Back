# app/config/config.py
#
# ⚠️ Este archivo asume que ya tenés OLLAMA_URL y OLLAMA_MODEL definidos.
# Agregá las variables nuevas (MONGO_*, JWT_*) a tu config.py existente,
# no reemplaces el archivo entero -- capaz tenés otras cosas ahí que no vi.

import os

# ---- Ya deberían existir en tu config.py ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# ---- Nuevas: MongoDB ----
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "apoyo_emocional")

# ---- Nuevas: JWT / Auth ----
# ⚠️ CRÍTICO: cambiar JWT_SECRET_KEY antes de producción. Este valor
# nunca debe subirse a git -- usar variable de entorno real en producción.
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CAMBIAR-ESTO-antes-de-produccion-nunca-usar-el-default"
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24 * 7  # 7 días
