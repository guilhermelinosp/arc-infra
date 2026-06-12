FROM python:3.12-alpine
RUN apk add --no-cache kubectl curl
COPY controller.py /app/controller.py
EXPOSE 8080
CMD ["python", "/app/controller.py"]
