import asyncio
import os
import time
from collections import deque
from datetime import datetime, timezone

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GroqRateLimiter:
    """
    Limitador de 3 dimensiones para la capa gratis de Groq: RPM, TPM y
    RPD. Los tres importan -- Groq corta por la que se llene primero, y
    en la práctica RPD (o TPM con prompts largos) suele llenarse antes
    que RPM.

    FIX (por qué los defaults son conservadores, no los límites reales
    de Groq): las fuentes públicas sobre el límite diario de la capa
    gratis NO son consistentes entre sí para modelos "high-quota" como
    llama-3.1-8b-instant (se ven cifras de ~1.000 y de ~14.400 RPD
    según la fuente/fecha). En vez de asumir el número más generoso y
    arriesgarnos a un 429 en producción, seteamos un default chico
    (900/día) y dejamos override por env var. Confirmá el número real
    para tu cuenta en console.groq.com/settings/limits (o mirando los
    headers x-ratelimit-* de una respuesta real) y ajustá
    GROQ_RPD_LIMIT si te sobra margen.

    Los límites de RPM/TPM sí están bien documentados (30 RPM / ~6000
    TPM para los modelos high-quota), así que esos defaults van más
    ajustados a lo real, con un colchón de seguridad chico.

    Todo en memoria de proceso -- no en Mongo. Esto es intencional para
    RPM/TPM (son ventanas de 60s, un restart de Render no las rompe de
    forma relevante). Para RPD el trade-off es distinto: si Render
    reinicia el proceso (free tier lo hace por inactividad), el
    contador diario se resetea a 0 antes de tiempo. Es un riesgo
    aceptado a propósito -- el peor caso es "un rato del día podemos
    gastar más cupo del que en verdad nos queda", no un fallo de
    seguridad. Si en algún momento importa que sea exacto, hay que
    persistir el contador en Mongo (colección chica: {date, count}).
    """

    def __init__(
        self,
        rpm_limit: int | None = None,
        tpm_limit: int | None = None,
        rpd_limit: int | None = None,
    ):
        self.rpm_limit = rpm_limit or int(os.getenv("GROQ_RPM_LIMIT", "28"))
        self.tpm_limit = tpm_limit or int(os.getenv("GROQ_TPM_LIMIT", "5500"))
        self.rpd_limit = rpd_limit or int(os.getenv("GROQ_RPD_LIMIT", "900"))

        self._request_timestamps: deque[float] = deque()
        self._token_events: deque[tuple[float, int]] = deque()

        self._daily_count = 0
        self._daily_date = self._today()

        self._lock = asyncio.Lock()

    def _today(self) -> str:
        # UTC porque Groq resetea RPD a medianoche UTC, no hora local.
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def estimate_tokens(messages: list[dict]) -> int:
        """
        Estimación aproximada (no un tokenizer real): ~4 caracteres por
        token en español es razonable como cota superior informal.
        Alcanza para un margen de seguridad, no para facturación.
        """
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        return max(1, total_chars // 4)

    async def acquire(self, estimated_tokens: int) -> tuple[bool, str | None]:
        """
        Intenta reservar cupo para un request de ~estimated_tokens.
        Devuelve (True, None) si hay lugar y ya quedó reservado, o
        (False, motivo) si algún límite se llenaría. No bloquea ni
        espera -- la decisión de qué hacer si no hay cupo (fallback a
        Ollama, esperar, avisar al usuario) es responsabilidad de quien
        llama.
        """
        async with self._lock:
            now = time.monotonic()

            self._evict_older_than(self._request_timestamps, now, 60)
            self._evict_token_events_older_than(now, 60)

            today = self._today()
            if today != self._daily_date:
                self._daily_date = today
                self._daily_count = 0

            if self._daily_count >= self.rpd_limit:
                return False, "rpd"

            if len(self._request_timestamps) >= self.rpm_limit:
                return False, "rpm"

            current_tpm = sum(tokens for _, tokens in self._token_events)
            if current_tpm + estimated_tokens > self.tpm_limit:
                return False, "tpm"

            # Reservamos cupo ya mismo (no después de la respuesta) --
            # si dos requests llegan casi juntos, el segundo tiene que
            # ver el cupo ya comprometido por el primero, no una foto
            # vieja.
            self._request_timestamps.append(now)
            self._token_events.append((now, estimated_tokens))
            self._daily_count += 1

            return True, None

    def _evict_older_than(self, dq: deque, now: float, window_seconds: int):
        while dq and now - dq[0] > window_seconds:
            dq.popleft()

    def _evict_token_events_older_than(self, now: float, window_seconds: int):
        while self._token_events and now - self._token_events[0][0] > window_seconds:
            self._token_events.popleft()

    def status(self) -> dict:
        """Para debug/observabilidad -- ver el estado actual del cupo."""
        now = time.monotonic()
        self._evict_older_than(self._request_timestamps, now, 60)
        self._evict_token_events_older_than(now, 60)
        current_tpm = sum(tokens for _, tokens in self._token_events)

        return {
            "rpm_used": len(self._request_timestamps),
            "rpm_limit": self.rpm_limit,
            "tpm_used": current_tpm,
            "tpm_limit": self.tpm_limit,
            "rpd_used": self._daily_count,
            "rpd_limit": self.rpd_limit,
        }