# core/serializers.py
from rest_framework import serializers
from .models import StudySession, SubjectTag, Message

class SubjectTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectTag
        fields = ['id', 'name', 'slug']

class StudySessionSerializer(serializers.ModelSerializer):
    subjects = SubjectTagSerializer(many=True, read_only=True)
    subject_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=SubjectTag.objects.all(), source='subjects'
    )
    members_count = serializers.IntegerField(read_only=True)
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)

    class Meta:
        model = StudySession
        fields = [
            'id', 'title', 'description', 'subjects', 'subject_ids', 'start_time', 'end_time',
            'is_virtual', 'virtual_link', 'location_text', 'capacity', 'members_count', 'owner_id', 'created_at'
        ]

    def validate(self, data):
        start = data.get('start_time') or getattr(self.instance, 'start_time', None)
        end = data.get('end_time') or getattr(self.instance, 'end_time', None)
        is_virtual = data.get('is_virtual') if 'is_virtual' in data else getattr(self.instance, 'is_virtual', False)
        virtual_link = data.get('virtual_link') if 'virtual_link' in data else getattr(self.instance, 'virtual_link', '')
        if end and start and end <= start:
            raise serializers.ValidationError({'end_time': 'End time must be after start time.'})
        if is_virtual and not virtual_link:
            raise serializers.ValidationError({'virtual_link': 'Virtual sessions require a link.'})
        return data

class MessageSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'user_id', 'text', 'created_at']
