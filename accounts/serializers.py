from rest_framework import serializers
from accounts.models import Profile, CustomUser as User
from rest_framework.exceptions import ValidationError
import re


class RegisterSerializer(serializers.ModelSerializer):
    # This Serializer is tailored for student registration.

    matric_no = serializers.CharField(max_length=12,write_only=True)
    class Meta:
        model = User
        fields = ['username','matric_no','password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        matric_no = validated_data.pop('matric_no')
        if re.match(r"^\d{4}\d{8}[A-Za-z]{2}$", matric_no) or re.match(r"^CSC/\d{2}/\d{4}$", matric_no):
            ...
        else:
            raise ValidationError({
                'matric_no': 'This field does not satisfy the pattern CSC/00/0000 or 202412345678AB'
            })
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password']
        )
        Profile.objects.create(user=user,matric_no=matric_no)
        return user


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['matric_no', 'dept','avatar']


class ManageProfileSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'profile']
        extra_kwargs = {
            'email':{'read_only':True},
            'phone':{'read_only':True},
        }

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        
        # Update user fields
        '''
        instance.username = validated_data.get('username', instance.username)
        instance.email = validated_data.get('email', instance.email)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.phone = validated_data.get('phone', instance.phone)
        '''

        for attr, value in validated_data.items():
            setattr(instance,attr,value)
        instance.save()
        
        # Update or create profile
        if profile_data:
            Profile.objects.update(
                user=instance,
                **profile_data
            )
        
        return instance