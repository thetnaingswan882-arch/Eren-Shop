#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Run the Flask app
gunicorn app:app
