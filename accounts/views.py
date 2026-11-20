from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from portal.models import AuditLog

def portal_login(request):
    """
    Unified portal login page. Validates user and redirects automatically
    to Super Admin, Trainer, or Student dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        remember_me = request.POST.get('remember_me')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, "Your account has been deactivated. Please contact administration.")
                return render(request, 'authentication/login.html')

            login(request, user)
            if not remember_me:
                # Session expires on browser close
                request.session.set_expiry(0)
            else:
                # 30 days
                request.session.set_expiry(60 * 60 * 24 * 30)

            # Audit log
            AuditLog.objects.create(
                user=user,
                action='USER_LOGIN',
                details=f"User {user.username} logged in as {user.get_role_display()}",
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Invalid username or password. Please try again.")

    return render(request, 'authentication/login.html')


@login_required
def portal_logout(request):
    """Log out current user and redirect to login page."""
    user = request.user
    AuditLog.objects.create(
        user=user,
        action='USER_LOGOUT',
        details=f"User {user.username} logged out.",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    logout(request)
    messages.info(request, "You have been successfully logged out.")
    return redirect('login')


@login_required
def dashboard_redirect(request):
    """Direct user to the correct dashboard according to assigned role."""
    if request.user.is_superuser or request.user.role == 'SUPER_ADMIN':
        return redirect('admin_dashboard')
    elif request.user.role == 'TRAINER':
        return redirect('trainer_dashboard')
    elif request.user.role == 'STUDENT':
        return redirect('student_dashboard')
    else:
        messages.error(request, "Unrecognized role assignment.")
        return redirect('login')


@login_required
def profile_view(request):
    """User profile overview page."""
    student_profile = getattr(request.user, 'student_profile', None)
    return render(request, 'authentication/profile.html', {
        'user': request.user,
        'student_profile': student_profile
    })


@login_required
def edit_profile(request):
    """Allows candidates to upload profile image, resume, and contact details."""
    user = request.user
    student_profile = getattr(user, 'student_profile', None)

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.email = request.POST.get('email', '').strip()
        user.phone_number = request.POST.get('phone_number', '').strip()

        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']

        user.save()

        if student_profile:
            student_profile.bio = request.POST.get('bio', '').strip()
            student_profile.github_profile = request.POST.get('github_profile', '').strip()
            student_profile.linkedin_profile = request.POST.get('linkedin_profile', '').strip()

            if 'resume' in request.FILES:
                student_profile.resume = request.FILES['resume']

            student_profile.save()

        AuditLog.objects.create(
            user=user,
            action='PROFILE_UPDATED',
            details=f"User {user.username} updated personal profile details and resume.",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        messages.success(request, "Your profile details, photo, and resume have been saved successfully!")
        return redirect('profile')

    return render(request, 'authentication/edit_profile.html', {
        'user': user,
        'student_profile': student_profile
    })
