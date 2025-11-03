from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from .models import CustomUser, DeviceToken
# from .models import CustomUser, Subject, SolvedMcq, SolvedMcqAnswer, SolvedChapterMcq, SolvedChapterMcqAnswer

class CustomUserAdmin(UserAdmin):
    # Fields to display in the admin list view
    list_display = ('username', 'first_name', 'last_name', 'email', 'user_type', 'profile_image', 'phone', 'city', 'is_staff')
    list_filter = ('user_type', 'is_staff', 'is_superuser', 'is_active')

    # Fields to display and organize in the admin detail/edit view
    fieldsets = (
        (None, {'fields': ('user_id', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'address', 'city', 'profile_image')}),
        ('Permissions', {
            'fields': ('user_type', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'last_login_token')}),
        ('Associations', {'fields': ('programs', 'courses','subjects', 'mocktest_results')}),

    )

    # Fields to display when creating a new user in the admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('user_id', 'username', 'email', 'phone', 'password1', 'password2', 'user_type', 'is_staff', 'is_active', 'profile_image')}
        ),
    )
    list_per_page = 50  # Pagination to reduce load per page
    show_full_result_count = False  # Avoid expensive COUNT(*) for large datasets

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Limit selected columns to speed up list view and avoid loading M2M on changelist
        qs = qs.only(
            'id', 'username', 'first_name', 'last_name', 'email', 'user_type',
            'profile_image', 'phone', 'city', 'is_staff', 'last_login', 'date_joined'
        )
        return qs

    @method_decorator(cache_page(60))
    def changelist_view(self, request, extra_context=None):
        # Cache the admin user list for 60s to reduce DB load under traffic
        return super().changelist_view(request, extra_context=extra_context)

    search_fields = ('user_id', 'username', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('user_id', 'username',)
    filter_horizontal = ('programs','courses', 'subjects', 'mocktest_results')
    # filter_horizontal = ('programs', 'subjects', 'mcq_results', 'mocktest_results')

# Register the CustomUser model and the CustomUserAdmin configuration
admin.site.register(CustomUser, CustomUserAdmin)
@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'active', 'updated_at')
    list_filter = ('platform', 'active')
    search_fields = ('user__email', 'token')



# class SubjectAdmin(admin.ModelAdmin):
#     list_display = ('subject_name', 'user_id')
#     search_fields = ('subject_name', 'user__user_id')

# class SolvedMcqAdmin(admin.ModelAdmin):
#     list_display = ('mcq_title', 'user_id', 'start_time', 'end_time')
#     search_fields = ('mcq_title', 'user__user_id')
#     list_filter = ('start_time', 'end_time')

# class SolvedMcqAnswerAdmin(admin.ModelAdmin):
#     list_display = ('question_id', 'selected_option', 'is_correct')
#     search_fields = ('question_id',)

# class SolvedChapterMcqAdmin(admin.ModelAdmin):
#     list_display = ('mcq_title', 'user_id', 'chapter_id', 'start_time', 'end_time')
#     search_fields = ('mcq_title', 'user__user_id', 'chapter_id')
#     list_filter = ('start_time', 'end_time')

# class SolvedChapterMcqAnswerAdmin(admin.ModelAdmin):
#     list_display = ('question_id', 'selected_option', 'is_correct')
#     search_fields = ('question_id',)

# admin.site.register(Subject, SubjectAdmin)
# admin.site.register(SolvedMcq, SolvedMcqAdmin)
# admin.site.register(SolvedMcqAnswer, SolvedMcqAnswerAdmin)
# admin.site.register(SolvedChapterMcq, SolvedChapterMcqAdmin)
# admin.site.register(SolvedChapterMcqAnswer, SolvedChapterMcqAnswerAdmin)
