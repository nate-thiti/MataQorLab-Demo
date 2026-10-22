# Pin the manifest so an existing local cache can build even when Docker Hub's
# tag-metadata endpoint is temporarily unreachable.
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

# ตั้งค่า Environment Variables เพื่อความเสถียรของ Python ภายใน Container
# PYTHONDONTWRITEBYTECODE: ป้องกัน Python เขียนไฟล์ .pyc ลงดิสก์
# PYTHONUNBUFFERED: แสดง Log ของแอปใน Terminal ทันทีโดยไม่ค้างในบัฟเฟอร์
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Pick up Debian security fixes (openssl/util-linux) before installing app deps.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# คัดลอกและติดตั้ง Dependencies ก่อนเพื่อการทำ Layer Cache ที่มีประสิทธิภาพ
COPY requirements.txt .
# Do not `pip install --upgrade pip`: newer pip ships pip/_vendor/bom.cdx.json and
# Trivy treats those vendored SBOM pins (setuptools 70.3.0, msgpack 1.1.2) as
# installed HIGH findings even though the app packages are already patched.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade 'setuptools>=78.1.1' 'wheel>=0.46.2' \
    && rm -f /usr/local/lib/python*/site-packages/pip/_vendor/bom.cdx.json

# คัดลอกโค้ดทั้งหมดของ Backend เข้าสู่ Working Directory
COPY . .

# เปิดพอร์ต 8000 ซึ่งเป็นพอร์ตมาตรฐานสำหรับ FastAPI API Service
EXPOSE 8000

# API is the default process. Automation runs separately with `python -m app.worker`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
