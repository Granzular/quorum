from django.db import models
from accounts.models import CustomUser as User
from uuid6 import uuid7

class Content(models.Model):
    TYPE_CHOICES = [
        ('post','Post'),
        ('comment','Comment')
    ]
    id = models.UUIDField( primary_key=True, default=uuid7, editable=False, db_index=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=128,blank=True,null=True)
    author = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.TextField(default=' ')
    parent = models.ForeignKey("self",null=True,blank=True,on_delete=models.CASCADE,related_name="replies")
    media = models.FileField(upload_to='posts/', blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    class Meta:
        ordering = ['-updated']

    def toggle_like(self,user):
        exist = self.likes.filter(user=user).exists()
        if exist:
            self.likes.get(user=user).delete()
        else:
            Like.objects.create(user=user,content=self)
        


class Like(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    content = models.ForeignKey(Content,on_delete=models.CASCADE,related_name='likes')

    class Meta:
        unique_together = ("user","content")