import django_filters
from api.models import Video

class VideoFilter(django_filters.FilterSet):
    program = django_filters.CharFilter(field_name='topic__chapters__subjects__courses_program__name', lookup_expr='icontains')
    course = django_filters.CharFilter(field_name='topic__chapters__subjects__courses__name', lookup_expr='icontains')

    class Meta:
        model = Video
        fields = ['program', 'course']
