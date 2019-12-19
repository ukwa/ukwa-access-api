FROM python:3.7

WORKDIR /usr/src/access

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn -c gunicorn.ini api:app


