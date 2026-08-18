FROM python:3.12-slim

WORKDIR /app

# tesseract-ocr is a system binary, not a Python package -- pytesseract is
# just a wrapper that shells out to it, so it has to be installed here too
# or receipt extraction will fail at runtime with TesseractNotFoundError.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# persists across restarts via the compose file's volumes
RUN mkdir -p /app/data /app/uploads/receipts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
