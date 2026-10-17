FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY copybot ./copybot
COPY config.example.toml ./config.example.toml
RUN useradd --create-home bot && mkdir -p /app/state && chown bot /app/state
USER bot
VOLUME ["/app/state"]
ENV COPYBOT_CONFIG=/app/config.toml
ENTRYPOINT ["python", "-m", "copybot"]
CMD ["run"]
