# Point d'entrée Vercel : expose l'instance WSGI `app`.
from app import create_app

app = create_app()
