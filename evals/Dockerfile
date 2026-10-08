FROM python:3.11-slim
WORKDIR /evals
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /evals
CMD ["python", "run_evals.py"]
