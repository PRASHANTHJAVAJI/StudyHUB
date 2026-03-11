# core/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone

class SubjectTag(models.Model):
    BACHELORS = 'bachelors'
    MASTERS = 'masters'
    PHD = 'phd'
    
    EDUCATION_LEVEL_CHOICES = [
        (BACHELORS, 'Bachelor'),
        (MASTERS, 'Masters'),
        (PHD, 'Doctorate/PhD'),
    ]
    
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVEL_CHOICES, default=BACHELORS)
    department = models.CharField(max_length=60, blank=True)  # New field for department

    def __str__(self):
        return f"{self.name} ({self.get_education_level_display()})"
    
    class Meta:
        unique_together = ['name', 'education_level']

class StudySession(models.Model):
    RECURRENCE_CHOICES = [
        ('none', 'No Recurrence'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_sessions')
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    subjects = models.ManyToManyField(SubjectTag, blank=True, related_name='sessions')
    visible_departments = models.ManyToManyField('Department', blank=True, related_name='visible_sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    is_virtual = models.BooleanField(default=False)
    virtual_link = models.URLField(blank=True)
    location_text = models.CharField(max_length=140, blank=True)
    capacity = models.PositiveIntegerField(default=8)
    created_at = models.DateTimeField(default=timezone.now)
    
    # Recurring fields
    is_recurring = models.BooleanField(default=False)
    recurrence_type = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='none')
    recurrence_interval = models.PositiveIntegerField(default=1, help_text="Repeat every X days/weeks/months")
    recurrence_end_date = models.DateTimeField(null=True, blank=True, help_text="When to stop recurring")
    parent_session = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='recurring_instances')

    class Meta:
        indexes = [models.Index(fields=['start_time'])]
        ordering = ['start_time']

    def __str__(self):
        return f"{self.title} @ {self.start_time:%b %d %H:%M}"

class SessionMember(models.Model):
    MEMBER = 'member'
    HOST = 'host'
    ROLE_CHOICES = [(MEMBER, 'Member'), (HOST, 'Host')]

    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='session_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=MEMBER)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'user'], name='unique_member_per_session')
        ]

class Message(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']

class WaitlistEntry(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='waitlist')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='session_waitlist')
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'user'], name='unique_waitlist_entry')
        ]

class Attendance(models.Model):
    """Track attendance for sessions created by leaders/admins."""
    PRESENT = 'present'
    ABSENT = 'absent'
    STATUS_CHOICES = [
        (PRESENT, 'Present'),
        (ABSENT, 'Absent'),
    ]
    
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='attendance')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='session_attendance')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='marked_attendance')
    marked_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'user'], name='unique_attendance_entry')
        ]
        verbose_name_plural = 'Attendance'
    
    def __str__(self):
        return f"{self.user.username} - {self.session.title} - {self.get_status_display()}"
class StudyNote(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class UserProfile(models.Model):
    BACHELORS = 'bachelors'
    MASTERS = 'masters'
    PHD = 'phd'
    
    EDUCATION_LEVEL_CHOICES = [
        (BACHELORS, 'Bachelor'),
        (MASTERS, 'Masters'),
        (PHD, 'Doctorate/PhD'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVEL_CHOICES, default=BACHELORS)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True)
    major = models.ForeignKey('Major', on_delete=models.SET_NULL, null=True, blank=True)
    minor = models.ForeignKey('Minor', on_delete=models.SET_NULL, null=True, blank=True)
    onboarding_complete = models.BooleanField(default=False)
    is_student_leader = models.BooleanField(default=False)  # <-- Added field
    is_faculty = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_education_level_display()}"
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


class Department(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Major(models.Model):
    name = models.CharField(max_length=80, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='majors')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Minor(models.Model):
    name = models.CharField(max_length=80, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='minors')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
