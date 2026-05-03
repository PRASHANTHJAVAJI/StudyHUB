# REST Framework imports - conditional in case rest_framework is not installed
try:
    from rest_framework import viewsets, permissions, decorators, response, status
    from django_filters.rest_framework import DjangoFilterBackend
    REST_FRAMEWORK_AVAILABLE = True
except ImportError:
    viewsets = None
    permissions = None
    decorators = None
    response = None
    status = None
    DjangoFilterBackend = None
    REST_FRAMEWORK_AVAILABLE = False

from django.db.models import Count, Q, Sum, ExpressionWrapper, F, DurationField
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import login, update_session_auth_hash, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.conf import settings
import csv
import json
import datetime
from django.http import HttpResponse, JsonResponse

from .models import StudySession, SubjectTag, SessionMember, Message, WaitlistEntry, Attendance, UserProfile, Major, Minor, Department, StudyNote
from .forms import StudySessionForm, CustomUserCreationForm, ProfileSetupForm, EditAccountForm, EditProfileForm

def profile_needs_setup(user):
    try:
        return not user.profile.onboarding_complete
    except UserProfile.DoesNotExist:
        return True

def is_faculty_or_leader(user):
    try:
        profile = getattr(user, 'profile', None)
        if not profile:
            return False
        return bool(getattr(profile, 'is_student_leader', False) or getattr(profile, 'is_faculty', False))
    except Exception:
        return False

def session_visible_to_user(session, user):
    if user.is_staff or user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if not profile or not profile.department:
        return False
    if session.owner_id == user.id:
        return True
    visible_departments = list(getattr(session, 'visible_departments', []).all())
    if visible_departments:
        return profile.department in visible_departments
    owner_department = getattr(getattr(session.owner, 'profile', None), 'department', None)
    return bool(owner_department and owner_department == profile.department)

# Serializers import - conditional in case rest_framework is not installed
if REST_FRAMEWORK_AVAILABLE:
    from .serializers import StudySessionSerializer, SubjectTagSerializer, MessageSerializer
else:
    StudySessionSerializer = None
    SubjectTagSerializer = None
    MessageSerializer = None



def custom_login(request):
    """
    Custom login view to handle authentication properly.
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')
                if profile_needs_setup(user):
                    return redirect('core:complete_profile')
                next_url = request.GET.get('next', '/feed/')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AuthenticationForm()
    
    return render(request, 'registration/login.html', {'form': form})


def signup(request):
    """
    Sign up page: create a new user account.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user)
                messages.success(request, 'Account created successfully!')
                if profile_needs_setup(user):
                    return redirect('core:complete_profile')
                return redirect('core:home')
            except Exception as e:
                messages.error(request, f'Error creating account: {str(e)}')
                # Log the error for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Signup error: {str(e)}')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'registration/signup.html', {'form': form})


@login_required
@never_cache
def profile(request):
    """
    User profile page showing user information, stats, and recent activity.
    """
    user_sessions = StudySession.objects.filter(owner=request.user).order_by('-created_at')
    joined_sessions = (
        StudySession.objects
        .filter(memberships__user=request.user)
        .exclude(owner=request.user)
        .order_by('-created_at')
    )

    sessions_count = user_sessions.count() + joined_sessions.count()

    # All session IDs the user is involved in (single DB call)
    all_session_ids = list(
        StudySession.objects
        .filter(Q(owner=request.user) | Q(memberships__user=request.user))
        .distinct()
        .values_list('id', flat=True)
    )

    # Study Partners: unique co-members across all sessions (single aggregation)
    partners_count = (
        SessionMember.objects
        .filter(session_id__in=all_session_ids)
        .exclude(user=request.user)
        .values('user')
        .distinct()
        .count()
    )

    # Study Hours: DB-level duration sum
    hours_data = (
        StudySession.objects
        .filter(id__in=all_session_ids, end_time__isnull=False)
        .annotate(dur=ExpressionWrapper(F('end_time') - F('start_time'), output_field=DurationField()))
        .aggregate(total=Sum('dur'))
    )
    total_duration = hours_data['total'] or datetime.timedelta(0)
    study_hours = int(round(total_duration.total_seconds() / 3600))

    # Recent Activity
    activity = []
    activity.append({
        'type': 'joined_platform',
        'icon': 'fa-user-plus',
        'title': 'Joined StudyHub',
        'desc': 'Welcome to the community!',
        'time': request.user.date_joined,
    })
    for s in user_sessions:
        activity.append({
            'type': 'created',
            'icon': 'fa-plus-circle',
            'title': 'Created a study session',
            'desc': s.title,
            'time': s.created_at,
        })
    # Get join times for joined sessions in one query
    membership_times = {
        m.session_id: m.joined_at
        for m in SessionMember.objects.filter(
            session__in=joined_sessions, user=request.user
        ).only('session_id', 'joined_at')
    }
    for s in joined_sessions:
        activity.append({
            'type': 'joined_group',
            'icon': 'fa-users',
            'title': 'Joined a study group',
            'desc': s.title,
            'time': membership_times.get(s.id, s.created_at),
        })
    activity.sort(key=lambda x: x['time'], reverse=True)

    context = {
        'user_sessions': user_sessions,
        'joined_sessions': joined_sessions,
        'sessions_count': sessions_count,
        'partners_count': partners_count,
        'study_hours': study_hours,
        'activity': activity,
    }
    return render(request, 'core/profile.html', context)


@login_required
@never_cache
def edit_profile(request):
    """
    Edit personal information (username, email) and academic profile
    (education level, department, major, minor) in one page.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    is_admin = request.user.is_staff or request.user.is_superuser
    is_faculty = not is_admin and getattr(profile, 'is_faculty', False)

    if request.method == 'POST':
        account_form = EditAccountForm(request.POST, instance=request.user)
        if is_admin:
            profile_form = None
            forms_valid = account_form.is_valid()
        else:
            profile_form = EditProfileForm(request.POST, instance=profile, user=request.user)
            forms_valid = account_form.is_valid() and profile_form.is_valid()

        if forms_valid:
            account_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('core:profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        account_form = EditAccountForm(instance=request.user)
        profile_form = None if is_admin else EditProfileForm(instance=profile, user=request.user)

    return render(request, 'core/edit_profile.html', {
        'account_form': account_form,
        'profile_form': profile_form,
        'is_admin': is_admin,
        'is_faculty': is_faculty,
    })


@login_required
def export_profile_data(request):
    """Export user's study session data as CSV."""
    user_sessions = StudySession.objects.filter(owner=request.user).prefetch_related('subjects')
    joined_sessions = (
        StudySession.objects
        .filter(memberships__user=request.user)
        .exclude(owner=request.user)
        .prefetch_related('subjects')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="studyhub_data_{request.user.username}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Type', 'Title', 'Subjects', 'Start Time', 'End Time', 'Location', 'Members'])

    for s in user_sessions:
        writer.writerow([
            'Created',
            s.title,
            ', '.join(subj.name for subj in s.subjects.all()),
            s.start_time.strftime('%Y-%m-%d %H:%M') if s.start_time else '',
            s.end_time.strftime('%Y-%m-%d %H:%M') if s.end_time else '',
            s.virtual_link if s.is_virtual else s.location_text,
            s.memberships.count(),
        ])
    for s in joined_sessions:
        writer.writerow([
            'Joined',
            s.title,
            ', '.join(subj.name for subj in s.subjects.all()),
            s.start_time.strftime('%Y-%m-%d %H:%M') if s.start_time else '',
            s.end_time.strftime('%Y-%m-%d %H:%M') if s.end_time else '',
            s.virtual_link if s.is_virtual else s.location_text,
            s.memberships.count(),
        ])

    return response


@login_required
@never_cache
def admin_dashboard(request):
    """
    Admin-only dashboard: departments/majors/minors, subjects, sessions, and profiles.
    """
    from django.contrib.auth.models import User

    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'You do not have permission to view the admin controls.')
        return redirect('core:home')

    active_tab = 'departments'  # default after redirects

    if request.method == 'POST':
        action = request.POST.get('action', '')
        active_tab = request.POST.get('active_tab', 'departments')

        # --- Department actions ---
        if action == 'add_department':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'Department name is required.')
            elif Department.objects.filter(name__iexact=name).exists():
                messages.error(request, f'Department "{name}" already exists.')
            else:
                Department.objects.create(name=name)
                messages.success(request, f'Department "{name}" added.')
            active_tab = 'departments'

        elif action == 'delete_department':
            dept = get_object_or_404(Department, id=request.POST.get('dept_id'))
            dept.delete()
            messages.success(request, f'Department "{dept.name}" deleted.')
            active_tab = 'departments'

        elif action == 'add_major':
            name = request.POST.get('name', '').strip()
            dept_id = request.POST.get('dept_id', '').strip()
            if not name or not dept_id:
                messages.error(request, 'Major name and department are required.')
            else:
                dept = get_object_or_404(Department, id=dept_id)
                if Major.objects.filter(name__iexact=name, department=dept).exists():
                    messages.error(request, f'Major "{name}" already exists in {dept.name}.')
                else:
                    Major.objects.create(name=name, department=dept)
                    messages.success(request, f'Major "{name}" added to {dept.name}.')
            active_tab = 'departments'

        elif action == 'delete_major':
            major = get_object_or_404(Major, id=request.POST.get('major_id'))
            major.delete()
            messages.success(request, f'Major "{major.name}" deleted.')
            active_tab = 'departments'

        elif action == 'add_minor':
            name = request.POST.get('name', '').strip()
            dept_id = request.POST.get('dept_id', '').strip()
            if not name or not dept_id:
                messages.error(request, 'Minor name and department are required.')
            else:
                dept = get_object_or_404(Department, id=dept_id)
                if Minor.objects.filter(name__iexact=name, department=dept).exists():
                    messages.error(request, f'Minor "{name}" already exists in {dept.name}.')
                else:
                    Minor.objects.create(name=name, department=dept)
                    messages.success(request, f'Minor "{name}" added to {dept.name}.')
            active_tab = 'departments'

        elif action == 'delete_minor':
            minor = get_object_or_404(Minor, id=request.POST.get('minor_id'))
            minor.delete()
            messages.success(request, f'Minor "{minor.name}" deleted.')
            active_tab = 'departments'

        # --- Subject actions ---
        elif action == 'add_subject':
            name = request.POST.get('name', '').strip()
            education_level = request.POST.get('education_level', '').strip()
            department = request.POST.get('department', '').strip()
            if not name or not education_level:
                messages.error(request, 'Subject name and education level are required.')
            elif SubjectTag.objects.filter(name__iexact=name, education_level=education_level).exists():
                messages.error(request, 'That subject already exists for the selected education level.')
            else:
                base_slug = slugify(name)
                if education_level:
                    base_slug = f"{base_slug}-{education_level}"
                slug = base_slug
                counter = 1
                while SubjectTag.objects.filter(slug=slug).exists():
                    counter += 1
                    slug = f"{base_slug}-{counter}"
                SubjectTag.objects.create(name=name, slug=slug, education_level=education_level, department=department)
                messages.success(request, f'Subject "{name}" added.')
            active_tab = 'subjects'

        elif action == 'delete_subject':
            subject = get_object_or_404(SubjectTag, id=request.POST.get('subject_id'))
            subject.delete()
            messages.success(request, f'Subject "{subject.name}" deleted.')
            active_tab = 'subjects'

        # --- Session actions ---
        elif action == 'delete_session':
            session = get_object_or_404(StudySession, id=request.POST.get('session_id'))
            session.delete()
            messages.success(request, f'Session "{session.title}" deleted.')
            active_tab = 'sessions'

        # --- Profile / user management actions ---
        elif action == 'create_admin':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            if not username or not email or not password:
                messages.error(request, 'Username, email, and password are required.')
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, f'Username "{username}" is already taken.')
            elif User.objects.filter(email__iexact=email).exists():
                messages.error(request, f'Email "{email}" is already in use.')
            else:
                new_admin = User.objects.create_user(username=username, email=email, password=password, is_staff=True, is_superuser=True)
                profile, _ = UserProfile.objects.get_or_create(user=new_admin)
                profile.onboarding_complete = True
                profile.save(update_fields=['onboarding_complete'])
                messages.success(request, f'Admin account "{username}" created successfully.')
            active_tab = 'profiles'

        elif action == 'set_role':
            profile_id = request.POST.get('profile_id')
            role = request.POST.get('role', '')
            profile = get_object_or_404(UserProfile, id=profile_id)
            # Reset all role flags first
            profile.is_faculty = False
            profile.is_student_leader = False
            profile.user.is_staff = False
            profile.user.is_superuser = False
            if role == 'admin':
                profile.user.is_staff = True
                profile.user.is_superuser = True
                profile.onboarding_complete = True
            elif role == 'faculty':
                profile.is_faculty = True
            elif role == 'leader':
                profile.is_student_leader = True
            profile.user.save()
            profile.save()
            messages.success(request, f'Role updated for {profile.user.username}.')
            active_tab = 'profiles'

        elif action == 'edit_user':
            user_id = request.POST.get('user_id')
            target = get_object_or_404(User, id=user_id)
            new_username = request.POST.get('username', '').strip()
            new_email = request.POST.get('email', '').strip()
            new_password = request.POST.get('password', '').strip()
            error = None
            if not new_username or not new_email:
                error = 'Username and email are required.'
            elif User.objects.filter(username__iexact=new_username).exclude(pk=target.pk).exists():
                error = f'Username "{new_username}" is already taken.'
            elif User.objects.filter(email__iexact=new_email).exclude(pk=target.pk).exists():
                error = f'Email "{new_email}" is already in use.'
            if error:
                messages.error(request, error)
            else:
                target.username = new_username
                target.email = new_email
                if new_password:
                    target.set_password(new_password)
                target.save()
                messages.success(request, f'User "{new_username}" updated successfully.')
            active_tab = 'profiles'

        elif action == 'delete_user':
            user_id = request.POST.get('user_id')
            target = get_object_or_404(User, id=user_id)
            if target == request.user:
                messages.error(request, 'You cannot delete your own account.')
            else:
                uname = target.username
                target.delete()
                messages.success(request, f'User "{uname}" deleted.')
            active_tab = 'profiles'

        return redirect(f"{request.path}?tab={active_tab}")

    active_tab = request.GET.get('tab', 'departments')

    subjects = SubjectTag.objects.order_by('education_level', 'department', 'name')
    departments = Department.objects.prefetch_related('majors', 'minors').order_by('name')
    sessions = StudySession.objects.select_related('owner').order_by('-start_time')
    profiles = UserProfile.objects.select_related('user', 'department', 'major', 'minor').order_by('user__username')
    department_names = list(Department.objects.order_by('name').values_list('name', flat=True))
    subject_departments = list(
        SubjectTag.objects.exclude(department='').order_by('department').values_list('department', flat=True).distinct()
    )
    department_options = sorted({*department_names, *subject_departments})

    context = {
        'subjects': subjects,
        'departments': departments,
        'sessions': sessions,
        'profiles': profiles,
        'education_levels': SubjectTag.EDUCATION_LEVEL_CHOICES,
        'department_options': department_options,
        'subject_count': subjects.count(),
        'department_count': departments.count(),
        'major_count': Major.objects.count(),
        'minor_count': Minor.objects.count(),
        'session_count': sessions.count(),
        'user_count': profiles.count(),
        'active_tab': active_tab,
    }
    return render(request, 'core/admin_dashboard.html', context)


@login_required
@never_cache
def complete_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    # Admins never need onboarding
    if request.user.is_staff or request.user.is_superuser:
        if not profile.onboarding_complete:
            profile.onboarding_complete = True
            profile.save(update_fields=['onboarding_complete'])
        return redirect('core:home')

    if profile.onboarding_complete:
        return redirect('core:home')

    is_faculty = getattr(profile, 'is_faculty', False)

    if request.method == 'POST':
        form = ProfileSetupForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            updated_profile = form.save(commit=False)
            updated_profile.onboarding_complete = True
            updated_profile.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('core:home')
    else:
        form = ProfileSetupForm(instance=profile, user=request.user)

    return render(request, 'core/profile_setup.html', {
        'form': form,
        'is_faculty': is_faculty,
    })


@login_required
def department_options(request, department_id):
    majors = list(
        Major.objects.filter(department_id=department_id)
        .order_by('name')
        .values('id', 'name')
    )
    minors = list(
        Minor.objects.filter(department_id=department_id)
        .order_by('name')
        .values('id', 'name')
    )
    return JsonResponse({'majors': majors, 'minors': minors})


@login_required
@never_cache
def change_password(request):
    """
    Change password page.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('core:profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'registration/change_password.html', {'form': form})


def logout_view(request):
    """
    Custom logout view that immediately logs out the user and redirects.
    """
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('core:landing')


def landing(request):
    """
    Public landing page for non-authenticated users.
    """
    return render(request, 'core/landing.html')


@login_required
@never_cache
def home(request):
    """
    Feed page: list sessions, with filters.
    Filters via query params:
      - q=search string in title/description
      - date=today|tomorrow|week|month
      - session_type=virtual|in-person
      - local_datetime=ISO8601 string from user's browser
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    qs = (
        StudySession.objects.select_related('owner', 'owner__profile')
        .prefetch_related('subjects', 'memberships__user', 'visible_departments')
        .annotate(num_members=Count('memberships'))
        .order_by('start_time')
    )

    q = request.GET.get('q')
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(subjects__name__icontains=q))

    # Department visibility filtering (always applied to General + Study Sessions)
    show_all_conferences = request.GET.get('show_all', '0') == '1'
    user_department = profile.department
    if user_department:
        qs = qs.filter(
            Q(visible_departments=user_department) |
            Q(visible_departments__isnull=True, owner__profile__department=user_department)
        ).distinct()
    elif request.user.is_staff or request.user.is_superuser:
        pass  # admins see all sessions
    else:
        qs = qs.none()

    # Date range and local time handling
    date_range = request.GET.get('date')
    local_datetime_str = request.GET.get('local_datetime')
    if local_datetime_str:
        try:
            user_now = datetime.datetime.fromisoformat(local_datetime_str.replace('Z', '+00:00'))
            # Ensure timezone-aware
            if timezone.is_naive(user_now):
                user_now = timezone.make_aware(user_now)
        except Exception:
            user_now = timezone.now()
    else:
        user_now = timezone.now()

    # Session type filter
    session_type = request.GET.get('session_type')
    if session_type == 'virtual':
        qs = qs.filter(is_virtual=True)
    elif session_type == 'in-person':
        qs = qs.filter(is_virtual=False)

    # Compute next occurrence for recurring sessions and filter out past ones
    def compute_next_occurrence(session, now_dt):
        """Return (next_start, next_end) or (None, None) if no future occurrence."""
        start = session.start_time
        end = session.end_time
        # Ensure now_dt is timezone-aware to safely compare with DB datetimes
        if timezone.is_naive(now_dt):
            now_dt = timezone.make_aware(now_dt)
        duration = (end - start) if (end and start) else None
        if session.is_recurring and session.recurrence_type != 'none':
            freq = session.recurrence_type
            interval = session.recurrence_interval or 1
            current = start
            while current < now_dt:
                if freq == 'daily':
                    current += datetime.timedelta(days=interval)
                elif freq == 'weekly':
                    current += datetime.timedelta(weeks=interval)
                elif freq == 'monthly':
                    current += datetime.timedelta(days=30 * interval)
                else:
                    break
                if (current - start).days > 365 * 5:
                    return (None, None)
            until = session.recurrence_end_date
            if until and current > until:
                return (None, None)
            next_end = (current + duration) if duration else None
            return (current, next_end)
        else:
            if end and end >= now_dt:
                return (start, end)
            if not end and start >= now_dt:
                return (start, None)
            return (None, None)

    processed = []
    for s in qs:
        ns, ne = compute_next_occurrence(s, user_now)
        if ns is None:
            continue
        # Apply date range filters based on next occurrence
        include = True
        if date_range == 'today' and ns.date() != user_now.date():
            include = False
        elif date_range == 'tomorrow' and ns.date() != (user_now + datetime.timedelta(days=1)).date():
            include = False
        elif date_range == 'week':
            week_later = user_now + datetime.timedelta(days=7)
            if not (user_now.date() <= ns.date() <= week_later.date()):
                include = False
        elif date_range == 'month':
            month_later = user_now + datetime.timedelta(days=31)
            if not (user_now.date() <= ns.date() <= month_later.date()):
                include = False
        if not include:
            continue
        # Attach display times for template
        s.display_start_time = ns
        s.display_end_time = ne
        processed.append(s)

    # Sort by department, then by next occurrence time
    def _dept_sort_key(session):
        visible_departments = list(session.visible_departments.all())
        if visible_departments:
            dept_name = sorted([d.name for d in visible_departments])[0]
        else:
            owner_dept = getattr(getattr(session.owner, 'profile', None), 'department', None)
            dept_name = owner_dept.name if owner_dept else ''
        return (dept_name.lower(), getattr(session, 'display_start_time', session.start_time))

    processed.sort(key=_dept_sort_key)

    # Get user's education level and subjects list
    user_education_level = profile.education_level
    subjects = SubjectTag.objects.filter(education_level=user_education_level).order_by('name')

    # Stats - count sessions happening today (based on user's local time)
    user_now_date = user_now.date()
    upcoming_sessions_count = sum(1 for s in processed if getattr(s, 'display_start_time', s.start_time).date() == user_now_date)

    # General and Study Sessions always come from the dept-filtered list
    sessions_general = [s for s in processed if s.category == 'general']
    sessions_study = [s for s in processed if s.category == 'study_session']

    # Conferences: all departments when toggle is on, otherwise dept-filtered
    if show_all_conferences:
        conf_qs = (
            StudySession.objects.filter(category='conference')
            .select_related('owner', 'owner__profile')
            .prefetch_related('subjects', 'memberships__user', 'visible_departments')
            .annotate(num_members=Count('memberships'))
            .order_by('start_time')
        )
        if q:
            conf_qs = conf_qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(subjects__name__icontains=q))
        if session_type == 'virtual':
            conf_qs = conf_qs.filter(is_virtual=True)
        elif session_type == 'in-person':
            conf_qs = conf_qs.filter(is_virtual=False)

        sessions_conference = []
        for s in conf_qs:
            ns, ne = compute_next_occurrence(s, user_now)
            if ns is None:
                continue
            include = True
            if date_range == 'today' and ns.date() != user_now.date():
                include = False
            elif date_range == 'tomorrow' and ns.date() != (user_now + datetime.timedelta(days=1)).date():
                include = False
            elif date_range == 'week':
                week_later = user_now + datetime.timedelta(days=7)
                if not (user_now.date() <= ns.date() <= week_later.date()):
                    include = False
            elif date_range == 'month':
                month_later = user_now + datetime.timedelta(days=31)
                if not (user_now.date() <= ns.date() <= month_later.date()):
                    include = False
            if not include:
                continue
            s.display_start_time = ns
            s.display_end_time = ne
            sessions_conference.append(s)
    else:
        sessions_conference = [s for s in processed if s.category == 'conference']

    context = {
        'sessions': processed,
        'sessions_general': sessions_general,
        'sessions_study': sessions_study,
        'sessions_conference': sessions_conference,
        'subjects': subjects,
        'user_education_level': user_education_level,
        'upcoming_sessions_count': upcoming_sessions_count,
        'q': q or '',
        'date_range': date_range or '',
        'session_type': session_type or '',
        'show_all': show_all_conferences,
        'user_department': profile.department,
    }
    return render(request, 'core/feed.html', context)


@login_required
def edit_session(request, pk):
    """Edit an existing study session."""
    session = get_object_or_404(StudySession, pk=pk)
    
    # Check if user is the owner
    if session.owner != request.user:
        messages.error(request, 'You can only edit sessions you created.')
        return redirect('core:detail', pk=pk)
    
    if request.method == 'POST':
        form = StudySessionForm(request.POST, instance=session, user=request.user)
        if form.is_valid():
            session = form.save(commit=False)
            if session.is_virtual:
                session.location_text = ""
            else:
                building_name = form.cleaned_data.get('building_name', '')
                room_number = form.cleaned_data.get('room_number', '')
                session.location_text = f"{building_name} - Room {room_number}".strip()
            session.save()

            profile_department = getattr(getattr(request.user, 'profile', None), 'department', None)
            visibility = form.cleaned_data.get('visibility', 'department')
            if visibility == 'all':
                session.visible_departments.set(Department.objects.all())
            elif profile_department:
                session.visible_departments.set([profile_department])

            # Handle subject selection
            subject_id = form.cleaned_data.get('subjects')
            if subject_id:
                session.subjects.clear()
                try:
                    subject = SubjectTag.objects.get(id=subject_id)
                    session.subjects.add(subject)
                except SubjectTag.DoesNotExist:
                    pass

            messages.success(request, 'Study session updated successfully!')
            return redirect('core:detail', pk=session.pk)
    else:
        form = StudySessionForm(instance=session, user=request.user)
    
    subjects_data = getattr(form, 'all_subjects', {})
    subjects_data_json = json.dumps(subjects_data)
    context = {
        'form': form,
        'session': session,
        'subjects_data': subjects_data_json
    }
    return render(request, 'core/edit_session.html', context)

@login_required
def delete_session(request, pk):
    """Delete a study session."""
    session = get_object_or_404(StudySession, pk=pk)
    
    # Check if user is the owner
    if session.owner != request.user:
        messages.error(request, 'You can only delete sessions you created.')
        return redirect('core:detail', pk=pk)
    
    if request.method == 'POST':
        session.delete()
        messages.success(request, 'Study session deleted successfully!')
        return redirect('core:home')
    
    return render(request, 'core/delete_session.html', {'session': session})

@login_required
@never_cache
def create_group(request):
    if request.method == 'POST':
        form = StudySessionForm(request.POST, user=request.user)
        if form.is_valid():
            session = form.save(commit=False)
            session.owner = request.user
            
            # Handle location fields based on session type
            if session.is_virtual:
                # For virtual sessions, location_text can be empty or contain additional info
                session.location_text = ""
            else:
                # For in-person sessions, combine building name and room number
                building_name = form.cleaned_data.get('building_name', '')
                room_number = form.cleaned_data.get('room_number', '')
                session.location_text = f"{building_name} - Room {room_number}".strip()
            
            session.save()

            profile_department = getattr(getattr(request.user, 'profile', None), 'department', None)
            visibility = form.cleaned_data.get('visibility', 'department')
            if visibility == 'all':
                session.visible_departments.set(Department.objects.all())
            elif profile_department:
                session.visible_departments.set([profile_department])

            # Handle single subject selection
            subject_id = form.cleaned_data.get('subjects')
            if subject_id:
                try:
                    subject = SubjectTag.objects.get(id=subject_id)
                    session.subjects.add(subject)
                except SubjectTag.DoesNotExist:
                    pass
            
            # Make creator the host member
            SessionMember.objects.get_or_create(
                session=session, user=request.user,
                defaults={'role': SessionMember.HOST}
            )
            
            messages.success(request, 'Study session created successfully!')
            return redirect('core:detail', pk=session.pk)
    else:
        form = StudySessionForm(user=request.user)
    
    # Pass the subjects data to the template for JavaScript
    subjects_data = getattr(form, 'all_subjects', {})
    # Convert to JSON for JavaScript
    subjects_data_json = json.dumps(subjects_data)
    
    context = {
        'form': form,
        'subjects_data': subjects_data_json
    }
    
    return render(request, 'core/create.html', context)


def group_details(request, pk):
    """
    Detail page: show one session with members and messages.
    """
    session = get_object_or_404(
        StudySession.objects.select_related('owner', 'owner__profile')
        .prefetch_related('subjects', 'memberships__user', 'messages__user', 'attendance__user', 'visible_departments')
        .annotate(num_members=Count('memberships')),
        pk=pk
    )
    is_member = False
    if request.user.is_authenticated:
        if not session_visible_to_user(session, request.user):
            messages.error(request, 'This session is not available for your department.')
            return redirect('core:home')
        is_member = SessionMember.objects.filter(session=session, user=request.user).exists()

    # Can mark attendance: session owner after session starts, OR any leader/admin who is a member
    can_mark_attendance = False
    if request.user.is_authenticated:
        session_started = timezone.now() >= session.start_time
        is_leader_or_admin = (
            request.user.is_staff or
            request.user.is_superuser or
            is_faculty_or_leader(request.user)
        )
        can_mark_attendance = session_started and (
            request.user == session.owner or is_leader_or_admin
        )

    # Handle message posting
    if request.method == 'POST' and request.user.is_authenticated and is_member:
        message_text = request.POST.get('message_text', '').strip()
        if message_text:
            Message.objects.create(
                session=session,
                user=request.user,
                text=message_text
            )
            messages.success(request, 'Message sent!')
            return redirect('core:detail', pk=pk)

    # Get attendance data
    attendance_dict = {}
    if can_mark_attendance or request.user.is_authenticated:
        attendance_records = session.attendance.select_related('user').all()
        attendance_dict = {record.user_id: record.status for record in attendance_records}

    context = {
        'session': session,
        'members': [m.user for m in session.memberships.all()],
        'messages': session.messages.all(),
        'is_member': is_member,
        'spots_left': max(session.capacity - session.num_members, 0),
        'waitlist': session.waitlist.all() if request.user == session.owner else [],
        'can_mark_attendance': can_mark_attendance,
        'attendance_dict': attendance_dict,
    }
    return render(request, 'core/detail.html', context)


@login_required
@never_cache
def join_session(request, pk):
    """
    Join a session via HTML (POST). Redirects back to detail.
    """
    session = get_object_or_404(StudySession, pk=pk)

    if not session_visible_to_user(session, request.user):
        messages.error(request, 'This session is not available for your department.')
        return redirect('core:home')

    if SessionMember.objects.filter(session=session, user=request.user).exists():
        messages.info(request, 'You already joined this session.')
        return redirect('core:detail', pk=pk)

    # Capacity check
    current_count = SessionMember.objects.filter(session=session).count()
    if current_count >= session.capacity:
        messages.error(request, 'Session is full.')
        return redirect('core:detail', pk=pk)

    SessionMember.objects.create(session=session, user=request.user)
    messages.success(request, 'Joined the session!')
    return redirect('core:detail', pk=pk)


@login_required
@never_cache
def leave_session(request, pk):
    """
    Leave a session via HTML (POST). Redirects back to detail.
    """
    session = get_object_or_404(StudySession, pk=pk)
    deleted, _ = SessionMember.objects.filter(session=session, user=request.user).delete()
    if deleted:
        messages.success(request, 'Left the session.')
        
        # Check if there's a spot and auto-promote the first waitlisted user
        current_count = SessionMember.objects.filter(session=session).count()
        if current_count < session.capacity:
            first_waitlist = WaitlistEntry.objects.filter(session=session).order_by('added_at').first()
            if first_waitlist:
                promoted_user = first_waitlist.user
                SessionMember.objects.create(session=session, user=promoted_user)
                first_waitlist.delete()

                # Notify only the promoted user
                try:
                    location = session.virtual_link if session.is_virtual else session.location_text or 'TBD'
                    send_mail(
                        f'You got a spot in "{session.title}"!',
                        f'Great news, {promoted_user.username}! A spot opened up in "{session.title}" '
                        f'and you have been automatically added.\n\n'
                        f'Date: {session.start_time.strftime("%B %d, %Y at %I:%M %p")}\n'
                        f'Location: {location}\n\n'
                        f'View details: {request.build_absolute_uri(f"/session/{session.pk}/")}',
                        settings.DEFAULT_FROM_EMAIL,
                        [promoted_user.email],
                        fail_silently=True,
                    )
                    messages.info(request, f'{promoted_user.username} was automatically promoted from the waitlist.')
                except Exception:
                    messages.info(request, f'{promoted_user.username} was promoted from the waitlist.')
    else:
        messages.info(request, 'You were not a member.')
    return redirect('core:detail', pk=pk)


@login_required
@never_cache
def join_waitlist(request, pk):
    session = get_object_or_404(StudySession, pk=pk)
    if not session_visible_to_user(session, request.user):
        messages.error(request, 'This session is not available for your department.')
        return redirect('core:home')
    # Only allow waitlist if full
    current_count = SessionMember.objects.filter(session=session).count()
    if current_count < session.capacity:
        messages.info(request, 'Session has spots. Please join directly.')
        return redirect('core:detail', pk=pk)
    WaitlistEntry.objects.get_or_create(session=session, user=request.user)
    messages.success(request, 'Added to waitlist!')
    return redirect('core:detail', pk=pk)


@login_required
def session_ics(request, pk):
    session = get_object_or_404(StudySession, pk=pk)
    if not session_visible_to_user(session, request.user):
        messages.error(request, 'This session is not available for your department.')
        return redirect('core:home')
    dtstamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%SZ')
    dtstart = session.start_time.strftime('%Y%m%dT%H%M%SZ')
    dtend = session.end_time.strftime('%Y%m%dT%H%M%SZ') if session.end_time else ''
    location = session.virtual_link if session.is_virtual else session.location_text
    description = session.description.replace('\n', ' ') if session.description else ''
    subjects = ', '.join([s.name for s in session.subjects.all()])
    summary = session.title
    organizer = session.owner.email or ''
    uid = f"session-{session.pk}@studyhub"

    # Recurrence rule
    rrule = ''
    if getattr(session, 'is_recurring', False) and getattr(session, 'recurrence_type', 'none') != 'none':
        freq_map = {
            'daily': 'DAILY',
            'weekly': 'WEEKLY',
            'monthly': 'MONTHLY',
        }
        freq = freq_map.get(session.recurrence_type)
        if freq:
            parts = [f'FREQ={freq}']
            interval = getattr(session, 'recurrence_interval', 1) or 1
            parts.append(f'INTERVAL={interval}')
            until = getattr(session, 'recurrence_end_date', None)
            if until:
                until_str = until.strftime('%Y%m%dT%H%M%SZ')
                parts.append(f'UNTIL={until_str}')
            rrule = f"RRULE:{';'.join(parts)}\n"

    ics = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//StudyHub//EN\n"
        "CALSCALE:GREGORIAN\n"
        "BEGIN:VEVENT\n"
        f"UID:{uid}\n"
        f"DTSTAMP:{dtstamp}\n"
        f"DTSTART:{dtstart}\n"
        f"{f'DTEND:{dtend}\n' if dtend else ''}"
        f"{rrule}"
        f"SUMMARY:{summary}\n"
        f"DESCRIPTION:{description} Subjects: {subjects}\n"
        f"LOCATION:{location}\n"
        f"ORGANIZER;CN={session.owner.username}:MAILTO:{organizer}\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    response = HttpResponse(ics, content_type='text/calendar')
    response['Content-Disposition'] = f'attachment; filename="session_{session.pk}.ics"'
    return response


@login_required
@never_cache
def mark_attendance(request, pk):
    """
    Mark attendance for a session member.
    Only leaders/admins can mark attendance, and only after session has started.
    """
    session = get_object_or_404(StudySession, pk=pk)
    
    # Check permissions: session owner OR any leader/admin
    is_leader_or_admin = (
        request.user.is_staff or
        request.user.is_superuser or
        is_faculty_or_leader(request.user)
    )

    if request.user != session.owner and not is_leader_or_admin:
        messages.error(request, 'You do not have permission to mark attendance.')
        return redirect('core:detail', pk=pk)
    
    # Check if session has started
    if timezone.now() < session.start_time:
        messages.error(request, 'Attendance can only be marked after the session has started.')
        return redirect('core:detail', pk=pk)
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        status = request.POST.get('status')  # 'present' or 'absent'
        
        if user_id and status in [Attendance.PRESENT, Attendance.ABSENT]:
            try:
                from django.contrib.auth.models import User
                member_user = User.objects.get(id=user_id)
                
                # Verify user is a member of the session
                if not SessionMember.objects.filter(session=session, user=member_user).exists():
                    messages.error(request, 'User is not a member of this session.')
                    return redirect('core:detail', pk=pk)
                
                # Create or update attendance
                attendance, created = Attendance.objects.update_or_create(
                    session=session,
                    user=member_user,
                    defaults={
                        'status': status,
                        'marked_by': request.user,
                        'marked_at': timezone.now()
                    }
                )
                
                status_display = 'Present' if status == Attendance.PRESENT else 'Absent'
                messages.success(request, f'Marked {member_user.username} as {status_display}.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
        else:
            messages.error(request, 'Invalid attendance data.')
    
    return redirect('core:detail', pk=pk)


# ---------------------------
# Your existing DRF ViewSets:
# ---------------------------

# Only define ViewSets if REST framework is available
if REST_FRAMEWORK_AVAILABLE:
    class IsOwnerOrReadOnly(permissions.BasePermission):
        def has_object_permission(self, request, view, obj):
            if request.method in permissions.SAFE_METHODS:
                return True
            return getattr(obj, 'owner_id', None) == getattr(request.user, 'id', None)

    class StudySessionViewSet(viewsets.ModelViewSet):
        queryset = (
            StudySession.objects.select_related('owner')
            .prefetch_related('subjects', 'memberships', 'messages')
            .annotate(num_members=Count('memberships'))
        )
        serializer_class = StudySessionSerializer
        permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
        filter_backends = [DjangoFilterBackend]
        filterset_fields = {'is_virtual': ['exact'], 'subjects__slug': ['exact']}

        def perform_create(self, serializer):
            session = serializer.save(owner=self.request.user)
            SessionMember.objects.get_or_create(
                session=session, user=self.request.user, defaults={'role': SessionMember.HOST}
            )

        @decorators.action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
        def join(self, request, pk=None):
            session = self.get_object()
            if SessionMember.objects.filter(session=session, user=request.user).exists():
                return response.Response({'detail': 'Already joined.'}, status=status.HTTP_200_OK)
            if session.memberships.count() >= session.capacity:
                return response.Response({'detail': 'Session is full.'}, status=status.HTTP_400_BAD_REQUEST)
            SessionMember.objects.create(session=session, user=request.user)
            return response.Response({'detail': 'Joined.'}, status=status.HTTP_201_CREATED)

        @decorators.action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
        def leave(self, request, pk=None):
            session = self.get_object()
            deleted, _ = SessionMember.objects.filter(session=session, user=request.user).delete()
            if deleted == 0:
                return response.Response({'detail': 'You were not a member.'}, status=status.HTTP_200_OK)
            return response.Response({'detail': 'Left.'}, status=status.HTTP_200_OK)

        @decorators.action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
        def messages(self, request, pk=None):
            session = self.get_object()
            if request.method == 'POST':
                if not SessionMember.objects.filter(session=session, user=request.user).exists():
                    return response.Response({'detail': 'Join first to post.'}, status=status.HTTP_403_FORBIDDEN)
                ser = MessageSerializer(data=request.data)
                ser.is_valid(raise_exception=True)
                msg = Message.objects.create(session=session, user=request.user, text=ser.validated_data['text'])
                return response.Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)
            qs = session.messages.select_related('user')
            page = self.paginate_queryset(qs)
            if page is not None:
                return self.get_paginated_response(MessageSerializer(page, many=True).data)
            return response.Response(MessageSerializer(qs, many=True).data)

    class SubjectTagViewSet(viewsets.ReadOnlyModelViewSet):
        queryset = SubjectTag.objects.all().order_by('name')
        serializer_class = SubjectTagSerializer
        permission_classes = [permissions.AllowAny]
else:
    # Placeholder classes if REST framework is not available
    IsOwnerOrReadOnly = None
    StudySessionViewSet = None
    SubjectTagViewSet = None
