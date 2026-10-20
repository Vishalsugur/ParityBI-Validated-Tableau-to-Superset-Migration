"""Pipeline code for the Service Desk BI migration project.

The Airflow DAG (airflow/dags/servicedesk_bi_pipeline.py) is a thin wrapper:
every step lives in this package so it can be tested and run without Airflow
(see pipeline/cli.py).
"""
