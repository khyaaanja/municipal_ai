from django.contrib import admin
from . import models as m

for name in dir(m):
    obj = getattr(m, name)
    try:
        if hasattr(obj, '_meta') and not obj._meta.abstract:
            admin.site.register(obj)
    except Exception:
        pass
