from django.db import models

# Create your models here.
class Instructor(models.Model):
    name = models.CharField(max_length=100)
    bio = models.CharField(max_length=100)
    image = models.ImageField(upload_to='instructors/', null=True, blank=True)

    def __str__(self):
        return self.name

class Hero(models.Model):
    title = models.CharField(max_length=200, verbose_name='Hero Title')
    description = models.TextField(verbose_name='Description', blank=True, null=True)
    image = models.ImageField(upload_to='hero_images/', verbose_name='Hero Image')
    link = models.URLField(max_length=200, verbose_name='Link to Course or Page', blank=True, null=True)
    button_text = models.CharField(max_length=50, verbose_name='Call to Action Button Text', default='Learn More')
    display_order = models.PositiveIntegerField(default=1, verbose_name='Display Order', help_text="The order in which this Hero section will appear")
    active = models.BooleanField(default=True, verbose_name='Is Active?', help_text="Set to false to hide this Hero section from the front end")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')

    class Meta:
        ordering = ['display_order']
        verbose_name = 'Hero Section'
        verbose_name_plural = 'Hero Sections'

    def __str__(self):
        return self.title
