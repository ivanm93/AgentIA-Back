# app/core/rate_limiter.py
#
# Limiter compartido -- separado en su propio módulo para que tanto
# main.py como los routers puedan importarlo sin depender uno del otro
# (si el limiter viviera dentro de main.py, los routers no podrían
# importarlo sin crear un import circular).
#
# Por defecto, slowapi guarda los contadores en memoria del proceso.
# Esto alcanza para un solo servidor (como tu deploy actual en Render,
# instancia única). Si en algún momento escalás a múltiples instancias,
# vas a necesitar un backend compartido (Redis) para que el límite
# aplique across todas las instancias, no una por una.

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)