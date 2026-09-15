from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f'/login/?next={request.path}')
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


staff_required        = role_required('staff', 'official', 'admin')
official_required     = role_required('official', 'admin')
admin_required        = role_required('admin')
mayor_required        = role_required('mayor', 'admin')
chairperson_required  = role_required('chairperson', 'mayor', 'admin')
