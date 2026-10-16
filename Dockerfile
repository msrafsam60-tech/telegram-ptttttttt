FROM python:3.11-slim

WORKDIR /app

# System dependencies (যদি দরকার হয়)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Requirements আগে কপি করে ইনস্টল (cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# বাকি সব ফাইল কপি
COPY . .

# Bot চালাও
CMD ["python", "main.py"]
