# # views.py

# import pandas as pd
# from django.shortcuts import get_object_or_404
# from rest_framework import status, views
# from rest_framework.parsers import MultiPartParser, FormParser
# from rest_framework.response import Response
# from rest_framework.permissions import IsAdminUser
# from api.models import MockTest, MockTestQuestion
# from .serializers import MockTestQuestionSerializer

# class MockTestQuestionImportView(views.APIView):
#     """
#     API view to handle importing MockTestQuestion data via file upload (CSV/Excel)
#     with column-based mapping.
#     """
#     parser_classes = [MultiPartParser, FormParser]
#     permission_classes = [IsAdminUser]

#     def post(self, request, mocktest_id, format=None):
#         """
#         Imports questions and associates them with the specified MockTest.
#         """
#         mocktest = get_object_or_404(MockTest, id=mocktest_id)

#         if 'file' not in request.FILES:
#             return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

#         file = request.FILES['file']
#         try:
#             data = self.parse_file(file)
#             questions_serializer = MockTestQuestionSerializer(data=data, many=True)
#             if questions_serializer.is_valid():
#                 questions = questions_serializer.save()
#                 mocktest.mocktest_questions.add(*questions)
#                 return Response({'message': 'Questions imported successfully.'}, status=status.HTTP_201_CREATED)
#             else:
#                 return Response(questions_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

#     def parse_file(self, file):
#         """
#         Parses CSV or Excel file and maps columns based on index.
#         Expected column order:
#             0: question_text
#             1: question_image_url
#             2: option_0_text
#             3: option_1_text
#             4: option_2_text
#             5: option_3_text
#             6: option_0_image_url
#             7: option_1_image_url
#             8: option_2_image_url
#             9: option_3_image_url
#             10: answer
#             11: weight
#             12: explanation
#             13: explanation_image_url
#         """
#         file_extension = file.name.split('.')[-1].lower()
#         if file_extension in ['xlsx', 'xls']:
#             df = pd.read_excel(file, engine='openpyxl', header=None)
#         elif file_extension == 'csv':
#             df = pd.read_csv(file, header=None)
#         else:
#             raise ValueError('Unsupported file format. Please upload a CSV or Excel file.')

#         expected_columns = 14  # Columns 0 to 13
#         if df.shape[1] < expected_columns:
#             raise ValueError(f'File has insufficient columns. Expected at least {expected_columns} columns.')

#         data = []
#         for index, row in df.iterrows():
#             question_data = {
#                 'question_text': row[0],
#                 'question_image_url': row[1],
#                 'option_0_text': row[2],
#                 'option_1_text': row[3],
#                 'option_2_text': row[4],
#                 'option_3_text': row[5],
#                 'option_0_image_url': row[6],
#                 'option_1_image_url': row[7],
#                 'option_2_image_url': row[8],
#                 'option_3_image_url': row[9],
#                 'answer': row[10],
#                 'weight': row[11],
#                 'explanation': row[12],
#                 'explanation_image_url': row[13],
#             }

#             # Optional: Validate required fields
#             if pd.isna(question_data['question_text']) or pd.isna(question_data['answer']) or pd.isna(question_data['weight']):
#                 raise ValueError(f'Required fields missing in row {index + 1}.')

#             data.append(question_data)

#         return data
