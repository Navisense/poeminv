FROM python:3.10
WORKDIR /app/
COPY requirements requirements
RUN pip install -r requirements/base.txt -r requirements/test.txt
COPY . .
