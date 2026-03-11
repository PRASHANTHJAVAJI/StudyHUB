from django import template

register = template.Library()

@register.filter
def is_member(session, user):
    """Check if a user is a member of a session."""
    return session.memberships.filter(user=user).exists()

@register.filter
def is_admin(user):
    try:
        return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))
    except Exception:
        return False

@register.filter
def is_leader(user):
    try:
        profile = getattr(user, 'profile', None)
        return bool(
            profile and (
                getattr(profile, 'is_student_leader', False) or
                getattr(profile, 'is_faculty', False)
            )
        )
    except Exception:
        return False

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(key)
