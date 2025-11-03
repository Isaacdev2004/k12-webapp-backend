# from rest_framework import serializers

# from api.models import ( MockTest,MockTestQuestion)



# class MockTestQuestionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = MockTestQuestion
#         fields = [
#             'id',
#             'question_text',
#             'question_image_url',
#             'option_0_text',
#             'option_1_text',
#             'option_2_text',
#             'option_3_text',
#             'option_0_image_url',
#             'option_1_image_url',
#             'option_2_image_url',
#             'option_3_image_url',
#             'answer',
#             'weight',
#             'explanation',
#             'explanation_image_url',
#         ]

#     def validate_answer(self, value):
#         if value not in [0, 1, 2, 3]:
#             raise serializers.ValidationError("Answer must be one of 0, 1, 2, or 3.")
#         return value

# class MockTestSerializer(serializers.ModelSerializer):
#     mocktest_questions = MockTestQuestionSerializer(many=True, required=False)

#     class Meta:
#         model = MockTest
#         fields = [
#             'id',
#             'name',
#             'description',
#             'public',
#             'is_free',
#             'mode',
#             'scheduled_start_time',
#             'duration',
#             'negMark',
#             'mocktest_questions',
#         ]

#     def create(self, validated_data):
#         questions_data = validated_data.pop('mocktest_questions', [])
#         mocktest = MockTest.objects.create(**validated_data)
#         for question_data in questions_data:
#             question = MockTestQuestion.objects.create(**question_data)
#             mocktest.mocktest_questions.add(question)
#         return mocktest

#     def update(self, instance, validated_data):
#         questions_data = validated_data.pop('mocktest_questions', [])
#         for attr, value in validated_data.items():
#             setattr(instance, attr, value)
#         instance.save()

#         if questions_data:
#             instance.mocktest_questions.clear()
#             for question_data in questions_data:
#                 question = MockTestQuestion.objects.create(**question_data)
#                 instance.mocktest_questions.add(question)
#         return instance
