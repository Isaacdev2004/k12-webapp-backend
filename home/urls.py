from django.urls import path
from rest_framework.routers import DefaultRouter
from django.urls import include
from .views import ProgramWithMockTestsViewSet,LiveClassList,InstructorViewSet,HeroViewSet
app_name = 'home'


router = DefaultRouter()
router.register(r'program-courses-with-mocktests-notes', ProgramWithMockTestsViewSet)
router.register(r'liveclasslist', LiveClassList, basename='profvideo')
router.register(r'instructors', InstructorViewSet)
router.register(r'heroes', HeroViewSet)

urlpatterns = [
    path('', include(router.urls)),

]