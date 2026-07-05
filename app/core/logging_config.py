# app/core/logging_config.py
#
# Logging estructurado -- reemplaza los print() sueltos que había en
# varios archivos (emotion_detector, summarizer, email_service, etc).
# Usa el módulo `logging` de la librería estándar, sin dependencias
# nuevas.
#
# Por qué esto es mejor que print():
# - Nivel de severidad (INFO/WARNING/ERROR) -- en Render podés filtrar
#   por nivel en vez de leer todo el chorro de texto.
# - Incluye automáticamente timestamp, módulo de origen, y nivel en cada
#   línea -- con print() había que armar eso a mano en cada mensaje.
# - Se puede subir/bajar el nivel general con una sola variable de
#   entorno (LOG_LEVEL), sin tocar código.

import logging
import os


def configure_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)