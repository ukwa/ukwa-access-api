FROM python:3.6

WORKDIR /usr/src/access

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn --timeout 300 --error-logfile - --access-logfile - --bind 0.0.0.0:8000 api:app


