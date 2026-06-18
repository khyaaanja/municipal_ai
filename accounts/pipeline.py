def set_default_role(backend, user, response, *args, **kwargs):
    if user and not user.role:
        user.role = 'citizen'
        user.save(update_fields=['role'])
