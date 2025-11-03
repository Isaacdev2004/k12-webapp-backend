from rest_framework import serializers
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from .models import CustomUser
from api.models import Subject,Program, Course, SubjectRecordingVideo, MockTestResult
from api.serializers import ProgramSerializer,SubjectSerializer,CourseSerializer,SubjectRecordingVideoSerializer,MockTestResultSerializer
from django.db.models import Prefetch



class UserSerializer(serializers.ModelSerializer):
    # programs_enroled = ProgramSerializer(many=True, read_only=True, source='programs')
    # subjects_enroled = SubjectSerializer(many=True, read_only=True, source='subjects')
    # course_enroled = CourseSerializer(many=True, read_only=True, source='courses')
    # mocktest_results_data = MockTestResultSerializer(many=True, read_only=True, source='mocktest_results_api')

    class Meta:
        model = CustomUser
        fields = '__all__'

    # def get_queryset(self):
    #     """
    #     Optimize the queryset with all necessary prefetch_related calls
    #     """
    #     return CustomUser.objects.prefetch_related(
    #         Prefetch(
    #             'programs',
    #             queryset=Program.objects.select_related('course').prefetch_related('subjects')
    #         ),
    #         Prefetch(
    #             'subjects',
    #             queryset=Subject.objects.select_related('course').prefetch_related(
    #                 Prefetch(
    #                     'subject_recording_videos',
    #                     queryset=SubjectRecordingVideo.objects.filter(is_active=True)
    #                 )
    #             )
    #         ),
    #         Prefetch(
    #             'courses',
    #             queryset=Course.objects.prefetch_related('subjects')
    #         ),
    #         Prefetch(
    #             'mocktest_results_api',
    #             queryset=MockTestResult.objects.select_related('mock_test__course').order_by('-completed_at')
    #         )
    #     )

    # def to_representation(self, instance):
    #     """
    #     Optimized to_representation method that uses prefetched data
    #     """
    #     # Get the request from context
    #     request = self.context.get('request')
    #     context = {'request': request}
        
    #     # Use prefetched data instead of making new queries
    #     representation = super().to_representation(instance)
        
    #     # Directly use prefetched relationships
    #     representation['programs_enroled'] = ProgramSerializer(
    #         instance.programs.all(),
    #         many=True,
    #         context=context
    #     ).data
        
    #     subjects = instance.subjects.all()
    #     representation['subjects_enroled'] = []
    #     for subject in subjects:
    #         subject_data = SubjectSerializer(subject, context=context).data
    #         # Use prefetched videos
    #         subject_data['subject_videos'] = SubjectRecordingVideoSerializer(
    #             subject.subject_recording_videos.all(),
    #             many=True,
    #             context=context
    #         ).data
    #         representation['subjects_enroled'].append(subject_data)
        
    #     representation['course_enroled'] = CourseSerializer(
    #         instance.courses.all(),
    #         many=True,
    #         context=context
    #     ).data
        
    #     representation['mocktest_results_data'] = MockTestResultSerializer(
    #         instance.mocktest_results_api.all(),
    #         many=True,
    #         context=context
    #     ).data
        
    #     return representation




class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'email', 'password', 'phone')
        extra_kwargs = {'password': {'write_only': True}}

    def save(self, **kwargs):
        user = super().save(**kwargs)
        user.user_type = 'student'  # Enforce 'student' user type
        user.save()
        return user



# accounts/serializers.py
from django.contrib.auth.models import User
from rest_framework import serializers

class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)
    token = serializers.CharField()
