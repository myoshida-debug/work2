import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonflow.settings')

application = get_wsgi_application()
