"""Liga Premier API."""

# Usa el almacen de certificados del sistema operativo en lugar del de certifi.
# Necesario cuando un antivirus o proxy corporativo inspecciona HTTPS (p. ej.
# Norton Web/Mail Shield): Windows confia en su certificado raiz, certifi no.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - opcional
    pass
