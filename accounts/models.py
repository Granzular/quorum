from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
import re
from uuid6 import uuid7


class CustomUser(AbstractUser):
    phone = models.CharField(max_length = 20, blank = True, null = True)

class Profile(models.Model):
    user = models.OneToOneField(CustomUser,on_delete=models.CASCADE,related_name='profile')
    avatar = models.ImageField(upload_to = "accounts",null=True,blank=True)
    matric_no = models.CharField(unique=True,max_length=14)
    dept = models.CharField(max_length = 64, default = "Computer Science")
    

    def clean(self):
        if re.match(r"^\d{4}\d{8}[A-Za-z]{2}$", self.matric_no) or re.match(r"^CSC/\d{2}/\d{4}$", self.matric_no) :
            ...
        else:
            raise ValidationError({
                'matric_no': 'This field does not satisfy the pattern CSC/00/0000 or 202412345678AB'
            })

    def __str__(self):
        return f"Profile of  {self.user.username}"
