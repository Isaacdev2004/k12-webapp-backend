from rest_framework import viewsets, permissions
from rest_framework.response import Response
from api.models import Program, Course
from rest_framework.permissions import IsAuthenticated,AllowAny

class ProgramWithMockTestsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Program.objects.filter(published=True)
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        programs_data = []
        for program in self.queryset:
            program_data = {
                "id": program.id,
                "program_name": program.name,
                "mock_tests": [],
                "videos": [],
                "notes": []
            }
            # Check if the Program has an associated Course
            if program.course:
                course = program.course  # For readability

                # 1) Collect Videos (through Subject -> Chapter -> Topic -> Video)
                for subject in course.subjects.all():
                    for chapter in subject.subject_chapters.all():
                        for topic in chapter.topics.all():  # Corrected from 'topic' to 'topics'
                            free_videos = topic.videos.filter(is_free=True)
                            for video in free_videos:
                                video_data = {
                                    "id": video.id,
                                    "title": video.title,  # Corrected from 'name' to 'title'
                                    "video_url": video.video_url,
                                    "is_free": video.is_free,
                                    "is_active": video.is_active,  # Corrected from 'published' to 'is_active'
                                    "video_file": (
                                        video.video_file.url 
                                        if video.video_file
                                        else None
                                    ),
                                    "video_description": video.video_description,
                                    "thumbnail": (
                                        request.build_absolute_uri(video.thumbnail.url)
                                        if video.thumbnail
                                        else None
                                    ),
                                    "video_duration": video.video_duration,
                                    "created_at": video.created_at,
                                }
                                program_data["videos"].append(video_data)

                # 2) Collect MockTests from the Course
                for mock_test in course.mock_tests.all():  # Corrected from 'mockTests' to 'mock_tests'
                    mock_test_data = {
                        "id": mock_test.id,
                        "title": mock_test.title,  # Corrected from 'name' to 'title'
                        "description": mock_test.description,
                        "is_free": mock_test.is_free,
                        "created_at": mock_test.created_at,
                        "updated_at": mock_test.updated_at,
                        "status": mock_test.status,  # Added existing field
                        "scheduled_start_time": mock_test.scheduled_start_time,
                        "duration": mock_test.duration,
                        "negMark": mock_test.negMark,
                        "start_time": mock_test.start_time,
                        "end_time": mock_test.end_time,
                    }
                    program_data["mock_tests"].append(mock_test_data)

                # 3) Collect Notes from the Course
                for note in course.notes.all():
                    note_data = {
                        "id": note.id,
                        "title": note.title,
                        "pdf": note.pdf.url if note.pdf else None,
                        "is_free": note.is_free,
                        "created_at": note.created_at,
                    }
                    program_data["notes"].append(note_data)

            programs_data.append(program_data)

        return Response(programs_data)




class LiveClassList(viewsets.ReadOnlyModelViewSet):
    queryset = Program.objects.filter(published=True)
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        programs_data = []
        for program in self.queryset:
            program_data = {
                "id": program.id,
                "name": program.name,
                "courses": []
            }

            if program.course and program.course.published:  # Direct access since it's a ForeignKey
                course = program.course
                course_data = {
                    "id": course.id,
                    "name": course.name,
                    "subjects": []
                }

                for subject in course.subjects.filter(published=True):
                    liveclass = subject.liveclass
                    subject_data = {
                        "id": subject.id,
                        "name": subject.name,
                        "subject_thumbnail": (
                            request.build_absolute_uri(subject.subject_thumbnail.url)
                            if subject.subject_thumbnail else None
                        ),
                        "liveclass": {
                            "id": liveclass.id if liveclass else None,
                            "name": liveclass.name if liveclass else None,
                            "description": liveclass.description if liveclass else None,
                            "start_time": liveclass.start_time if liveclass else None,
                            "end_time": liveclass.end_time if liveclass else None,
                            "zoom_meeting_id": liveclass.zoom_meeting_id if liveclass else None,
                            "zoom_password": liveclass.zoom_password if liveclass else None,
                            "status": liveclass.status if liveclass else None,
                            "created_at": liveclass.created_at if liveclass else None,
                            "updated_at": liveclass.updated_at if liveclass else None,
                            "is_recurring": liveclass.is_recurring if liveclass else None,
                            "is_free_meeting": liveclass.is_free_meeting if liveclass else None,
                            "public": liveclass.public if liveclass else None,
                        } if liveclass else None,
                    }
                    course_data["subjects"].append(subject_data)

                program_data["courses"].append(course_data)

            programs_data.append(program_data)

        return Response(programs_data)


from .models import Instructor,Hero
from .serializers import InstructorSerializer,HeroSerializer

class InstructorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Instructor.objects.all()
    serializer_class = InstructorSerializer
    permission_classes = [AllowAny]  



class HeroViewSet(viewsets.ModelViewSet):
    queryset = Hero.objects.filter(active=True).order_by('display_order')
    serializer_class = HeroSerializer