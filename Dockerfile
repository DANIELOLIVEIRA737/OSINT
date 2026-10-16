FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ATLAS_HOST=0.0.0.0 PORT=8000 ATLAS_DATA_DIR=/data
WORKDIR /app
RUN groupadd --gid 10001 atlas && useradd --uid 10001 --gid atlas atlas \
    && mkdir /data && chown atlas:atlas /data
COPY app.py workspace.py intelligence.py cti.py ./
COPY static ./static
COPY integrations/cti ./integrations/cti
RUN chmod -R a+rX /app
USER atlas
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"
CMD ["python", "app.py"]
