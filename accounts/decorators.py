from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def role_required(allowed_roles):
    """
    Decorator for views that checks if the logged-in user belongs to allowed roles.
    If unauthorized, redirects with an error message and logs the attempt.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access this page.")
                return redirect('login')

            user_role = getattr(request.user, 'role', '')
            if request.user.is_superuser:
                # Superuser can access admin views
                user_role = 'SUPER_ADMIN'

            if user_role not in allowed_roles:
                messages.error(request, "Access Denied: You do not have permission to view this resource.")
                # Redirect to appropriate dashboard
                if user_role == 'SUPER_ADMIN':
                    return redirect('admin_dashboard')
                elif user_role == 'TRAINER':
                    return redirect('trainer_dashboard')
                elif user_role == 'STUDENT':
                    return redirect('student_dashboard')
                return redirect('login')

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def admin_required(view_func):
    return role_required(['SUPER_ADMIN'])(view_func)


def trainer_required(view_func):
    return role_required(['TRAINER', 'SUPER_ADMIN'])(view_func)


def student_required(view_func):
    return role_required(['STUDENT'])(view_func)
