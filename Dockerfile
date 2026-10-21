# ---- Stage 1: generate pydantic v2 models from OpenAPI ----
FROM python:3.12-slim AS generator
RUN pip install --no-cache-dir datamodel-code-generator==0.25.6
WORKDIR /local
COPY src/main/resources/openapi/openapi.yaml ./openapi.yaml
RUN datamodel-codegen \
    --input openapi.yaml \
    --input-file-type openapi \
    --output /local/models.py \
    --output-model-type pydantic_v2.BaseModel

# ---- Stage 2: runtime ----
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=generator /local/models.py /app/src/app/generated/models.py
COPY src /app/src

ENV PYTHONPATH=/app/src
WORKDIR /app/src

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
