FROM python:3.12-slim
WORKDIR /app

# Libs da app + agente OpenTelemetry. O bootstrap detecta flask/requests/psycopg2
# e instala as instrumentacoes certas. O codigo da app NAO tem nada de OTel.
RUN pip install --no-cache-dir flask requests psycopg2-binary \
        opentelemetry-distro opentelemetry-exporter-otlp && \
    opentelemetry-bootstrap -a install

ARG APP
COPY ${APP}/app.py /app/app.py

CMD ["opentelemetry-instrument", "python", "app.py"]
