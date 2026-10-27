FROM python:3.12-slim
RUN pip install --no-cache-dir kafka-python==2.2.15 fastavro==1.12.1
WORKDIR /app
COPY generate.py affinity.py schema_demo.py ./
COPY schemas ./schemas
ENTRYPOINT ["python", "generate.py"]
