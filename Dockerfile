# SovereignGuard — reproducible container.
#
# Deliberately based on slim-bookworm with no build toolchain: the ML core is
# pure numpy, so there is nothing to compile. The image builds in seconds and
# has a small attack surface, which matters for something positioned as a
# security tool.
FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.title="SovereignGuard" \
      org.opencontainers.image.description="AI Red Team / Blue Team payment-security laboratory" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SG_HOST=0.0.0.0 \
    SG_PORT=8000 \
    # Keep SQLite off any bind-mounted volume: network and virtiofs mounts
    # frequently lack the POSIX locking SQLite needs, which surfaces as
    # "disk I/O error" on first write.
    SG_STATE_DIR=/var/lib/sovereignguard

WORKDIR /app

# Dependencies first, so edits to source do not invalidate the layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sovereignguard/ ./sovereignguard/
COPY experiments/ ./experiments/
COPY data/attack_taxonomy.json ./data/attack_taxonomy.json
COPY sg.py README.md LICENSE ./

RUN mkdir -p /var/lib/sovereignguard /app/data/synthetic /app/data/attacks \
             /app/data/evaluation /app/models /app/experiments/results \
 && useradd --create-home --shell /usr/sbin/nologin sg \
 && chown -R sg:sg /app /var/lib/sovereignguard
USER sg

# Fail the build if the package cannot import or the taxonomy is inconsistent.
RUN python -c "from sovereignguard import taxonomy; taxonomy.validate(); \
import sovereignguard.pipeline; print('SovereignGuard import + taxonomy OK')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

ENTRYPOINT ["python", "sg.py"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
