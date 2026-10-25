from django.db import models, router
from django.conf import settings
from accounts.models import CustomUser as User
from uuid6 import uuid7
from main.media_cleanup import FileCleanupQuerySet, delete_with_file_cleanup, save_with_file_cleanup
from main.media_storage import file_storage

class Content(models.Model):
    objects = models.Manager.from_queryset(FileCleanupQuerySet)()

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
    media = models.FileField(
        upload_to=settings.MEDIA_UPLOAD_FOLDERS['community']['posts'],
        storage=file_storage, blank=True, null=True,
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def save(self, **kwargs):
        """Clean up replaced or cleared media after the reference commits."""
        return save_with_file_cleanup(self, super().save, **kwargs)

    def delete(self, using=None, keep_parents=False):
        using = using or router.db_for_write(type(self), instance=self)
        return delete_with_file_cleanup(
            self, super().delete, using=using, keep_parents=keep_parents,
        )

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
