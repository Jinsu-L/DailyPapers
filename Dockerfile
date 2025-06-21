# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# 환경변수로 config 경로 등 주입 가능
ENV CONFIG_PATH=/app/config/sources.yaml

# The main command to run when the container starts
# The --date argument will be provided by the GitHub Action
CMD ["python", "main.py"]