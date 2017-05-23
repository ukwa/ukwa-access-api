FROM python:3-alpine

WORKDIR /usr/src/access

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn --error-logfile - --access-logfile - api:app


