from rest_framework.serializers import ModelSerializer
from community.models import Content

class PostSerializer(ModelSerializer):

    class Meta:
        model = Content
        fields = '__all__'