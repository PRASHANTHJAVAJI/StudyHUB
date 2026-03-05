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

from django.db.models import Count, Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import login, update_session_auth_hash, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.conf import settings
import json
import datetime
from django.http import HttpResponse

from .models import StudySession, SubjectTag, SessionMember, Message, WaitlistEntry, Attendance
from .forms import StudySessionForm, CustomUserCreationForm

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
    joined_sessions = StudySession.objects.filter(memberships__user=request.user).exclude(owner=request.user).order_by('-created_at')

    # Study Sessions count
    sessions_count = user_sessions.count()

    # Study Partners: unique users in all sessions the user owns or joined (excluding self)
    partner_ids = set()
    for session in user_sessions:
        partner_ids.update(session.memberships.exclude(user=request.user).values_list('user_id', flat=True))
    for session in joined_sessions:
        partner_ids.update(session.memberships.exclude(user=request.user).values_list('user_id', flat=True))
    partners_count = len(partner_ids)

    # Study Hours: sum of durations (in hours) of all sessions the user owns or joined
    def session_hours(session):
        if session.end_time and session.start_time:
            delta = session.end_time - session.start_time
            return max(delta.total_seconds() / 3600, 0)
        return 0
    study_hours = sum(session_hours(s) for s in user_sessions) + sum(session_hours(s) for s in joined_sessions)
    study_hours = int(round(study_hours))

    # Recent Activity: list of dicts with 'type', 'title', 'desc', 'time'
    activity = []
    # Joined StudyHub
    activity.append({
        'type': 'joined',
        'title': 'Joined StudyHub',
        'desc': 'Welcome to the community!',
        'time': request.user.date_joined,
    })
    # Created sessions
    for s in user_sessions:
        activity.append({
            'type': 'created',
            'title': 'Created a study session',
            'desc': s.title,
            'time': s.created_at,
        })
    # Joined sessions
    for s in joined_sessions:
        # Find when the user joined (SessionMember)
        member = s.memberships.filter(user=request.user).first()
        joined_time = member.joined_at if hasattr(member, 'joined_at') and member.joined_at else s.created_at
        activity.append({
            'type': 'joined_group',
            'title': 'Joined a study group',
            'desc': s.title,
            'time': joined_time,
        })
    # Sort activity by time, most recent first
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
    from datetime import timedelta

    qs = (
        StudySession.objects.select_related('owner')
        .prefetch_related('subjects', 'memberships__user')
        .annotate(num_members=Count('memberships'))
        .order_by('start_time')
    )

    q = request.GET.get('q')
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(subjects__name__icontains=q))

    # Date range and local time handling
    date_range = request.GET.get('date')
    local_datetime_str = request.GET.get('local_datetime')
    from datetime import datetime
    if local_datetime_str:
        try:
            user_now = datetime.fromisoformat(local_datetime_str.replace('Z', '+00:00'))
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

    # Creator type filter (general users vs leaders/admins)
    creator_type = request.GET.get('creator_type', '').strip()
    if creator_type == 'general':
        # Filter to show only sessions created by general users (not admin, not leader)
        # Exclude: staff, superusers, and users with is_student_leader=True
        # Users without profiles are considered general (they don't have is_student_leader=True)
        # Use select_related to ensure owner and profile are loaded efficiently
        qs = qs.select_related('owner', 'owner__profile').exclude(
            Q(owner__is_staff=True) | 
            Q(owner__is_superuser=True) | 
            Q(owner__profile__is_student_leader=True)
        ).distinct()
    elif creator_type == 'leaders-admins':
        # Filter to show only sessions created by admins or student leaders
        qs = qs.select_related('owner', 'owner__profile').filter(
            Q(owner__is_staff=True) | 
            Q(owner__is_superuser=True) | 
            Q(owner__profile__is_student_leader=True)
        ).distinct()

    # Compute next occurrence for recurring sessions and filter out past ones
    def compute_next_occurrence(session, now_dt):
        """Return (next_start, next_end) or (None, None) if no future occurrence."""
        start = session.start_time
        end = session.end_time
        duration = (end - start) if (end and start) else None
        if getattr(session, 'is_recurring', False) and getattr(session, 'recurrence_type', 'none') != 'none':
            freq = session.recurrence_type
            interval = session.recurrence_interval or 1
            current = start
            # Advance until current >= now_dt
            while current < now_dt:
                if freq == 'daily':
                    current += timedelta(days=interval)
                elif freq == 'weekly':
                    current += timedelta(weeks=interval)
                elif freq == 'monthly':
                    # naive month add: add 30 days per interval
                    current += timedelta(days=30 * interval)
                else:
                    break
                # hard stop if we somehow loop too much
                if (current - start).days > 365 * 5:
                    break
            # Check end boundary
            until = getattr(session, 'recurrence_end_date', None)
            if until and current > until:
                return (None, None)
            next_start = current
            next_end = (current + duration) if duration else None
            return (next_start, next_end)
        else:
            # Non-recurring
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
        elif date_range == 'tomorrow' and ns.date() != (user_now + timedelta(days=1)).date():
            include = False
        elif date_range == 'week':
            week_later = user_now + timedelta(days=7)
            if not (user_now.date() <= ns.date() <= week_later.date()):
                include = False
        elif date_range == 'month':
            month_later = user_now + timedelta(days=31)
            if not (user_now.date() <= ns.date() <= month_later.date()):
                include = False
        if not include:
            continue
        # Attach display times for template
        s.display_start_time = ns
        s.display_end_time = ne
        processed.append(s)

    # Sort by next occurrence time
    processed.sort(key=lambda x: getattr(x, 'display_start_time', x.start_time))

    # Get user's education level and subjects list
    user_education_level = request.user.profile.education_level
    subjects = SubjectTag.objects.filter(education_level=user_education_level).order_by('name')

    # Stats - count sessions happening today (based on user's local time)
    user_now_date = user_now.date()
    upcoming_sessions_count = sum(1 for s in processed if getattr(s, 'display_start_time', s.start_time).date() == user_now_date)

    context = {
        'sessions': processed,
        'subjects': subjects,
        'user_education_level': user_education_level,
        'upcoming_sessions_count': upcoming_sessions_count,
        'q': q or '',
        'date_range': date_range or '',
        'session_type': session_type or '',
        'creator_type': creator_type,
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
        StudySession.objects.select_related('owner')
        .prefetch_related('subjects', 'memberships__user', 'messages__user', 'attendance__user')
        .annotate(num_members=Count('memberships')),
        pk=pk
    )
    is_member = False
    if request.user.is_authenticated:
        is_member = SessionMember.objects.filter(session=session, user=request.user).exists()

    # Check if user can mark attendance (leader/admin and session has started)
    can_mark_attendance = False
    if request.user.is_authenticated:
        is_leader_or_admin = (
            request.user.is_staff or 
            request.user.is_superuser or 
            (hasattr(request.user, 'profile') and request.user.profile.is_student_leader)
        )
        session_started = timezone.now() >= session.start_time
        can_mark_attendance = is_leader_or_admin and session_started and request.user == session.owner

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
        
        # Check if there's a spot available and notify waitlisted users
        current_count = SessionMember.objects.filter(session=session).count()
        if current_count < session.capacity:
            # Get the first person on the waitlist
            first_waitlist = WaitlistEntry.objects.filter(session=session).order_by('added_at').first()
            if first_waitlist:
                # Auto-promote the first waitlisted user
                SessionMember.objects.create(session=session, user=first_waitlist.user)
                first_waitlist.delete()
                
                # Send email notification to the promoted user
                try:
                    send_mail(
                        f'Spot Available in {session.title}',
                        f'Great news! A spot has opened up in "{session.title}" and you have been automatically added to the session.\n\n'
                        f'Session Details:\n'
                        f'Date: {session.start_time.strftime("%B %d, %Y")}\n'
                        f'Time: {session.start_time.strftime("%I:%M %p")}\n'
                        f'Location: {session.location_text if not session.is_virtual else "Virtual"}\n\n'
                        f'You can view the session details at: {request.build_absolute_uri(f"/session/{session.pk}/")}',
                        settings.DEFAULT_FROM_EMAIL,
                        [first_waitlist.user.email],
                        fail_silently=False,
                    )
                    messages.info(request, f'{first_waitlist.user.username} has been automatically added from the waitlist.')
                except Exception as e:
                    messages.warning(request, f'User promoted from waitlist but email notification failed: {str(e)}')
                
                # Notify remaining waitlisted users
                remaining_waitlist = WaitlistEntry.objects.filter(session=session).exclude(user=first_waitlist.user)
                for waitlist_entry in remaining_waitlist:
                    try:
                        send_mail(
                            f'Spot Available in {session.title}',
                            f'A spot has opened up in "{session.title}"!\n\n'
                            f'Session Details:\n'
                            f'Date: {session.start_time.strftime("%B %d, %Y")}\n'
                            f'Time: {session.start_time.strftime("%I:%M %p")}\n'
                            f'Location: {session.location_text if not session.is_virtual else "Virtual"}\n\n'
                            f'Join now at: {request.build_absolute_uri(f"/session/{session.pk}/")}',
                            settings.DEFAULT_FROM_EMAIL,
                            [waitlist_entry.user.email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        print(f"Failed to send waitlist notification to {waitlist_entry.user.email}: {str(e)}")
    else:
        messages.info(request, 'You were not a member.')
    return redirect('core:detail', pk=pk)


@login_required
@never_cache
def join_waitlist(request, pk):
    session = get_object_or_404(StudySession, pk=pk)
    # Only allow waitlist if full
    current_count = SessionMember.objects.filter(session=session).count()
    if current_count < session.capacity:
        messages.info(request, 'Session has spots. Please join directly.')
        return redirect('core:detail', pk=pk)
    WaitlistEntry.objects.get_or_create(session=session, user=request.user)
    messages.success(request, 'Added to waitlist!')
    return redirect('core:detail', pk=pk)


def session_ics(request, pk):
    session = get_object_or_404(StudySession, pk=pk)
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
    
    # Check permissions
    is_leader_or_admin = (
        request.user.is_staff or 
        request.user.is_superuser or 
        (hasattr(request.user, 'profile') and request.user.profile.is_student_leader)
    )
    
    if not is_leader_or_admin or request.user != session.owner:
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
