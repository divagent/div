alembic init alembic 
alembic revision --autogenerate -m "initial schema"


alembic revision -m "baseline"
alembic stamp head
alembic current 
alembic heads
alembic upgrade head
