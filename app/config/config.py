# app/config/config.py
#
# ⚠️ Este archivo asume que ya tenés OLLAMA_URL y OLLAMA_MODEL definidos.
# Agregá las variables nuevas (MONGO_*, JWT_*) a tu config.py existente,
# no reemplaces el archivo entero -- capaz tenés otras cosas ahí que no vi.

import os

# FIX: sin esto, un archivo .env en la raíz del proyecto NUNCA se carga
# al entorno del proceso -- os.getenv() solo lee variables que YA están
# en el entorno (las que pusiste con `set`/`export`, o las que Render
# inyecta directamente). load_dotenv() es lo que efectivamente lee el
# archivo .env y las agrega al entorno antes de que el resto del
# archivo intente leerlas con os.getenv(). En Render esto no hace
# falta (las variables de entorno se configuran directo en el panel),
# pero para desarrollo local con un .env es imprescindible.
from dotenv import load_dotenv
load_dotenv()

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

# ---- Nuevas: recuperación de contraseña / email ----
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# ---- Nueva: búsqueda web (Tavily) ----
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")