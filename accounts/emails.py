import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def send_student_welcome_email(student_user, raw_password, request=None):
    """
    Sends an official account creation welcome email to student with login credentials.
    Returns (success: bool, status_message: str).
    """
    if not student_user.email:
        return False, "No email address provided for this student."

    if request:
        try:
            login_url = request.build_absolute_uri(reverse('login'))
        except Exception:
            login_url = "http://127.0.0.1:8000/login/"
    else:
        login_url = "http://127.0.0.1:8000/login/"

    portal_name = getattr(settings, 'PLATFORM_NAME', 'SATX')
    platform_branch = getattr(settings, 'PLATFORM_BRANCH', 'EXAM PORTAL')

    reg_no = 'N/A'
    course_name = 'Unassigned'
    batch_name = 'Unassigned'

    if hasattr(student_user, 'student_profile') and student_user.student_profile:
        profile = student_user.student_profile
        if profile.reg_no:
            reg_no = profile.reg_no
        if profile.course:
            course_name = profile.course.name
        if profile.batch:
            batch_name = profile.batch.name

    candidate_name = student_user.get_full_name() or student_user.username
    subject = f"Welcome to {portal_name} Exam Portal - Your Account Credentials"

    plain_content = f"""Dear {candidate_name},

Welcome to {portal_name} Exam Portal!
Your student account has been created successfully. You can now log in to the portal to take your scheduled online examinations.

Here are your account credentials:
----------------------------------------
Portal URL: {login_url}
Username: {student_user.username}
Password: {raw_password}
Registration No: {reg_no}
Assigned Course: {course_name}
Assigned Batch: {batch_name}
----------------------------------------

Instructions:
1. Open the portal URL: {login_url}
2. Enter your username and password.
3. Once logged in, view your scheduled exams and ensure your webcam is ready for proctored tests.
4. For security, please update your password after your initial login from the profile section.

Best regards,
Examination Management Team
{portal_name} {platform_branch}
"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f1f5f9;
            margin: 0;
            padding: 24px 12px;
            color: #1e293b;
        }}
        .email-wrapper {{
            max-width: 620px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
            border: 1px solid #e2e8f0;
        }}
        .email-header {{
            background: linear-gradient(135deg, #0a192f 0%, #0f4c81 100%);
            color: #ffffff;
            padding: 32px 28px;
            text-align: center;
        }}
        .header-title {{
            margin: 0;
            font-size: 26px;
            font-weight: 800;
            letter-spacing: 1.5px;
            color: #38bdf8;
        }}
        .header-subtitle {{
            margin: 6px 0 0 0;
            font-size: 13px;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        .email-body {{
            padding: 32px 28px;
        }}
        .greeting {{
            font-size: 18px;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 12px;
        }}
        .lead-text {{
            font-size: 15px;
            line-height: 1.6;
            color: #475569;
            margin-bottom: 24px;
        }}
        .credentials-box {{
            background-color: #f8fafc;
            border: 1px solid #cbd5e1;
            border-left: 6px solid #0284c7;
            border-radius: 10px;
            padding: 20px 22px;
            margin-bottom: 26px;
        }}
        .cred-title {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: #0284c7;
            margin-bottom: 14px;
        }}
        .cred-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 9px 0;
            border-bottom: 1px dashed #e2e8f0;
            font-size: 14px;
        }}
        .cred-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .cred-key {{
            color: #64748b;
            font-weight: 600;
        }}
        .cred-val {{
            color: #0f172a;
            font-weight: 700;
            font-family: 'Consolas', 'Courier New', monospace;
            background: #ffffff;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #e2e8f0;
        }}
        .cred-val-highlight {{
            color: #0369a1;
            background: #e0f2fe;
            border-color: #bae6fd;
        }}
        .action-container {{
            text-align: center;
            margin: 28px 0;
        }}
        .btn-login {{
            display: inline-block;
            background: #0284c7;
            color: #ffffff !important;
            font-size: 15px;
            font-weight: 700;
            padding: 14px 34px;
            border-radius: 8px;
            text-decoration: none;
            box-shadow: 0 4px 14px rgba(2, 132, 199, 0.35);
        }}
        .instructions-box {{
            background: #ecfeff;
            border: 1px solid #a5f3fc;
            border-radius: 8px;
            padding: 16px 20px;
            font-size: 13px;
            color: #0e7490;
            line-height: 1.6;
            margin-top: 20px;
        }}
        .instructions-box strong {{
            color: #155e75;
        }}
        .email-footer {{
            background-color: #f8fafc;
            border-top: 1px solid #e2e8f0;
            padding: 20px 28px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="email-header">
            <h1 class="header-title">{portal_name}</h1>
            <p class="header-subtitle">{platform_branch}</p>
        </div>
        <div class="email-body">
            <div class="greeting">Hello {candidate_name},</div>
            <div class="lead-text">
                Your student examination account for <strong>{portal_name} Exam Portal</strong> has been created. You can now log in to review scheduled exams, take live proctored tests, and track your assessment results.
            </div>

            <div class="credentials-box">
                <div class="cred-title">Account Access Credentials</div>
                <div class="cred-item">
                    <span class="cred-key">Portal URL</span>
                    <span class="cred-val"><a href="{login_url}" style="color: #0284c7; text-decoration: none;">{login_url}</a></span>
                </div>
                <div class="cred-item">
                    <span class="cred-key">Username</span>
                    <span class="cred-val cred-val-highlight">{student_user.username}</span>
                </div>
                <div class="cred-item">
                    <span class="cred-key">Password</span>
                    <span class="cred-val" style="color: #dc2626;">{raw_password}</span>
                </div>
                <div class="cred-item">
                    <span class="cred-key">Registration No</span>
                    <span class="cred-val">{reg_no}</span>
                </div>
                <div class="cred-item">
                    <span class="cred-key">Assigned Course</span>
                    <span class="cred-val">{course_name}</span>
                </div>
                <div class="cred-item">
                    <span class="cred-key">Assigned Batch</span>
                    <span class="cred-val">{batch_name}</span>
                </div>
            </div>

            <div class="action-container">
                <a href="{login_url}" class="btn-login" target="_blank">Sign In to {portal_name} &rarr;</a>
            </div>

            <div class="instructions-box">
                <strong>Next Steps:</strong>
                <ol style="margin: 6px 0 0 0; padding-left: 20px;">
                    <li>Log in using your username and temporary password.</li>
                    <li>Update your password in your profile settings for security.</li>
                    <li>Review exam instructions and ensure your webcam/microphone work properly.</li>
                </ol>
            </div>
        </div>
        <div class="email-footer">
            &copy; 2026 {portal_name}. All Rights Reserved. • Developed By Team SAT
        </div>
    </div>
</body>
</html>
"""

    is_console = 'console' in getattr(settings, 'EMAIL_BACKEND', '')
    has_smtp_user = bool(getattr(settings, 'EMAIL_HOST_USER', '').strip())

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', f"{portal_name} Exam Portal <noreply@satx.edu>")
        msg = EmailMultiAlternatives(subject, plain_content, from_email, [student_user.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        if is_console or not has_smtp_user:
            return False, (
                f"Email was only printed to the server terminal. "
                f"To send real emails to {student_user.email}, configure EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in your .env file."
            )

        return True, f"Welcome email with login credentials sent to {student_user.email}."
    except Exception as e:
        logger.warning(f"Failed to send welcome email to {student_user.email}: {e}")
        return False, f"Email notification not sent ({e}). Account was still created."


def send_student_password_reset_email(student_user, new_password, request=None):
    """
    Sends notification when password is reset by an Administrator or Trainer.
    """
    if not student_user.email:
        return False, "Student has no email address configured."

    login_url = request.build_absolute_uri(reverse('login')) if request else "http://127.0.0.1:8000/login/"
    portal_name = getattr(settings, 'PLATFORM_NAME', 'SATX')

    subject = f"{portal_name} Exam Portal - Password Reset Notification"
    candidate_name = student_user.get_full_name() or student_user.username

    plain_content = f"""Dear {candidate_name},

Your password for {portal_name} Exam Portal has been reset by an administrator/trainer.

Your new login credentials:
----------------------------------------
Portal URL: {login_url}
Username: {student_user.username}
New Password: {new_password}
----------------------------------------

Please log in and update your password if desired.

Best regards,
Examination Management Team
{portal_name}
"""

    html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; background: #f8fafc; padding: 24px;">
    <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 10px; border: 1px solid #e2e8f0; padding: 24px;">
        <h2 style="color: #0284c7; margin-top: 0;">{portal_name} Exam Portal</h2>
        <p>Hello <strong>{candidate_name}</strong>,</p>
        <p>Your portal password has been reset. Use the credentials below to log in:</p>
        <div style="background: #f1f5f9; padding: 14px; border-radius: 6px; font-family: monospace; font-size: 14px;">
            <p style="margin: 4px 0;"><strong>Username:</strong> {student_user.username}</p>
            <p style="margin: 4px 0;"><strong>New Password:</strong> <span style="color: #dc2626; font-weight: bold;">{new_password}</span></p>
            <p style="margin: 4px 0;"><strong>Portal Login:</strong> <a href="{login_url}">{login_url}</a></p>
        </div>
        <p style="margin-top: 20px; font-size: 13px; color: #64748b;">If you did not request this change, please contact your examination administrator immediately.</p>
    </div>
</body>
</html>
"""

    is_console = 'console' in getattr(settings, 'EMAIL_BACKEND', '')
    has_smtp_user = bool(getattr(settings, 'EMAIL_HOST_USER', '').strip())

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', f"{portal_name} Exam Portal <noreply@satx.edu>")
        msg = EmailMultiAlternatives(subject, plain_content, from_email, [student_user.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        if is_console or not has_smtp_user:
            return False, f"Password reset email was logged to the server terminal only. Configure EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env for real email delivery."

        return True, f"Password reset email sent to {student_user.email}."
    except Exception as e:
        logger.warning(f"Failed to send password reset email to {student_user.email}: {e}")
        return False, f"Password reset email notification failed ({e})."
