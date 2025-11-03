# home/serializers.py


from rest_framework import serializers
from .models import Instructor, Hero


class InstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instructor
        fields = ['id', 'name', 'bio', 'image']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        if instance.image:
            representation['image'] = request.build_absolute_uri(instance.image.url) if request else None
        return representation

class HeroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hero
        fields = ['id', 'title', 'description', 'image', 'link', 'button_text', 'display_order', 'active', 'created_at', 'updated_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        if instance.image:
            representation['image'] = request.build_absolute_uri(instance.image.url) if request else None
        return representation
