from django.contrib import admin

# Register your models here.
admin.site.site_header = "Coding for Kids Admin"
admin.site.site_title = "Coding for Kids Admin Portal"
admin.site.index_title = "Welcome to Coding for Kids Admin Portal"



from django.contrib import admin
from .models import Instructor, Hero

# Register the Instructor model
@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ('name', 'bio', 'image')
    search_fields = ('name',)

# Register the Hero model
@admin.register(Hero)
class HeroAdmin(admin.ModelAdmin):
    list_display = ('title', 'active', 'display_order', 'created_at', 'updated_at')
    list_filter = ('active',)
    search_fields = ('title',)
    ordering = ('display_order',)

