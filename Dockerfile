ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    locales-all

RUN mkdir -p /app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN python manage.py test
RUN python manage.py migrate
RUN python manage.py collectstatic --noinput


EXPOSE 8080

CMD ["gunicorn", "--bind", ":8080", "--workers", "2", "acbeo.wsgi"]
