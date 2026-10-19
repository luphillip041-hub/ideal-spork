FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY copybot ./copybot
COPY config.example.toml ./config.example.toml
# Default config; mount your own over it or tune with COPYBOT_* env vars.
COPY config.example.toml ./config.toml
RUN useradd --create-home bot && mkdir -p /app/state && chown bot /app/state
USER bot
VOLUME ["/app/state"]
ENV COPYBOT_CONFIG=/app/config.toml \
    COPYBOT_STATE_PATH=/app/state/bot_state.json
ENTRYPOINT ["python", "-m", "copybot"]
CMD ["run"]
