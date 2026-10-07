"""Limitador de peticiones en memoria (ventana deslizante).

Vive en el proceso: con varios workers cada uno lleva su propia cuenta. Para
limites compartidos entre instancias habria que mover el estado a Redis.
"""

import time
from collections import deque
from threading import Lock


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float, max_keys: int = 50_000) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events.get(key)
        if events is None:
            if len(self._events) >= self.max_keys:
                self._evict(now)
            events = self._events[key] = deque()
        while events and events[0] <= now - self.window:
            events.popleft()
        return events

    def _evict(self, now: float) -> None:
        """Evita que la memoria crezca sin limite con muchas IPs distintas."""
        for key in [k for k, ev in self._events.items() if not ev or ev[-1] <= now - self.window]:
            del self._events[key]
        if len(self._events) >= self.max_keys:
            self._events.clear()

    def retry_after(self, key: str) -> int:
        """Segundos que faltan para poder intentar de nuevo (0 si no esta bloqueado)."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            if len(events) < self.max_events:
                return 0
            return max(1, int(events[0] + self.window - now) + 1)

    def hit(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def check_and_hit(self, key: str) -> int:
        """Registra el evento si hay cupo; si no, devuelve los segundos de espera."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            if len(events) >= self.max_events:
                return max(1, int(events[0] + self.window - now) + 1)
            events.append(now)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


class LoginThrottle:
    """Proteccion contra fuerza bruta en el login.

    - Por IP+correo: `max_attempts` fallos en la ventana bloquean esa cuenta desde esa IP.
    - Por IP: 4x ese numero frena el "password spraying" (probar muchos correos).
    Un login exitoso limpia el contador de la cuenta.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.by_account = SlidingWindowLimiter(max_attempts, window_seconds)
        self.by_ip = SlidingWindowLimiter(max_attempts * 4, window_seconds)

    @staticmethod
    def _account(ip: str, email: str) -> str:
        return f"{ip}|{email.strip().lower()}"

    def retry_after(self, ip: str, email: str) -> int:
        return max(self.by_account.retry_after(self._account(ip, email)), self.by_ip.retry_after(ip))

    def failed(self, ip: str, email: str) -> None:
        self.by_account.hit(self._account(ip, email))
        self.by_ip.hit(ip)

    def succeeded(self, ip: str, email: str) -> None:
        self.by_account.reset(self._account(ip, email))
