from django.conf import settings

def portal_branding(request):
    """
    Context processor ensuring official branding, developer credits,
    and portal identity are globally available in all templates.
    """
    return {
        'PLATFORM_NAME': getattr(settings, 'PLATFORM_NAME', 'PUMO TECHNOVATION EXAM PORTAL'),
        'PLATFORM_BRANCH': getattr(settings, 'PLATFORM_BRANCH', 'POONAMALLEE'),
        'DEVELOPER_CREDITS': getattr(settings, 'DEVELOPER_CREDITS', 'SARATHY & THIRUMAL'),
        'FOOTER_COPYRIGHT': getattr(settings, 'FOOTER_COPYRIGHT', '© 2026 PUMO TECHNOVATION. All Rights Reserved.'),
    }
