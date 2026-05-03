# core/admin.py
from django.contrib import admin
from .models import StudySession, SessionMember, Message, SubjectTag, UserProfile, Department, Major, Minor


class SessionMemberInline(admin.TabularInline):
    model = SessionMember
    extra = 0


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'start_time', 'end_time', 'is_virtual', 'capacity')
    list_filter = ('is_virtual', 'start_time', 'visible_departments')
    search_fields = ('title', 'description', 'owner__username')
    inlines = [SessionMemberInline, MessageInline]
    filter_horizontal = ('subjects', 'visible_departments')


@admin.register(SubjectTag)
class SubjectTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'education_level', 'department')
    list_filter = ('education_level', 'department')
    search_fields = ('name', 'slug')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role_label', 'education_level', 'department', 'major', 'minor', 'onboarding_complete', 'is_student_leader', 'is_faculty', 'created_at')
    list_filter = ('education_level', 'onboarding_complete', 'is_student_leader', 'is_faculty')
    search_fields = ('user__username', 'user__email', 'department__name', 'major__name', 'minor__name')

    # Fields shown for non-admin users (full academic profile)
    STUDENT_FIELDS = ('user', 'education_level', 'department', 'major', 'minor', 'onboarding_complete', 'is_student_leader', 'is_faculty')
    # Fields shown for faculty (department only)
    FACULTY_FIELDS = ('user', 'department', 'onboarding_complete', 'is_student_leader', 'is_faculty')
    # Fields shown for site admins (no academic info)
    ADMIN_FIELDS = ('user', 'onboarding_complete', 'is_student_leader', 'is_faculty')

    def get_fields(self, request, obj=None):
        if obj is None:
            return self.STUDENT_FIELDS
        if obj.user.is_staff or obj.user.is_superuser:
            return self.ADMIN_FIELDS
        if obj.is_faculty:
            return self.FACULTY_FIELDS
        return self.STUDENT_FIELDS

    @admin.display(description='Role')
    def role_label(self, obj):
        if obj.user.is_staff or obj.user.is_superuser:
            return 'Admin'
        if obj.is_faculty:
            return 'Faculty'
        if obj.is_student_leader:
            return 'Student Leader'
        return 'Student'


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Major)
class MajorAdmin(admin.ModelAdmin):
    list_display = ('name', 'department')
    list_filter = ('department',)
    search_fields = ('name',)


@admin.register(Minor)
class MinorAdmin(admin.ModelAdmin):
    list_display = ('name', 'department')
    list_filter = ('department',)
    search_fields = ('name',)
