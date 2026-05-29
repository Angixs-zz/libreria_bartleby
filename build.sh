#!/usr/bin/env bash
# exit on error
set -o errexit

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar migraciones de la base de datos
python manage.py migrate

# Recolectar archivos estáticos
python manage.py collectstatic --no-input
