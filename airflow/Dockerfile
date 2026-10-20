FROM apache/airflow:3.3.2-python3.12

# Extra Python packages for the pipeline. Installing "apache-airflow==<version>"
# alongside them pins Airflow so pip can't accidentally up/downgrade it
# (the pattern recommended in the official Airflow Docker docs).
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
