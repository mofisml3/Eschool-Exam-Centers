"""uvicorn ecsa.api.main:app --reload"""
from ecsa.api.app import create_app

app = create_app()
