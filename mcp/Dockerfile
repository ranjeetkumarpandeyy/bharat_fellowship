FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/agent_mcp

WORKDIR /app

EXPOSE 8101

CMD ["python", "-m", "agent_mcp.citizen_server"]