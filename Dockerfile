# Base image with Python FROM python:3.11-slim

# Set environment variables ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Set working directory WORKDIR /app

# Install dependencies COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files COPY . .

# Expose any necessary port (Slack uses Socket Mode, so not required here)
EXPOSE 3000

# Run the app
CMD ["python", "app.py"]
