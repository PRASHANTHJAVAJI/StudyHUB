from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import StudySession, SubjectTag, UserProfile

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        label='Email Address',
        help_text='Required. Enter a valid email address.'
    )
    education_level = forms.ChoiceField(
        choices=UserProfile.EDUCATION_LEVEL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Education Level',
        help_text='Select your current education level'
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2', 'education_level')
    
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
                user=user,
                defaults={'education_level': self.cleaned_data['education_level']}
            )
            if not created:
                profile.education_level = self.cleaned_data['education_level']
                profile.save()
        return user


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
        
        selected_subject = None
        if self.is_bound:
            selected_subject = self.data.get('subjects')
        
        # Handle building_name and room_number for existing sessions
        if self.instance and self.instance.pk:
            if not self.instance.is_virtual and self.instance.location_text:
                # Parse location_text to extract building and room
                location_parts = self.instance.location_text.split(' - Room ')
                if len(location_parts) == 2:
                    self.fields['building_name'].initial = location_parts[0]
                    self.fields['room_number'].initial = location_parts[1]
        
        if user and user.is_authenticated:
            try:
                if not hasattr(user, 'profile'):
                    UserProfile.objects.get_or_create(user=user)
                # Build department choices from ALL subjects
                all_departments_qs = SubjectTag.objects.values_list('department', flat=True).distinct()
                all_departments = sorted([d for d in all_departments_qs if d])
                department_choices = [('', '-- Select Department --')] + [(dept, dept) for dept in all_departments]
                # Append 'Other' if there are subjects without a department
                if SubjectTag.objects.filter(department='').exists():
                    department_choices.append(('Other', 'Other'))
                self.fields['department'] = forms.ChoiceField(
                    choices=department_choices,
                    widget=forms.Select(attrs={'class': 'form-control', 'required': True}),
                    label='Department',
                    help_text='First select a department, then choose a subject'
                )

                # Subjects choices: include ALL subjects so any department selection is valid
                all_subjects_qs = SubjectTag.objects.all().order_by('department', 'name')
                if selected_subject:
                    try:
                        selected_subject_obj = SubjectTag.objects.get(id=selected_subject)
                        if selected_subject_obj not in all_subjects_qs:
                            all_subjects_qs = list(all_subjects_qs) + [selected_subject_obj]
                    except SubjectTag.DoesNotExist:
                        pass
                self.fields['subjects'] = forms.ChoiceField(
                    choices=[('', '-- Select Department First --')] + [(str(subj.id), subj.name) for subj in all_subjects_qs],
                    widget=forms.Select(attrs={'class': 'form-control', 'required': True}),
                    label='Subject',
                    help_text='Select a subject from the chosen department'
                )

                # subjects_data for JS: group ALL subjects by department
                self.all_subjects = {}
                for subject in all_subjects_qs:
                    dept = subject.department or 'Other'
                    if dept not in self.all_subjects:
                        self.all_subjects[dept] = []
                    subject_data = (str(subject.id), str(subject.name))
                    self.all_subjects[dept].append(subject_data)
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
            'title', 'description', 'subjects',
            'start_time', 'end_time',
            'is_virtual', 'virtual_link', 'location_text',
            'capacity', 'is_recurring', 'recurrence_type', 
            'recurrence_interval', 'recurrence_end_date'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
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
