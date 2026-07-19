FROM python:3.12-slim

WORKDIR /app

# dependances d'abord (cache Docker : ne se reinstalle que si requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# code applicatif
COPY . .

# main.py est le point d'entree (voir docker-compose.yml)
CMD ["python", "main.py"]
