from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import StudySession, SubjectTag, UserProfile, Department, Major, Minor

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        label='Email Address',
        help_text='Required. Enter a valid email address.'
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('username', 'password1', 'password2'):
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['class'] = 'form-control'
    
    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with that email address already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Ensure profile exists before accessing it
            profile, created = UserProfile.objects.get_or_create(
                user=user
            )
        return user


class EditAccountForm(forms.ModelForm):
    """Edit username and email on the User model."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        label='Email Address',
    )

    class Meta:
        model = User
        fields = ('username', 'email')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = ''

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('That email is already in use by another account.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        qs = User.objects.filter(username__iexact=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('That username is already taken.')
        return username


class EditProfileForm(forms.ModelForm):
    """Edit academic fields on UserProfile. Fields shown depend on user role."""
    class Meta:
        model = UserProfile
        fields = ('education_level', 'department', 'major', 'minor')
        widgets = {
            'education_level': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'major': forms.Select(attrs={'class': 'form-select'}),
            'minor': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        is_faculty = self.user and not (self.user.is_staff or self.user.is_superuser) and getattr(getattr(self.user, 'profile', None), 'is_faculty', False)

        if is_faculty:
            # Faculty: department only
            self.fields.pop('education_level', None)
            self.fields.pop('major', None)
            self.fields.pop('minor', None)
            self.fields['department'].queryset = Department.objects.order_by('name')
            self.fields['department'].required = True
            self.fields['department'].empty_label = 'Select a department'
        else:
            self.fields['department'].queryset = Department.objects.order_by('name')
            self.fields['department'].required = True
            self.fields['major'].required = True
            self.fields['minor'].required = False
            self.fields['department'].empty_label = 'Select a department'
            self.fields['major'].empty_label = 'Select a major'
            self.fields['minor'].empty_label = 'None'

            department_id = None
            if self.is_bound:
                department_id = self.data.get('department') or None
            elif self.instance and self.instance.department_id:
                department_id = self.instance.department_id

            if department_id:
                self.fields['major'].queryset = Major.objects.filter(department_id=department_id).order_by('name')
                self.fields['minor'].queryset = Minor.objects.filter(department_id=department_id).order_by('name')
            else:
                self.fields['major'].queryset = Major.objects.none()
                self.fields['minor'].queryset = Minor.objects.none()


class ProfileSetupForm(forms.ModelForm):
    """Onboarding form. Fields shown depend on user role passed via user= kwarg."""
    class Meta:
        model = UserProfile
        fields = ('education_level', 'department', 'major', 'minor')
        widgets = {
            'education_level': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            'department': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            'major': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            'minor': forms.Select(attrs={'class': 'form-select form-select-lg'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        is_faculty = self.user and not (self.user.is_staff or self.user.is_superuser) and getattr(getattr(self.user, 'profile', None), 'is_faculty', False)

        if is_faculty:
            self.fields.pop('education_level', None)
            self.fields.pop('major', None)
            self.fields.pop('minor', None)
            self.fields['department'].queryset = Department.objects.order_by('name')
            self.fields['department'].required = True
            self.fields['department'].empty_label = 'Select your department'
        else:
            self.fields['department'].queryset = Department.objects.order_by('name')
            department_id = None
            if self.is_bound:
                department_id = self.data.get('department') or None
            elif self.instance and self.instance.department_id:
                department_id = self.instance.department_id

            if department_id:
                self.fields['major'].queryset = Major.objects.filter(department_id=department_id).order_by('name')
                self.fields['minor'].queryset = Minor.objects.filter(department_id=department_id).order_by('name')
            else:
                self.fields['major'].queryset = Major.objects.none()
                self.fields['minor'].queryset = Minor.objects.none()

            self.fields['department'].required = True
            self.fields['major'].required = True
            self.fields['minor'].required = False
            self.fields['department'].empty_label = 'Select a department'
            self.fields['major'].empty_label = 'Select a major'
            self.fields['minor'].empty_label = 'Select a minor (optional)'


class StudySessionForm(forms.ModelForm):
    building_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Building Name'
    )
    room_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Room Number'
    )
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.user = user  # stored for clean() validation

        is_privileged = False
        is_admin_or_faculty = False
        profile = None
        profile_dept_name = None
        if user and user.is_authenticated:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            is_admin_or_faculty = bool(
                user.is_staff or user.is_superuser or
                (profile and getattr(profile, 'is_faculty', False))
            )
            is_privileged = is_admin_or_faculty or bool(
                profile and getattr(profile, 'is_student_leader', False)
            )
            if profile and profile.department:
                profile_dept_name = profile.department.name

        # Normal users with a profile department get the department field locked/hidden
        is_dept_locked = not is_privileged and profile_dept_name is not None

        # --- Restrict category choices by role ---
        if 'category' in self.fields:
            from .models import StudySession as _SS
            if is_admin_or_faculty:
                pass  # all three options available
            elif is_privileged:  # student leader
                self.fields['category'].choices = [
                    (_SS.CATEGORY_GENERAL, 'General'),
                    (_SS.CATEGORY_STUDY, 'Study Session'),
                ]
            else:
                # Regular users: General only, hide the field
                self.fields['category'].choices = [(_SS.CATEGORY_GENERAL, 'General')]
                self.fields['category'].widget = forms.HiddenInput()

        # --- Department visibility ---
        # Always remove the raw M2M field.
        # Visibility dropdown shown for privileged users (student leaders, faculty, admins).
        # Regular users get no dropdown — their department is assigned automatically in the view.
        self.fields.pop('visible_departments', None)
        if is_privileged:
            initial_vis = 'department'
            if self.instance and self.instance.pk:
                all_count = Department.objects.count()
                vd_count = self.instance.visible_departments.count()
                if all_count > 0 and vd_count >= all_count:
                    initial_vis = 'all'
            vis_field = forms.ChoiceField(
                choices=[
                    ('department', 'My Department Only'),
                    ('all', 'All Departments'),
                ],
                label='Visibility',
                widget=forms.Select(attrs={'class': 'form-control'}),
                required=True,
            )
            vis_field.initial = initial_vis
            self.fields['visibility'] = vis_field

        selected_subject = None
        if self.is_bound:
            selected_subject = self.data.get('subjects')

        # Handle building_name and room_number for existing sessions
        if self.instance and self.instance.pk:
            if not self.instance.is_virtual and self.instance.location_text:
                location_parts = self.instance.location_text.split(' - Room ')
                if len(location_parts) == 2:
                    self.fields['building_name'].initial = location_parts[0]
                    self.fields['room_number'].initial = location_parts[1]

        if user and user.is_authenticated:
            try:
                education_level = profile.education_level if profile else SubjectTag.BACHELORS

                if is_dept_locked:
                    # Normal user: hide the department field, lock to profile department
                    dept_name = profile_dept_name
                    self.fields['department'] = forms.CharField(
                        widget=forms.HiddenInput(),
                        initial=dept_name,
                        required=False,
                    )
                    # Filter subjects to profile department only
                    all_subjects_qs = SubjectTag.objects.filter(
                        education_level=education_level,
                        department=dept_name,
                    ).order_by('name')
                    if selected_subject:
                        try:
                            sel_obj = SubjectTag.objects.get(id=selected_subject)
                            if sel_obj not in list(all_subjects_qs):
                                all_subjects_qs = list(all_subjects_qs) + [sel_obj]
                        except SubjectTag.DoesNotExist:
                            pass
                    subject_choices = [('', '-- Select a Subject --')]
                    subject_choices += [(str(s.id), s.name) for s in all_subjects_qs]
                    self.fields['subjects'] = forms.ChoiceField(
                        choices=subject_choices,
                        widget=forms.Select(attrs={'class': 'form-control', 'required': True}),
                        label='Subject',
                        help_text=f'Subjects available in {dept_name}',
                    )
                    self.all_subjects = {}  # no dept switcher needed for normal users
                else:
                    # Privileged user: full department dropdown
                    department_names = list(Department.objects.order_by('name').values_list('name', flat=True))
                    if not department_names:
                        department_names = sorted(
                            [d for d in SubjectTag.objects.values_list('department', flat=True).distinct() if d]
                        )
                    if not department_names:
                        default_departments = ["Computer Science", "Electrical Science", "Architecture"]
                        for dept_name in default_departments:
                            Department.objects.get_or_create(name=dept_name)
                        department_names = default_departments
                    department_choices = [('', '-- Select Department --')] + [(dept, dept) for dept in department_names]
                    if SubjectTag.objects.filter(department='').exists():
                        department_choices.append(('Other', 'Other'))

                    selected_department = None
                    if self.is_bound:
                        selected_department = self.data.get('department') or None
                    elif self.instance and self.instance.pk:
                        existing_subject = self.instance.subjects.first()
                        if existing_subject and existing_subject.department:
                            selected_department = existing_subject.department
                    elif profile and profile.department:
                        selected_department = profile.department.name

                    department_help = 'First select a department, then choose a subject'
                    if len(department_choices) == 1:
                        department_help = 'No departments available. Add them in the admin panel.'

                    self.fields['department'] = forms.ChoiceField(
                        choices=department_choices,
                        widget=forms.Select(attrs={'class': 'form-control', 'required': True}),
                        label='Department',
                        help_text=department_help,
                    )
                    if selected_department:
                        self.fields['department'].initial = selected_department

                    all_subjects_qs = SubjectTag.objects.filter(education_level=education_level).order_by('department', 'name')
                    if selected_department:
                        if selected_department == 'Other':
                            all_subjects_qs = all_subjects_qs.filter(department='')
                        else:
                            all_subjects_qs = all_subjects_qs.filter(department=selected_department)
                    if selected_subject:
                        try:
                            selected_subject_obj = SubjectTag.objects.get(id=selected_subject)
                            if selected_subject_obj not in all_subjects_qs:
                                all_subjects_qs = list(all_subjects_qs) + [selected_subject_obj]
                        except SubjectTag.DoesNotExist:
                            pass

                    subject_choices = [('', '-- Select Department First --')]
                    subject_choices += [(str(subj.id), subj.name) for subj in all_subjects_qs]
                    if len(subject_choices) == 1:
                        subject_choices = [('', '-- No Subjects Available --')]

                    subject_help = 'Select a subject from the chosen department'
                    if subject_choices == [('', '-- No Subjects Available --')]:
                        subject_help = 'No subjects available. Add them in the admin panel.'

                    self.fields['subjects'] = forms.ChoiceField(
                        choices=subject_choices,
                        widget=forms.Select(attrs={'class': 'form-control', 'required': True}),
                        label='Subject',
                        help_text=subject_help,
                    )

                    # subjects_data for JS: group subjects by department
                    all_subjects_for_js = SubjectTag.objects.filter(education_level=education_level).order_by('department', 'name')
                    self.all_subjects = {}
                    for subject in all_subjects_for_js:
                        dept = subject.department or 'Other'
                        if dept not in self.all_subjects:
                            self.all_subjects[dept] = []
                        self.all_subjects[dept].append((str(subject.id), str(subject.name)))

            except Exception:
                self.fields['department'] = forms.ChoiceField(
                    choices=[('', 'Error loading departments')],
                    widget=forms.Select(attrs={'class': 'form-control'}),
                    label='Department',
                    help_text='Error loading departments. Please try again.'
                )
                self.fields['subjects'] = forms.ChoiceField(
                    choices=[('', 'Error loading subjects')],
                    widget=forms.Select(attrs={'class': 'form-control'}),
                    label='Subject',
                    help_text='Error loading subjects. Please try again.'
                )
        else:
            self.fields['department'] = forms.ChoiceField(
                choices=[('', 'Please login to see departments')],
                widget=forms.Select(attrs={'class': 'form-control'}),
                label='Department',
                help_text='Login required to view departments'
            )
            self.fields['subjects'] = forms.ChoiceField(
                choices=[('', 'Please login to see subjects')],
                widget=forms.Select(attrs={'class': 'form-control'}),
                label='Subject',
                help_text='Login required to view subjects'
            )
    
    class Meta:
        model = StudySession
        fields = [
            'title', 'description', 'category', 'subjects', 'visible_departments',
            'start_time', 'end_time',
            'is_virtual', 'virtual_link', 'location_text',
            'capacity', 'is_recurring', 'recurrence_type',
            'recurrence_interval', 'recurrence_end_date'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'required': True, 'rows': 4}),
            'start_time': forms.DateTimeInput(attrs={
                'type': 'datetime-local', 
                'class': 'form-control', 
                'required': True
            }),
            'end_time': forms.DateTimeInput(attrs={
                'type': 'datetime-local', 
                'class': 'form-control',
                'min': ''  # No minimum constraint
            }),
            'virtual_link': forms.URLInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'recurrence_type': forms.Select(attrs={'class': 'form-control'}),
            'recurrence_interval': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'recurrence_end_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local', 
                'class': 'form-control'
            }),
        }

    def clean(self):
        cleaned = super().clean()

        # Only admins and faculty can create conferences
        category = cleaned.get('category')
        if category == 'conference':
            u = getattr(self, 'user', None)
            allowed = u and (
                u.is_staff or u.is_superuser or
                getattr(getattr(u, 'profile', None), 'is_faculty', False)
            )
            if not allowed:
                self.add_error('category', 'Only admins and faculty can create conferences.')

        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        
        if start and end and end <= start:
            self.add_error('end_time', 'End time must be after start time.')
        
        is_virtual = cleaned.get('is_virtual')
        link = cleaned.get('virtual_link', '')
        building_name = cleaned.get('building_name', '')
        room_number = cleaned.get('room_number', '')
        
        if is_virtual:
            if not link:
                self.add_error('virtual_link', 'Provide a virtual meeting link for virtual sessions.')
        else:
            if not building_name:
                self.add_error('building_name', 'Provide a building name for in-person sessions.')
            if not room_number:
                self.add_error('room_number', 'Provide a room number for in-person sessions.')
        
        # Validate recurring fields
        is_recurring = cleaned.get('is_recurring', False)
        recurrence_type = cleaned.get('recurrence_type', 'none')
        recurrence_end_date = cleaned.get('recurrence_end_date')
        
        if is_recurring:
            if recurrence_type == 'none':
                self.add_error('recurrence_type', 'Select a recurrence type for recurring sessions.')
            if recurrence_end_date and recurrence_end_date <= start:
                self.add_error('recurrence_end_date', 'Recurrence end date must be after the start time.')
        
        return cleaned
