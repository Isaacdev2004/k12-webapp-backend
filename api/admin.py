from django.contrib import admin
from .models import Program, SubjectFee, Course, Subject, Chapter, PaymentPicture, Topic, MCQ, MCQQuestion, Video, Content, LiveClass, MockTest, MockTestQuestion, Note, McqResult
from .models import SubjectRecordingVideo, SubjectNote,QrPayment,OnePGPayment,QrPaymentTransaction, ZoomRecording, ZoomWebhookLog, ZoomAllowedHost, NCHLPayment, BillingHistory

from django.utils.html import format_html
from django.urls import path, reverse
from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from django import forms

from rangefilter.filters import DateRangeFilter
from import_export import resources
from import_export.admin import ExportMixin
from import_export.formats import base_formats
from django.db.models import F, Window
from django.db.models.functions import Rank


def clean_image_url(url):
    """
    Remove query parameters from signed URLs before saving to database.
    Strips everything after '?' to remove temporary signing parameters like:
    ?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...
    
    This prevents storing temporary signed URLs that will expire.
    """
    if not url or pd.isna(url) or str(url).lower() == 'nan':
        return ''
    
    url = str(url).strip()
    # Strip query parameters (everything after '?')
    url = url.split('?')[0]
    
    return url if url else ''


admin.site.register(McqResult)
class SubjectFeeInline(admin.TabularInline):
    model = SubjectFee
    extra = 0
    min_num = 1
    verbose_name = "Subject Fee"
    verbose_name_plural = "Subject Fees"

class ProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'published', 'has_subjects', 'has_chapters', 'has_topics', 'has_chapterwise_tests', 'has_chapterwise_notes', 'has_chapterwise_videos', 'has_mock_tests', 'has_live_classes', 'has_recorded_lectures', 'has_discussions', 'has_lecture_notes')
    search_fields = ('name',)
    inlines = [SubjectFeeInline]
    filter_horizontal = ('subjects','participant_users')
    exclude = ('payment_picture',)



class SubjectInline(admin.TabularInline):
    model = Subject
    extra = 1
    min_num = 1
    verbose_name = "Subject"
    verbose_name_plural = "Subjects"

class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 1
    min_num = 1
    verbose_name = "Chapter"
    verbose_name_plural = "Chapters"

class TopicInline(admin.TabularInline):
    model = Topic
    extra = 1
    min_num = 1
    verbose_name = "Topic"
    verbose_name_plural = "Topics"


class CourseAdmin(admin.ModelAdmin):
    list_display = ('name',  'published')
    # search_fields = ('name',)
    inlines = [SubjectInline]

class SubjectRecordingVideoInline(admin.TabularInline):
    model = SubjectRecordingVideo
    extra = 1
    min_num = 0
    verbose_name = "Subject Recording Video"
    verbose_name_plural = "Subject Recording Videos"
    readonly_fields = ('is_auto_created',)
    fields = ('title', 'video_url', 'video_duration', 'is_active', 'is_free', 'is_auto_created')

class SubjectNoteInline(admin.TabularInline):
    model = SubjectNote
    extra = 1
    min_num = 0
    verbose_name = "Subject Note"
    verbose_name_plural = "Subject Notes"

class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'course')
    search_fields = ('name', 'course__name')
    inlines = [SubjectRecordingVideoInline, SubjectNoteInline, ChapterInline]

class ChapterAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject')
    search_fields = ('name', 'subject__name')
    inlines = [TopicInline]


@admin.register(PaymentPicture)
class PaymentPictureAdmin(admin.ModelAdmin):
    list_display = ['user', 'payment_image_thumbnail', 'program','course', 'is_verified', 'total_amount', 'date', 'status', 'rejected_reason']
    list_filter = ['subject', 'user', 'is_verified', 'program','course' ,'status']
    search_fields = ['payment_image', 'program__name', 'user__username']

    fieldsets = (
        (None, {
            'fields': ('user', 'payment_image', 'program','course', 'subject', 'is_verified', 'total_amount', 'status', 'rejected_reason')
        }),
    )

    readonly_fields = ('payment_image_thumbnail',)

    def payment_image_thumbnail(self, obj):
        if obj.payment_image:
            return mark_safe(f'<a href="{obj.payment_image.url}" target="_blank"><img src="{obj.payment_image.url}" width="100" height="100" /></a>')
        return "-"
    payment_image_thumbnail.short_description = 'Payment Image'

    def save_model(self, request, obj, form, change):
        if obj.status != 'rejected':
            obj.rejected_reason = None  
        super().save_model(request, obj, form, change)


class VideoInline(admin.TabularInline):
    model = Video
    extra = 1
    min_num = 0
    verbose_name = "Video"
    verbose_name_plural = "Videos"

class MCQInline(admin.TabularInline):
    model = MCQ
    extra = 1
    min_num = 0
    verbose_name = "MCQ"
    verbose_name_plural = "MCQs"

class ContentInline(admin.TabularInline):
    model = Content
    extra = 1
    min_num = 0
    verbose_name = "Content"
    verbose_name_plural = "Contents"


class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'chapter')
    search_fields = ('name', 'chapter__name')
    inlines = [VideoInline, MCQInline, ContentInline]

# class MCQAdmin(admin.ModelAdmin):
#     list_display = ('title', 'topic', 'is_active', 'status', 'scheduled_start_time', 'duration', 'negMark')
#     search_fields = ('title', 'topic__name')
# admin.py

import pandas as pd
import csv
import io

from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, redirect
from django.template.response import TemplateResponse
from django.utils.html import format_html

from .models import MCQ, MCQQuestion
from .forms import MCQQuestionImportForm

@admin.register(MCQ)
class MCQAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'is_active', 'status', 'scheduled_start_time', 'duration', 'negMark','import_button')
    search_fields = ('title', 'topic__name')


    def import_button(self, obj):
        url = reverse('admin:mcq-import-questions', args=[obj.id])
        return format_html('<a class="button" href="{}">Import Questions</a>', url)
    import_button.short_description = 'Import'
    import_button.allow_tags = True

    # Add a custom admin view
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/import-questions/', self.admin_site.admin_view(self.import_questions), name='mcq-import-questions'),
        ]
        return custom_urls + urls

    def import_questions(self, request, object_id, *args, **kwargs):
        mcq = self.get_object(request, object_id)
        if not mcq:
            self.message_user(request, "MCQ not found.", level=messages.ERROR)
            return redirect('admin:api')  # Replace 'app' with your app name

        if request.method == 'POST':
            form = MCQQuestionImportForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data['file']
                try:
                    # Read the file based on its extension
                    if file.name.endswith('.csv'):
                        df = pd.read_csv(file)
                    elif file.name.endswith('.xls') or file.name.endswith('.xlsx'):
                        df = pd.read_excel(file)
                    elif file.name.endswith('.txt'):
                        df = pd.read_csv(file, delimiter='\t')
                    else:
                        self.message_user(request, "Unsupported file format. Please upload a CSV, Excel, or TXT file.", level=messages.ERROR)
                        return redirect(request.path)

                    # Check if the required columns are present in the file
                    required_columns = ['question', 'answer']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    if missing_columns:
                        self.message_user(request, f"Missing columns: {', '.join(missing_columns)}", level=messages.ERROR)
                        return redirect(request.path)

                    mcq_questions = []  # List to hold MCQQuestion instances for bulk insert
                    for index, row in df.iterrows():
                        # Optional: Validate each row's data here
                        mcq_question = MCQQuestion(
                            mcq=mcq,
                            question_text=row['question'],
                            question_image_url=clean_image_url(row.get('questionImage', '')),
                            option_0_text=row.get('options.0.text', ''),
                            option_1_text=row.get('options.1.text', ''),
                            option_2_text=row.get('options.2.text', ''),
                            option_3_text=row.get('options.3.text', ''),
                            option_0_image_url=clean_image_url(row.get('options.0.image', '')),
                            option_1_image_url=clean_image_url(row.get('options.1.image', '')),
                            option_2_image_url=clean_image_url(row.get('options.2.image', '')),
                            option_3_image_url=clean_image_url(row.get('options.3.image', '')),
                            answer=row['answer'],
                            weight=row.get('weight', 1),
                            explanation=row.get('explanation', ''),
                            explanation_image_url=clean_image_url(row.get('explanationimage', ''))
                        )
                        mcq_questions.append(mcq_question)

                    # Bulk create MCQQuestion instances
                    if mcq_questions:
                        MCQQuestion.objects.bulk_create(mcq_questions)
                        self.message_user(request, f"Successfully imported {len(mcq_questions)} questions.", level=messages.SUCCESS)
                    else:
                        self.message_user(request, "No valid questions found to import.", level=messages.WARNING)

                    return redirect(f'../../{object_id}/change/')  # Redirect to MCQ change page

                except Exception as e:
                    self.message_user(request, f"An error occurred: {str(e)}", level=messages.ERROR)
                    return redirect(request.path)
        else:
            form = MCQQuestionImportForm()

        context = {
            'form': form,
            'mcq': mcq,
            'opts': self.model._meta,
            'original': mcq,
            'title': 'Import MCQ Questions',
        }
        return TemplateResponse(request, 'admin/mcq_import_questions.html', context)


class MCQQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'mcq', 'answer', 'weight')
    search_fields = ('question_text', 'mcq__title')

class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'is_active', 'video_duration', 'created_at')
    search_fields = ('title', 'topic__name')

class ContentAdmin(admin.ModelAdmin):
    list_display = ('topic', 'title','is_active', 'is_free')
    search_fields = ('topic__name',)

class DaysOfWeekWidget(forms.CheckboxSelectMultiple):
    """Custom widget for selecting multiple days of the week"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = LiveClass.DAYS_OF_WEEK_CHOICES

class LiveClassForm(forms.ModelForm):
    days_of_week = forms.MultipleChoiceField(
        choices=LiveClass.DAYS_OF_WEEK_CHOICES,
        widget=DaysOfWeekWidget,
        required=False,
        help_text="Select days when recurrence type is weekly"
    )
    
    class Meta:
        model = LiveClass
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add JavaScript to show/hide days_of_week based on recurrence_type
        self.fields['recurrence_type'].widget.attrs.update({
            'onchange': 'toggleDaysOfWeek(this.value)'
        })
        
    def clean(self):
        cleaned_data = super().clean()
        recurrence_type = cleaned_data.get('recurrence_type')
        days_of_week = cleaned_data.get('days_of_week')
        
        if recurrence_type == 'weekly' and not days_of_week:
            raise forms.ValidationError("Please select at least one day when recurrence type is weekly.")
        
        # Convert string values to integers
        if days_of_week:
            cleaned_data['days_of_week'] = [int(day) for day in days_of_week]
        
        return cleaned_data

class LiveClassAdmin(admin.ModelAdmin):
    form = LiveClassForm
    list_display = ('title', 'subject', 'host', 'start_time', 'end_time', 'duration', 'recurrence_type', 'days_of_week_display', 'is_free')
    list_filter = ('subject', 'host', 'is_active', 'is_free', 'recurrence_type', 'day_of_week')
    search_fields = ('title', 'subject__name', 'host__email', 'zoom_meeting_id')
    readonly_fields = ('created_at', 'updated_at', 'duration', 'days_of_week_display')
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'subject', 'host', 'is_active', 'is_free')
        }),
        ('Timing', {
            'fields': ('start_time', 'end_time', 'duration')
        }),
        ('Recurrence Settings', {
            'fields': ('recurrence_type', 'days_of_week', 'recurrence_start_date', 'recurrence_end_date'),
            'description': 'Configure recurring class schedule. Select days of week when recurrence type is weekly.'
        }),
        ('Meeting Details', {
            'fields': ('live_url', 'zoom_meeting_id', 'zoom_password')
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at', 'days_of_week_display'),
            'classes': ('collapse',)
        }),
    )
    
    class Media:
        js = ('admin/js/liveclass_admin.js',)  # We'll create this JS file
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return form
    
# class MockTestAdmin(admin.ModelAdmin):
#     list_display = ('title', 'course', 'is_active', 'status', 'scheduled_start_time', 'duration', 'negMark')
#     search_fields = ('title', 'course__name')

class MockTestQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'mock_test', 'answer', 'weight')
    search_fields = ('question_text', 'mock_test__title')

class NoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'created_at')
    search_fields = ('title', 'course__name')

# Registering models with admin site
admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Chapter, ChapterAdmin)
# admin.site.register(PaymentPicture, PaymentPictureAdmin)
admin.site.register(Topic, TopicAdmin)
# admin.site.register(MCQ, MCQAdmin)
admin.site.register(MCQQuestion, MCQQuestionAdmin)
admin.site.register(Video, VideoAdmin)
admin.site.register(Content, ContentAdmin)
admin.site.register(LiveClass, LiveClassAdmin)
# admin.site.register(MockTest, MockTestAdmin)
admin.site.register(MockTestQuestion, MockTestQuestionAdmin)
admin.site.register(Note, NoteAdmin)


from .models import  MockTestResult

# @admin.register(McqResult)
# class McqResultAdmin(admin.ModelAdmin):
#     list_display = ('user', 'mcq', 'score', 'total_score', 'completed_at')
#     search_fields = ('user__username', 'mcq__title')  # Search by user and MCQ title
#     list_filter = ('completed_at',)  # Filter by the completion date


class MockTestResultResource(resources.ModelResource):
    rank = resources.Field()
    user_name = resources.Field()
    mock_test_name = resources.Field()

    def dehydrate_user_name(self, obj):
        if obj.user.first_name and obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return obj.user.username

    def dehydrate_mock_test_name(self, obj):
        return f"{obj.mock_test.title} - {obj.mock_test.course.name}"

    def dehydrate_rank(self, obj):
        return obj.rank if hasattr(obj, 'rank') else ''

    class Meta:
        model = MockTestResult
        fields = ('user_name', 'mock_test_name', 'rank', 'score', 'total_score', 'completed_at', 'correct_answers', 'wrong_answers', 'unattempted')
        export_order = ('rank', 'user_name', 'mock_test_name', 'score', 'total_score', 'correct_answers', 'wrong_answers', 'unattempted', 'completed_at')

@admin.register(MockTestResult)
class MockTestResultAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = MockTestResultResource
    list_display = ('user', 'mock_test', 'score', 'total_score', 'correct_answers', 'wrong_answers', 'unattempted', 'completed_at', 'get_rank')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'mock_test__title', 'mock_test__course__name')
    list_filter = (
        'mock_test__title',
        ('mock_test', admin.RelatedFieldListFilter),
        ('mock_test__course', admin.RelatedFieldListFilter),
        'completed_at',
    )
    formats = [base_formats.XLSX, base_formats.CSV]
    exclude = ('submissions_data',)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('user', 'mock_test', 'mock_test__course').annotate(
            rank=Window(
                expression=Rank(),
                partition_by=F('mock_test'),
                order_by=F('score').desc()
            )
        )
        return queryset

    def get_rank(self, obj):
        return obj.rank if hasattr(obj, 'rank') else ''
    get_rank.short_description = 'Rank'
    get_rank.admin_order_field = 'rank'


from .forms import MockTestQuestionImportForm

# MockTestAdmin with Import Functionality
@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'is_active', 'status', 'scheduled_start_time', 'duration', 'negMark', 'import_button')
    search_fields = ('title', 'course__name')

    def import_button(self, obj):
        url = reverse('admin:mocktest-import-questions', args=[obj.id])
        return format_html('<a class="button" href="{}">Import Questions</a>', url)
    import_button.short_description = 'Import'
    import_button.allow_tags = True  # Deprecated in Django 2.0+, safe with format_html

    # Optional: Add custom CSS for the button
    # class Media:
    #     css = {
    #         'all': ('your_app/css/admin_custom.css',)  # Ensure this path is correct
    #     }

    # Add a custom admin view
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/import-questions/', self.admin_site.admin_view(self.import_questions), name='mocktest-import-questions'),
        ]
        return custom_urls + urls

    def import_questions(self, request, object_id, *args, **kwargs):
        mock_test = self.get_object(request, object_id)
        if not mock_test:
            self.message_user(request, "Mock Test not found.", level=messages.ERROR)
            return redirect('admin:api')  # Replace 'your_app' with your app name

        if request.method == 'POST':
            form = MockTestQuestionImportForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data['file']
                try:
                    # Read the file based on its extension
                    if file.name.endswith('.csv'):
                        df = pd.read_csv(file)
                    elif file.name.endswith('.xls') or file.name.endswith('.xlsx'):
                        df = pd.read_excel(file)
                    elif file.name.endswith('.txt'):
                        df = pd.read_csv(file, delimiter='\t')
                    else:
                        self.message_user(request, "Unsupported file format. Please upload a CSV, Excel, or TXT file.", level=messages.ERROR)
                        return redirect(request.path)

                    # Check if the required columns are present in the file
                    required_columns = ['question', 'answer']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    if missing_columns:
                        self.message_user(request, f"Missing columns: {', '.join(missing_columns)}", level=messages.ERROR)
                        return redirect(request.path)

                    mocktest_questions = []  # List to hold MockTestQuestion instances for bulk insert
                    for index, row in df.iterrows():
                        # Validate required fields
                        if pd.isnull(row.get('question')) or pd.isnull(row.get('answer')):
                            self.message_user(request, f"Row {index + 2}: Missing 'question' or 'answer'. Skipping.", level=messages.WARNING)
                            continue

                        # Validate 'weight' is a number
                        try:
                            weight = float(row.get('weight', 1))
                        except (ValueError, TypeError):
                            self.message_user(request, f"Row {index + 2}: Invalid 'weight'. Using default value 1.", level=messages.WARNING)
                            weight = 1

                        # Optionally, check for duplicates
                        if MockTestQuestion.objects.filter(mock_test=mock_test, question_text=row['question']).exists():
                            self.message_user(request, f"Row {index + 2}: Duplicate question found. Skipping.", level=messages.WARNING)
                            continue

                        mocktest_question = MockTestQuestion(
                            mock_test=mock_test,
                            question_text=row['question'],
                            question_image_url=clean_image_url(row.get('questionImage', '')),
                            option_0_text=row.get('options.0.text', ''),
                            option_1_text=row.get('options.1.text', ''),
                            option_2_text=row.get('options.2.text', ''),
                            option_3_text=row.get('options.3.text', ''),
                            option_0_image_url=clean_image_url(row.get('options.0.image', '')),
                            option_1_image_url=clean_image_url(row.get('options.1.image', '')),
                            option_2_image_url=clean_image_url(row.get('options.2.image', '')),
                            option_3_image_url=clean_image_url(row.get('options.3.image', '')),
                            answer=row['answer'],
                            weight=weight,
                            explanation=row.get('explanation', ''),
                            explanation_image_url=clean_image_url(row.get('explanationimage', ''))
                        )
                        mocktest_questions.append(mocktest_question)

                    # Bulk create MockTestQuestion instances
                    if mocktest_questions:
                        MockTestQuestion.objects.bulk_create(mocktest_questions)
                        self.message_user(request, f"Successfully imported {len(mocktest_questions)} questions.", level=messages.SUCCESS)
                    else:
                        self.message_user(request, "No valid questions found to import.", level=messages.WARNING)

                    return redirect(f'../../{object_id}/change/')  # Redirect to MockTest change page

                except Exception as e:
                    self.message_user(request, f"An error occurred: {str(e)}", level=messages.ERROR)
                    return redirect(request.path)
        else:
            form = MockTestQuestionImportForm()

        context = {
            'form': form,
            'mock_test': mock_test,
            'opts': self.model._meta,
            'original': mock_test,
            'title': 'Import Mock Test Questions',
        }
        return TemplateResponse(request, 'admin/mocktest_import_questions.html', context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if not extra_context:
            extra_context = {}
        import_url = reverse('admin:mocktest-import-questions', args=[object_id])
        extra_context['import_url'] = import_url
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


class SubjectRecordingVideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'is_active', 'is_auto_created', 'video_duration', 'created_at', 'updated_at')
    search_fields = ('title', 'subject__name')
    list_filter = ('is_active', 'is_auto_created', 'subject')
    readonly_fields = ('is_auto_created',)  # Make auto_created read-only since it's set by system
    
    def changelist_view(self, request, extra_context=None):
        """Add custom context to the changelist view"""
        if extra_context is None:
            extra_context = {}
        
        # Add link to multipart upload page
        extra_context['multipart_upload_url'] = '/api/admin/video-upload/'
        extra_context['multipart_upload_button'] = format_html(
            '<a href="{}" class="addlink" style="background: #417690; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin-left: 10px;">'
            'Upload Large Video File</a>',
            '/api/admin/video-upload/'
        )
        
        return super().changelist_view(request, extra_context=extra_context)
    
    def add_view(self, request, form_url='', extra_context=None):
        """Add custom context to the add view"""
        if extra_context is None:
            extra_context = {}
            
        extra_context['multipart_upload_button'] = format_html(
            '<div style="background: #f8f8f8; border: 1px solid #ddd; padding: 15px; margin-bottom: 20px; border-radius: 4px;">'
            '<h3 style="margin-top: 0;">Need to upload a large video file?</h3>'
            '<p style="margin-bottom: 10px;">For video files larger than 100MB, use our specialized upload tool:</p>'
            '<a href="{}" class="button" style="background: #417690; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">'
            '🎥 Upload Large Video File</a>'
            '</div>',
            '/api/admin/video-upload/'
        )
        
        return super().add_view(request, form_url=form_url, extra_context=extra_context)

class SubjectNoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'is_active', 'created_at')
    search_fields = ('title', 'subject__name')
    list_filter = ('is_active', 'subject')

admin.site.register(SubjectRecordingVideo, SubjectRecordingVideoAdmin)
admin.site.register(SubjectNote, SubjectNoteAdmin)




@admin.register(QrPayment)
class QrPaymentAdmin(admin.ModelAdmin):
    list_display = ('name', 'accountno', 'is_active', 'payment_method', 'account_name', 'account_branch', 'qr_image')
    list_filter = ('payment_method', 'is_active')
    search_fields = ('name', 'accountno', 'account_name', 'account_branch')


@admin.register(OnePGPayment)
class OnePGPaymentAdmin(admin.ModelAdmin):
    list_display = ('merchant_txn_id', 'user', 'program', 'course', 'amount', 'service_charge', 'total_amount', 'status', 'transaction_date')
    list_filter = ('status', 'transaction_date', 'program', 'course')
    search_fields = ('merchant_txn_id', 'gateway_txn_id', 'user__email', 'program__name', 'course__name')
    readonly_fields = ('merchant_txn_id', 'transaction_date', 'last_updated', 'total_amount')
    filter_horizontal = ('subjects',)
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('merchant_txn_id', 'gateway_txn_id', 'process_id', 'instrument_code', 'status')
        }),
        ('User and Program Information', {
            'fields': ('user', 'program', 'course', 'subjects')
        }),
        ('Payment Information', {
            'fields': ('amount', 'service_charge', 'total_amount')
        }),
        ('Additional Information', {
            'fields': ('remarks', 'transaction_date', 'last_updated'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # Only for new objects
            obj.total_amount = obj.amount + obj.service_charge
        super().save_model(request, obj, form, change)


@admin.register(NCHLPayment)
class NCHLPaymentAdmin(admin.ModelAdmin):
    list_display = ('merchant_txn_id', 'user', 'program', 'course', 'amount', 'status', 'timestamp')
    list_filter = ('status', 'timestamp', 'program', 'course')
    search_fields = ('merchant_txn_id', 'transaction_id', 'user__email', 'program__name', 'course__name')
    readonly_fields = ('merchant_txn_id', 'timestamp', 'last_updated', 'response_payload')
    filter_horizontal = ('subjects',)
    fieldsets = (
        ('Transaction Details', {
            'fields': ('merchant_txn_id', 'transaction_id', 'gateway_txn_id', 'status')
        }),
        ('User and Program Information', {
            'fields': ('user', 'program', 'course', 'subjects')
        }),
        ('Payment Information', {
            'fields': ('amount',)
        }),
        ('System Information', {
            'fields': ('timestamp', 'last_updated', 'response_payload'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BillingHistory)
class BillingHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'program', 'course', 'amount', 'payment_kind', 'created_at', 'invoice_link')
    list_filter = ('payment_kind', 'created_at', 'program', 'course')
    search_fields = ('user__email', 'merchant_txn_id', 'transaction_id')

    def invoice_link(self, obj):
        if obj.invoice_pdf:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.invoice_pdf.url)
        return '-'
    invoice_link.short_description = 'Invoice'


@admin.register(QrPaymentTransaction)
class QrPaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'user', 'program', 'course', 'transaction_amount', 'status', 'transaction_date')
    list_filter = ('status', 'transaction_date', 'program', 'course')
    search_fields = ('bill_number', 'user__email', 'program__name', 'course__name')
    readonly_fields = ('bill_number', 'transaction_date', 'last_updated')
    filter_horizontal = ('subjects',)
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('bill_number', 'status')
        }),
        ('User and Program Information', {
            'fields': ('user', 'program', 'course', 'subjects')
        }),
        ('Payment Information', {
            'fields': ('transaction_amount',)
        }),
        ('System Information', {
            'fields': ('transaction_date', 'last_updated'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ZoomAllowedHost)
class ZoomAllowedHostAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'enabled', 'created_at', 'updated_at')
    list_filter = ('enabled', 'created_at', 'updated_at')
    search_fields = ('email', 'name')
    list_editable = ('enabled',)
    
    fieldsets = (
        ('Host Information', {
            'fields': ('email', 'name', 'enabled')
        }),
        ('Additional Information', {
            'fields': ('notes',),
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    actions = ['enable_hosts', 'disable_hosts', 'extract_from_webhook_logs']
    
    def enable_hosts(self, request, queryset):
        """Enable recording processing for selected hosts"""
        updated = queryset.update(enabled=True)
        self.message_user(request, f'{updated} host(s) enabled for recording processing.', messages.SUCCESS)
    enable_hosts.short_description = "Enable selected hosts"
    
    def disable_hosts(self, request, queryset):
        """Disable recording processing for selected hosts"""
        updated = queryset.update(enabled=False)
        self.message_user(request, f'{updated} host(s) disabled for recording processing.', messages.WARNING)
    disable_hosts.short_description = "Disable selected hosts"
    
    def extract_from_webhook_logs(self, request, queryset):
        """Extract unique host emails from webhook logs and add them as allowed hosts"""
        from .models import ZoomWebhookLog
        
        # Get unique host emails from webhook logs
        webhook_emails = ZoomWebhookLog.objects.filter(
            host_email__isnull=False
        ).exclude(
            host_email=''
        ).values_list('host_email', flat=True).distinct()
        
        added_count = 0
        existing_count = 0
        
        for email in webhook_emails:
            _, created = ZoomAllowedHost.objects.get_or_create(
                email=email,
                defaults={'enabled': False}  # Default to disabled for safety
            )
            if created:
                added_count += 1
            else:
                existing_count += 1
        
        self.message_user(
            request, 
            f'Added {added_count} new host(s). {existing_count} already existed. Please enable the ones you want to process.',
            messages.SUCCESS
        )
    extract_from_webhook_logs.short_description = "Extract hosts from webhook logs (adds as disabled)"


@admin.register(ZoomWebhookLog)
class ZoomWebhookLogAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'meeting_id', 'host_email', 'processed', 'created_at')
    list_filter = ('event_type', 'processed', 'created_at')
    search_fields = ('event_type', 'meeting_id', 'host_email')
    readonly_fields = ('event_type', 'meeting_id', 'host_email', 'payload', 'created_at')
    
    fieldsets = (
        ('Webhook Information', {
            'fields': ('event_type', 'meeting_id', 'host_email', 'processed')
        }),
        ('Payload Data', {
            'fields': ('payload',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Webhooks are created automatically, so disable manual creation"""
        return False


@admin.register(ZoomRecording)
class ZoomRecordingAdmin(admin.ModelAdmin):
    list_display = (
        'zoom_recording_id', 
        'zoom_meeting_id',
        'host_email',
        'status', 
        'duration_formatted', 
        'file_size_mb', 
        'recording_start_time',
        'live_class',
        'subject_recording_video'
    )
    list_filter = (
        'status', 
        'file_type',
        'host_email',
        'recording_start_time',
        'live_class__subject',
        'created_at'
    )
    search_fields = (
        'zoom_recording_id', 
        'zoom_meeting_id', 
        'zoom_meeting_uuid',
        'host_email',
        'live_class__title',
        'live_class__subject__name'
    )
    readonly_fields = (
        'zoom_recording_id',
        'zoom_meeting_id', 
        'zoom_meeting_uuid',
        'host_email',
        'recording_start_time',
        'recording_end_time',
        'duration',
        'duration_formatted',
        'file_size',
        'file_size_mb',
        'file_type',
        'zoom_download_url',
        'download_token',
        'processing_started_at',
        'processing_completed_at',
        'created_at',
        'updated_at'
    )
    
    fieldsets = (
        ('Zoom Information', {
            'fields': (
                'zoom_recording_id', 
                'zoom_meeting_id', 
                'zoom_meeting_uuid',
                'host_email',
                'zoom_download_url',
                'download_token'
            )
        }),
        ('Recording Details', {
            'fields': (
                'recording_start_time',
                'recording_end_time', 
                'duration',
                'duration_formatted',
                'file_size',
                'file_size_mb',
                'file_type'
            )
        }),
        ('Storage Information', {
            'fields': (
                'r2_storage_key',
                'r2_storage_url'
            )
        }),
        ('Processing Status', {
            'fields': (
                'status',
                'processing_started_at',
                'processing_completed_at',
                'error_message'
            )
        }),
        ('Relationships', {
            'fields': (
                'live_class',
                'subject_recording_video'
            )
        }),
        ('System Information', {
            'fields': (
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['process_recordings', 'retry_failed_recordings', 'retry_stuck_recordings']
    
    def file_size_mb(self, obj):
        """Display file size in MB"""
        if obj.file_size:
            return f"{round(obj.file_size / (1024 * 1024), 2)} MB"
        return "Unknown"
    file_size_mb.short_description = 'File Size (MB)'
    
    def process_recordings(self, request, queryset):
        """Admin action to process selected recordings"""
        from .zoom_service import ZoomRecordingService
        
        zoom_service = ZoomRecordingService()
        processed = 0
        failed = 0
        
        for recording in queryset.filter(status='pending'):
            if zoom_service.process_recording(recording):
                processed += 1
            else:
                failed += 1
        
        message = f"Processed {processed} recordings"
        if failed > 0:
            message += f", {failed} failed"
        
        self.message_user(request, message)
    
    process_recordings.short_description = "Process selected recordings"
    
    def retry_failed_recordings(self, request, queryset):
        """Admin action to retry failed recordings"""
        from .zoom_service import ZoomRecordingService
        
        zoom_service = ZoomRecordingService()
        retried = 0
        success = 0
        
        for recording in queryset.filter(status='failed'):
            recording.status = 'pending'
            recording.error_message = None
            recording.save()
            
            if zoom_service.process_recording(recording):
                success += 1
            retried += 1
        
        message = f"Retried {retried} recordings, {success} successful"
        self.message_user(request, message)
    
    retry_failed_recordings.short_description = "Retry failed recordings"
    
    def retry_stuck_recordings(self, request, queryset):
        """Admin action to retry stuck processing recordings"""
        from .zoom_service import ZoomRecordingService
        from django.utils import timezone
        from datetime import timedelta
        
        zoom_service = ZoomRecordingService()
        retried = 0
        success = 0
        
        # Only process recordings that have been stuck for more than 1 hour
        cutoff_time = timezone.now() - timedelta(hours=1)
        stuck_recordings = queryset.filter(
            status='processing',
            processing_started_at__lt=cutoff_time
        )
        
        for recording in stuck_recordings:
            recording.status = 'pending'
            recording.error_message = None
            recording.processing_started_at = None
            recording.processing_completed_at = None
            recording.save()
            
            if zoom_service.process_recording(recording):
                success += 1
            retried += 1
        
        message = f"Retried {retried} stuck recordings, {success} successful"
        self.message_user(request, message)
    
    retry_stuck_recordings.short_description = "Retry stuck processing recordings"
    
    def get_urls(self):
        """Add custom admin URLs for manual actions"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'sync-recordings/',
                self.admin_site.admin_view(self.sync_recordings_view),
                name='zoom-sync-recordings'
            ),
            path(
                'process-pending/',
                self.admin_site.admin_view(self.process_pending_view),
                name='zoom-process-pending'
            ),
        ]
        return custom_urls + urls
    
    def sync_recordings_view(self, request):
        """Custom admin view to sync recordings from Zoom"""
        if request.method == 'POST':
            from .zoom_service import ZoomRecordingService
            from datetime import datetime, timedelta
            
            try:
                zoom_service = ZoomRecordingService()
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                
                meetings = zoom_service.get_recordings_by_date_range(start_date, end_date)
                synced_count = 0
                
                for meeting in meetings:
                    # Process meeting recordings (similar to sync_zoom_recordings view)
                    # Implementation would be similar to the view function
                    pass
                
                self.message_user(request, f"Synced {synced_count} new recordings from Zoom")
                
            except Exception as e:
                self.message_user(request, f"Error syncing recordings: {str(e)}", level=messages.ERROR)
            
            return redirect('..')
        
        return render(request, 'admin/zoom_sync_form.html', {
            'title': 'Sync Zoom Recordings',
            'opts': self.model._meta,
        })
    
    def process_pending_view(self, request):
        """Custom admin view to process all pending recordings"""
        if request.method == 'POST':
            from .zoom_service import ZoomRecordingService
            
            try:
                zoom_service = ZoomRecordingService()
                results = zoom_service.process_pending_recordings()
                
                self.message_user(
                    request, 
                    f"Processed {results['processed']} recordings, {results['failed']} failed"
                )
                
            except Exception as e:
                self.message_user(request, f"Error processing recordings: {str(e)}", level=messages.ERROR)
            
            return redirect('..')
        
        pending_count = ZoomRecording.objects.filter(status='pending').count()
        
        return render(request, 'admin/zoom_process_form.html', {
            'title': 'Process Pending Recordings',
            'opts': self.model._meta,
            'pending_count': pending_count,
        })
    
    def changelist_view(self, request, extra_context=None):
        """Add custom buttons to the changelist view"""
        if extra_context is None:
            extra_context = {}
        
        extra_context['sync_recordings_url'] = 'sync-recordings/'
        extra_context['process_pending_url'] = 'process-pending/'
        extra_context['pending_count'] = ZoomRecording.objects.filter(status='pending').count()
        
        return super().changelist_view(request, extra_context=extra_context)

